"""Request context and tenant-scoped data access. Every read/write of a tenant table goes through these helpers."""
from dataclasses import dataclass
from typing import TypeVar

import jwt
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Membership, Org, RoleAssignment, User, UserPreference
from .org_settings import as_of, get_org_settings
from .roles import canonical, primary_role

SESSION_COOKIE = "graft_session"
T = TypeVar("T")


@dataclass(frozen=True)
class Grant:
    id: str
    role: str
    scope_type: str  # organization | project | case
    scope_id: str | None
    default_for_cases: bool = False


@dataclass(frozen=True)
class Ctx:
    """The request's authorization context, resolved from the session cookie and the database only.
    `working_role` is a presentation preference: it never widens or narrows what the user may do."""

    user: User
    org: Org
    grants: tuple[Grant, ...] = ()
    membership_id: str | None = None
    working_role: str | None = None

    @property
    def org_id(self) -> str:
        return self.org.id

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def org_roles(self) -> frozenset[str]:
        return frozenset(g.role for g in self.grants if g.scope_type == "organization")

    @property
    def roles(self) -> frozenset[str]:
        return frozenset(g.role for g in self.grants)

    @property
    def role(self) -> str:
        """One display role (highest priority). Never use this for an authorization decision."""
        return primary_role(self.roles) or "project_member"

    def project_ids(self, *roles: str) -> frozenset[str]:
        return frozenset(g.scope_id for g in self.grants
                         if g.scope_type == "project" and g.scope_id and (not roles or g.role in roles))

    def case_grant_ids(self, *roles: str) -> frozenset[str]:
        return frozenset(g.scope_id for g in self.grants
                         if g.scope_type == "case" and g.scope_id and (not roles or g.role in roles))


CSRF_COOKIE = "graft_csrf"


def encode_session(user_id: str, org_id: str) -> str:
    """Expiring session (SESSION_HOURS). Membership status and grants are re-checked on every request, so a
    deactivated member loses access immediately, not at expiry."""
    import time

    now = int(time.time())
    return jwt.encode({"sub": user_id, "org": org_id, "iat": now,
                       "exp": now + int(get_settings().SESSION_HOURS * 3600)},
                      get_settings().SESSION_SECRET, algorithm="HS256")


def load_ctx(db: Session, user_id: str | None, org_id: str | None) -> Ctx:
    """Resolve membership, active grants and presentation context. Inactive memberships cannot act."""
    row = db.execute(
        select(Membership, User, Org)
        .join(User, User.id == Membership.user_id)
        .join(Org, Org.id == Membership.org_id)
        .where(Membership.user_id == user_id, Membership.org_id == org_id)
    ).first()
    if row is None:
        raise HTTPException(401, "No membership for this session")
    membership, user, org = row
    if membership.status != "active":
        raise HTTPException(401, "This membership is not active")
    today = as_of(get_org_settings(db, org.id))
    grants = tuple(
        Grant(id=g.id, role=g.role_code, scope_type=g.scope_type, scope_id=g.scope_id,
              default_for_cases=g.default_for_cases)
        for g in db.execute(select(RoleAssignment).where(
            RoleAssignment.org_id == org.id, RoleAssignment.user_id == user.id, RoleAssignment.is_active.is_(True),
        ).order_by(RoleAssignment.created_at)).scalars()
        if (g.valid_from is None or g.valid_from <= today) and (g.valid_until is None or today <= g.valid_until)
    )
    pref = db.execute(select(UserPreference).where(UserPreference.org_id == org.id,
                                                  UserPreference.user_id == user.id)).scalar_one_or_none()
    working = (pref.value or {}).get("working_role") if pref else None
    if working not in {g.role for g in grants}:
        working = None
    return Ctx(user=user, org=org, grants=grants, membership_id=membership.id, working_role=working)


def get_ctx(
    db: Session = Depends(get_db), graft_session: str | None = Cookie(default=None)
) -> Ctx:
    """Roles come from server-side grants, never from the request body."""
    if not graft_session:
        raise HTTPException(401, "Not signed in")
    try:
        claims = jwt.decode(graft_session, get_settings().SESSION_SECRET, algorithms=["HS256"],
                            options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid session")
    return load_ctx(db, claims.get("sub"), claims.get("org"))


def require_roles(*roles: str):
    """Dependency: the caller must hold one of these roles at organisation scope."""
    wanted = {canonical(r) for r in roles}

    def dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if not ctx.org_roles & wanted:
            raise HTTPException(403, "Requires role: " + ", ".join(sorted(wanted)))
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
