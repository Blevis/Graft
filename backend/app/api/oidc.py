"""OpenID Connect sign-in (authorization code flow with PKCE). Production identity; demo login is disabled there.

Validation: discovery document issuer must equal OIDC_ISSUER; the ID token signature is checked against the
provider's JWKS (PyJWT), with issuer, audience (client id), expiry, issued-at and the nonce we sent. state and the
PKCE verifier travel in a short-lived, signed, HttpOnly cookie scoped to the callback path.

Who gets in: an existing identity link (issuer + subject), else an active member of OIDC_ORG_SLUG whose verified
email matches (the link is then recorded), else, when OIDC_GROUP_ROLE_MAP is configured and the token carries a
mapped group, just-in-time provisioning into that org. Roles from mapped groups are granted at organization scope
and removed when the group disappears; every change is audited. Nobody else is admitted (403)."""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Membership, Org, RoleAssignment, User, UserIdentity
from ..models._base import utcnow
from ..services import audit
from ..services.roles import ROLE_CODES
from .auth import start_session

router = APIRouter(prefix="/auth/oidc", tags=["auth"])
FLOW_COOKIE = "graft_oidc"
_cache: dict = {}
_TRANSPORT: httpx.BaseTransport | None = None  # tests install a mock issuer here


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _TRANSPORT
    _TRANSPORT = t
    _cache.clear()


def _http() -> httpx.Client:
    return httpx.Client(timeout=10.0, transport=_TRANSPORT)


def _require_oidc():
    if get_settings().AUTH_MODE != "oidc":
        raise HTTPException(404, "Not found")


def discovery() -> dict:
    s = get_settings()
    if "discovery" not in _cache:
        with _http() as h:
            r = h.get(s.OIDC_ISSUER.rstrip("/") + "/.well-known/openid-configuration")
        r.raise_for_status()
        doc = r.json()
        if doc.get("issuer") != s.OIDC_ISSUER:
            raise HTTPException(502, "Identity provider issuer mismatch")
        _cache["discovery"] = doc
    return _cache["discovery"]


def _jwks(refresh: bool = False) -> dict:
    if refresh or "jwks" not in _cache:
        with _http() as h:
            r = h.get(discovery()["jwks_uri"])
        r.raise_for_status()
        _cache["jwks"] = r.json()
    return _cache["jwks"]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@router.get("/login")
