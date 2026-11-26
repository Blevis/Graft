"""Phase 5: OIDC sign-in against a mocked issuer, CSRF, production mode, deactivation."""
import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import oidc
from app.config import get_settings
from app.db import SessionLocal
from app.models import User

ISS = "https://idp.example.test"
CLIENT = "graft-web"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "alg": "RS256", "use": "sig"}


class Issuer:
    def __init__(self):
        self.claims_override, self.nonce, self.challenge = {}, None, None

    def token(self, **extra):
        now = int(time.time())
        claims = {"iss": ISS, "aud": CLIENT, "sub": "idp-user-1", "iat": now, "exp": now + 300, "nonce": self.nonce,
                  "email": "dren.basha@ea.example", "email_verified": True, **self.claims_override, **extra}
        return jwt.encode(claims, KEY, algorithm="RS256", headers={"kid": "k1"})

    def handler(self, request: httpx.Request):
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={"issuer": ISS, "authorization_endpoint": f"{ISS}/authorize",
                                             "token_endpoint": f"{ISS}/token", "jwks_uri": f"{ISS}/jwks"})
        if request.url.path == "/jwks":
            return httpx.Response(200, json={"keys": [JWK]})
        if request.url.path == "/token":
            form = parse_qs(request.content.decode())
            verifier = form["code_verifier"][0]
            digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            if digest != self.challenge or form["code"][0] != "good-code":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": self.token(), "access_token": "x", "token_type": "Bearer"})
        return httpx.Response(404)


@pytest.fixture
def idp(app_client, monkeypatch):
    s = get_settings()
    for k, v in {"AUTH_MODE": "oidc", "OIDC_ISSUER": ISS, "OIDC_CLIENT_ID": CLIENT,
                 "OIDC_REDIRECT_URI": "http://localhost/api/auth/oidc/callback",
                 "OIDC_ORG_SLUG": "engineering-albania-demo", "OIDC_GROUP_ROLE_MAP": ""}.items():
        monkeypatch.setattr(s, k, v)
    with SessionLocal() as db:
        db.execute(select(User).where(User.name == "Dren Basha")).scalar_one().email = "dren.basha@ea.example"
        db.commit()
    issuer = Issuer()
    oidc.set_transport(httpx.MockTransport(issuer.handler))
    yield issuer
    oidc.set_transport(None)


def _sign_in(c: TestClient, issuer: Issuer, code="good-code", state=None):
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["response_type"] == ["code"]
    issuer.nonce, issuer.challenge = q["nonce"][0], q["code_challenge"][0]
    return c.get("/api/auth/oidc/callback", params={"code": code, "state": state or q["state"][0]},
                 follow_redirects=False)


def test_oidc_sign_in_links_identity_and_sets_session(idp, app_client):
    c = TestClient(app_client.app)
    r = _sign_in(c, idp)
    assert r.status_code == 302 and r.headers["location"] == "/app/home"
    me = c.get("/api/auth/me").json()
    assert me["user"]["name"] == "Dren Basha" and "org_admin" in me["roles"]
    # Password login is unavailable while AUTH_MODE=oidc, even with the right demo password.
    assert c.post("/api/auth/login", json={"email": "dren.basha@demo.graft.example",
                                           "password": "graft-demo"}).status_code == 404
    # Second sign-in uses the identity link (subject), even if the email changes.
    idp.claims_override = {"email": "renamed@ea.example"}
    c2 = TestClient(app_client.app)
    assert _sign_in(c2, idp).status_code == 302 and c2.get("/api/auth/me").json()["user"]["name"] == "Dren Basha"


@pytest.mark.parametrize("override,status", [
    ({"aud": "someone-else"}, 401), ({"iss": "https://evil.example"}, 401), ({"exp": int(time.time()) - 600}, 401),
    ({"nonce": "replayed"}, 401), ({"email": "stranger@ea.example", "sub": "other"}, 403),
    ({"email_verified": False, "sub": "other-2"}, 403),
])
def test_oidc_rejections(idp, app_client, override, status):
    idp.claims_override = override
    assert _sign_in(TestClient(app_client.app), idp).status_code == status


def test_state_pkce_and_flow_cookie(idp, app_client):
    assert _sign_in(TestClient(app_client.app), idp, state="forged").status_code == 400
    assert _sign_in(TestClient(app_client.app), idp, code="stolen-code").status_code == 401
    fresh = TestClient(app_client.app)  # no flow cookie
    assert fresh.get("/api/auth/oidc/callback", params={"code": "good-code", "state": "x"}).status_code == 400


def test_group_mapping_provisions_and_revokes(idp, app_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "OIDC_GROUP_ROLE_MAP", json.dumps({"graft-auditors": "auditor"}))
    idp.claims_override = {"sub": "new-1", "email": "new.auditor@ea.example", "name": "Nova Auditor",
                           "groups": ["graft-auditors"]}
    c = TestClient(app_client.app)
    assert _sign_in(c, idp).status_code == 302
    assert c.get("/api/auth/me").json()["roles"] == ["auditor"]
    idp.claims_override = {**idp.claims_override, "groups": []}
    c2 = TestClient(app_client.app)
    assert _sign_in(c2, idp).status_code == 302
    assert c2.get("/api/auth/me").json()["roles"] == []


def test_csrf_and_deactivation(login, app_client):
    admin = login("Dren Basha")
    bare = TestClient(app_client.app)
    bare.cookies.update(admin.cookies)
    assert bare.patch("/api/settings", json={"stale_days": 5}).status_code == 403  # no CSRF header
    assert admin.patch("/api/settings", json={"stale_days": 5}).status_code == 200
    gent = login("Gent Morina")
    users = {u["name"]: u["id"] for u in admin.get("/api/users").json()}
    admin.patch(f"/api/org/members/{users['Gent Morina']}", json={"status": "suspended"})
    assert gent.get("/api/cases").status_code == 401 and gent.get("/api/notifications").status_code == 401


def test_production_mode_disables_demo_accounts(app_client, accounts, monkeypatch):
    monkeypatch.setattr(get_settings(), "DEMO_MODE", False)
    c = TestClient(app_client.app)
    assert c.get("/api/auth/demo-accounts").status_code == 404
    email = next(iter(accounts.values()))["email"]
    assert c.post("/api/auth/login", json={"email": email, "password": "graft-demo"}).status_code == 404
    assert c.get("/api/auth/demo-password").status_code == 404


def test_expired_session_is_rejected(app_client, accounts):
    uid = accounts[("Engineering Albania (demo)", "Elira Dervishi")]
    expired = jwt.encode({"sub": uid["user_id"], "org": uid["org_id"], "iat": 1, "exp": 2},
                         get_settings().SESSION_SECRET, algorithm="HS256")
    c = TestClient(app_client.app)
    c.cookies.set("graft_session", expired)
    assert c.get("/api/cases").status_code == 401
    unexpiring = jwt.encode({"sub": uid["user_id"], "org": uid["org_id"]}, get_settings().SESSION_SECRET,
                            algorithm="HS256")
    c.cookies.set("graft_session", unexpiring)
    assert c.get("/api/cases").status_code == 401  # tokens without exp are refused
