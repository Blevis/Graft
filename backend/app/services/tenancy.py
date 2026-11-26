"""Request context and tenant-scoped data access. Every read/write of a tenant table goes through these helpers."""
from dataclasses import dataclass
from typing import TypeVar

import jwt
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Membership, Org, User

SESSION_COOKIE = "graft_session"
T = TypeVar("T")


@dataclass(frozen=True)
class Ctx:
    user: User
    org: Org
    role: str

    @property
    def org_id(self) -> str:
        return self.org.id

    @property
    def user_id(self) -> str:
        return self.user.id


def encode_session(user_id: str, org_id: str) -> str:
    return jwt.encode({"sub": user_id, "org": org_id}, get_settings().SESSION_SECRET, algorithm="HS256")


def get_ctx(
    db: Session = Depends(get_db), graft_session: str | None = Cookie(default=None)
) -> Ctx:
    """Role comes from the server-side membership, never from the request body."""
    if not graft_session:
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(graft_session, get_settings().SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid session")
    row = db.execute(
        select(Membership, User, Org)
        .join(User, User.id == Membership.user_id)
        .join(Org, Org.id == Membership.org_id)
        .where(Membership.user_id == claims.get("sub"), Membership.org_id == claims.get("org"))
    ).first()
    if row is None:
        raise HTTPException(401, "No membership for this session")
    membership, user, org = row
    return Ctx(user=user, org=org, role=membership.role)


def require_roles(*roles: str):
    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if ctx.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return ctx

    return dep


def scoped(model, ctx: Ctx):
    """SELECT ... WHERE org_id = ctx.org_id"""
    return select(model).where(model.org_id == ctx.org_id)


def get_scoped(db: Session, model: type[T], ctx: Ctx, id_: str) -> T:
    """Fetch by id inside the caller's org. Another org's row is indistinguishable from a missing one: 404."""
    obj = db.execute(scoped(model, ctx).where(model.id == id_)).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "Not found")
    return obj