def login(request: Request):
    _require_oidc()
    s = get_settings()
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    params = {"response_type": "code", "client_id": s.OIDC_CLIENT_ID, "redirect_uri": s.OIDC_REDIRECT_URI,
              "scope": s.OIDC_SCOPES, "state": state, "nonce": nonce,
              "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()), "code_challenge_method": "S256"}
    resp = RedirectResponse(discovery()["authorization_endpoint"] + "?" + urlencode(params), status_code=302)
    flow = jwt.encode({"state": state, "nonce": nonce, "verifier": verifier, "exp": int(time.time()) + 600},
                      s.SESSION_SECRET, algorithm="HS256")
    resp.set_cookie(FLOW_COOKIE, flow, httponly=True, samesite="lax", secure=request.url.scheme == "https",
                    max_age=600, path="/api/auth/oidc")
    return resp


def validate_id_token(id_token: str, nonce: str) -> dict:
    s = get_settings()
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError:
        raise HTTPException(401, "Malformed ID token")
    algs = [a.strip() for a in s.OIDC_ALGORITHMS.split(",") if a.strip()]
    if header.get("alg") not in algs:
        raise HTTPException(401, "ID token algorithm not allowed")
    keys = [k for k in _jwks().get("keys", []) if k.get("kid") == header.get("kid")] or \
        [k for k in _jwks(refresh=True).get("keys", []) if k.get("kid") == header.get("kid")]
    if not keys:
        raise HTTPException(401, "Unknown signing key")
    try:
        claims = jwt.decode(id_token, jwt.PyJWK(keys[0]).key, algorithms=algs, audience=s.OIDC_CLIENT_ID,
                            issuer=s.OIDC_ISSUER, leeway=60,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"ID token rejected ({type(e).__name__})")
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise HTTPException(401, "ID token nonce mismatch")
    return claims


def _group_roles(claims: dict) -> set[str] | None:
    s = get_settings()
    if not s.OIDC_GROUP_ROLE_MAP:
        return None
    mapping = json.loads(s.OIDC_GROUP_ROLE_MAP)
    groups = claims.get(s.OIDC_GROUPS_CLAIM) or []
    return {mapping[g] for g in groups if g in mapping and mapping[g] in ROLE_CODES}


def resolve_member(db: Session, claims: dict) -> tuple[User, Org]:
    s = get_settings()
    org = db.execute(select(Org).where(Org.slug == s.OIDC_ORG_SLUG)).scalar_one_or_none()
    if org is None:
        raise HTTPException(403, "Sign-in is not configured for an organisation")
    ident = db.execute(select(UserIdentity).where(UserIdentity.issuer == claims["iss"],
                                                  UserIdentity.subject == claims["sub"])).scalar_one_or_none()
    user = db.get(User, ident.user_id) if ident else None
    email = (claims.get("email") or "").strip().lower()
    if user is None and email and claims.get("email_verified") is True:
        user = db.execute(select(User).join(Membership, Membership.user_id == User.id).where(
            Membership.org_id == org.id, func.lower(User.email) == email)).scalars().first()
    mapped = _group_roles(claims)
    member = db.execute(select(Membership).where(Membership.org_id == org.id, Membership.user_id == user.id)
                        ).scalar_one_or_none() if user else None
    if member is None:
        if not mapped:
            raise HTTPException(403, "You are not provisioned in this organisation")
        user = user or User(name=claims.get("name") or email or "New member", email=email or None)
        db.add(user)
        db.flush()
        member = Membership(org_id=org.id, user_id=user.id, status="active", joined_at=utcnow())
        db.add(member)
        db.flush()
        audit.record(db, org_id=org.id, actor_user_id=None, entity="membership", entity_id=member.id,
                     action="provisioned_by_group", after={"user": user.id, "roles": sorted(mapped)})
    if member.status != "active":
        raise HTTPException(403, "This membership is not active")
    if ident is None:
        ident = UserIdentity(user_id=user.id, issuer=claims["iss"], subject=claims["sub"], email=email or None)
        db.add(ident)
        db.flush()
        audit.record(db, org_id=org.id, actor_user_id=user.id, entity="user_identity", entity_id=ident.id,
                     action="linked", after={"issuer": claims["iss"]})
    ident.last_login_at = utcnow()
    if mapped is not None:
        _sync_group_roles(db, org.id, user.id, mapped)
    return user, org


def _sync_group_roles(db: Session, org_id: str, user_id: str, wanted: set[str]) -> None:
    managed = set(json.loads(get_settings().OIDC_GROUP_ROLE_MAP).values())
    have = {g.role_code: g for g in db.execute(select(RoleAssignment).where(
        RoleAssignment.org_id == org_id, RoleAssignment.user_id == user_id, RoleAssignment.is_active.is_(True),
        RoleAssignment.scope_type == "organization")).scalars()}
    for role in wanted - set(have):
        g = RoleAssignment(org_id=org_id, user_id=user_id, role_code=role, scope_type="organization")
        db.add(g)
        db.flush()
        audit.record(db, org_id=org_id, actor_user_id=None, entity="role_assignment", entity_id=g.id,
                     action="granted_by_group", after=audit.snapshot(g))
    for role, g in have.items():
        if role in managed and role not in wanted:
            g.is_active, g.revoked_at = False, utcnow()
            audit.record(db, org_id=org_id, actor_user_id=None, entity="role_assignment", entity_id=g.id,
                         action="revoked_by_group", after=audit.snapshot(g))


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             db: Session = Depends(get_db)):
    _require_oidc()
    s = get_settings()
    if error:
        raise HTTPException(401, f"Sign-in failed at the identity provider ({error[:60]})")
    try:
        flow = jwt.decode(request.cookies.get(FLOW_COOKIE, ""), s.SESSION_SECRET, algorithms=["HS256"],
                          options={"require": ["exp"]})
    except jwt.PyJWTError:
        raise HTTPException(400, "Sign-in session expired; start again")
    if not code or not state or not secrets.compare_digest(state, flow["state"]):
        raise HTTPException(400, "State mismatch")
    form = {"grant_type": "authorization_code", "code": code, "redirect_uri": s.OIDC_REDIRECT_URI,
            "client_id": s.OIDC_CLIENT_ID, "code_verifier": flow["verifier"]}
    if s.OIDC_CLIENT_SECRET:
        form["client_secret"] = s.OIDC_CLIENT_SECRET
    with _http() as h:
        r = h.post(discovery()["token_endpoint"], data=form)
    if r.status_code != 200 or "id_token" not in r.json():
        raise HTTPException(401, "Token exchange failed")
    claims = validate_id_token(r.json()["id_token"], flow["nonce"])
    user, org = resolve_member(db, claims)
    audit.record(db, org_id=org.id, actor_user_id=user.id, entity="session", entity_id=user.id, action="oidc_login")
    db.commit()
    resp = RedirectResponse("/app/home", status_code=302)
    start_session(request, resp, user.id, org.id)
    resp.delete_cookie(FLOW_COOKIE, path="/api/auth/oidc")
    return resp
