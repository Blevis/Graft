from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Membership, Org, RoleAssignment, User
from ..schemas.requests import DemoLogin
from ..services import audit
from ..services.org_settings import get_org_settings
from ..services.roles import primary_role, role_labels
from ..services.serialize import Lookup, org_out
from ..services.tenancy import SESSION_COOKIE, Ctx, encode_session, get_ctx

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_https(request: Request) -> bool:
    """Behind Render's proxy uvicorn runs with --proxy-headers, so the scheme reflects X-Forwarded-Proto."""
    return request.url.scheme == "https"


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    if not get_settings().DEMO_MODE:
        raise HTTPException(404, "Not found")
    rows = db.execute(
        select(Membership, User, Org).join(User, User.id == Membership.user_id).join(Org, Org.id == Membership.org_id)
        .where(Org.is_demo.is_(True), Membership.status == "active").order_by(Org.created_at, Membership.created_at)
    ).all()
    grants: dict[tuple[str, str], set[str]] = {}
    for org_id, user_id, code in db.execute(select(RoleAssignment.org_id, RoleAssignment.user_id,
                                                   RoleAssignment.role_code).where(RoleAssignment.is_active.is_(True))):
        grants.setdefault((org_id, user_id), set()).add(code)
    out = []
    for m, u, o in rows:
        codes = grants.get((o.id, u.id), set())
        out.append({"user_id": u.id, "name": u.name, "title": u.title, "role": primary_role(codes) or "project_member",
                    "roles": sorted(codes), "org_id": o.id, "org_name": o.name})
    return out


@router.post("/demo-login")
def demo_login(body: DemoLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_settings().DEMO_MODE or get_settings().AUTH_MODE != "demo":
        raise HTTPException(404, "Not found")
    m = db.execute(
        select(Membership).join(Org, Org.id == Membership.org_id)
        .where(Membership.user_id == body.user_id, Org.is_demo.is_(True), Membership.status == "active")
        .order_by(Membership.created_at)
    ).scalars().first()
    if m is None:
        raise HTTPException(404, "Unknown demo account")
    audit.record(db, org_id=m.org_id, actor_user_id=m.user_id, entity="session", entity_id=m.user_id,
                 action="demo_login")
    db.commit()
    response.set_cookie(SESSION_COOKIE, encode_session(m.user_id, m.org_id), httponly=True, samesite="lax",
                        secure=_is_https(request), max_age=60 * 60 * 12, path="/")
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", secure=_is_https(request), httponly=True, samesite="lax")
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Who am I, which roles I hold at which scope, and my presentation context. Display data only:
    the server re-resolves every grant on each request."""
    settings = get_org_settings(db, ctx.org_id)
    lk = Lookup(db, ctx.org_id)
    labels = role_labels(settings.get("role_labels"))
    scopes = []
    for g in ctx.grants:
        name = None
        if g.scope_type == "project":
            name = (lk.project_ref(g.scope_id) or {}).get("name")
        elif g.scope_type == "case":
            from ..models import EmployeeCase
            c = db.get(EmployeeCase, g.scope_id)
            name = c.ref if c and c.org_id == ctx.org_id else None
        scopes.append({"role": g.role, "label": labels.get(g.role, g.role), "scope_type": g.scope_type,
                       "scope_id": g.scope_id, "scope_name": name, "default_for_cases": g.default_for_cases})
    return {
        "user": {"id": ctx.user.id, "name": ctx.user.name, "title": ctx.user.title, "role": ctx.role},
        "org": org_out(ctx.org, settings),
        "role": ctx.role,
        "roles": sorted(ctx.roles),
        "grants": scopes,
        "working_role": ctx.working_role,
        "role_labels": labels,
        "auth_mode": get_settings().AUTH_MODE,
        "demo_mode": get_settings().DEMO_MODE,
    }
