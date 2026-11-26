from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Membership, Org, User
from ..schemas.requests import DemoLogin
from ..services import audit
from ..services.org_settings import get_org_settings
from ..services.serialize import org_out
from ..services.tenancy import SESSION_COOKIE, Ctx, encode_session, get_ctx

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/demo-accounts")
def demo_accounts(db: Session = Depends(get_db)):
    if not get_settings().DEMO_MODE:
        raise HTTPException(404, "Not found")
    rows = db.execute(
        select(Membership, User, Org).join(User, User.id == Membership.user_id).join(Org, Org.id == Membership.org_id)
        .where(Org.is_demo.is_(True)).order_by(Org.created_at, Membership.created_at)
    ).all()
    return [{"user_id": u.id, "name": u.name, "title": u.title, "role": m.role, "org_id": o.id, "org_name": o.name}
            for m, u, o in rows]


@router.post("/demo-login")
def demo_login(body: DemoLogin, response: Response, db: Session = Depends(get_db)):
    if not get_settings().DEMO_MODE or get_settings().AUTH_MODE != "demo":
        raise HTTPException(404, "Not found")
    m = db.execute(
        select(Membership).join(Org, Org.id == Membership.org_id)
        .where(Membership.user_id == body.user_id, Org.is_demo.is_(True)).order_by(Membership.created_at)
    ).scalars().first()
    if m is None:
        raise HTTPException(404, "Unknown demo account")
    audit.record(db, org_id=m.org_id, actor_user_id=m.user_id, entity="session", entity_id=m.user_id,
                 action="demo_login")
    db.commit()
    response.set_cookie(SESSION_COOKIE, encode_session(m.user_id, m.org_id), httponly=True, samesite="lax",
                        secure=False, max_age=60 * 60 * 12, path="/")
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return {
        "user": {"id": ctx.user.id, "name": ctx.user.name, "title": ctx.user.title, "role": ctx.role},
        "org": org_out(ctx.org, get_org_settings(db, ctx.org_id)),
        "role": ctx.role,
        "auth_mode": get_settings().AUTH_MODE,
        "demo_mode": get_settings().DEMO_MODE,
    }
