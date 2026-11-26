"""Tenancy and directory: Org, User, Membership, Project, Setting, AuditEvent, Notification."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..services.roles import DEFAULT_REQUIRED_RESPONSIBILITIES, ROLE_CODES
from ._base import CreatedMixin, IdMixin, org_fk, utcnow

ROLES = ROLE_CODES
MEMBERSHIP_STATUSES = ("invited", "active", "suspended")

DEFAULT_SETTINGS = {
    "stale_days": 7,
    "unanswered_working_days": 3,
    "as_of_date": "2026-10-14",
    "ai_enabled": True,
    "default_sla_hours": 48,
    # Raise MISSING_READINESS_DATE when no expected readiness date is recorded. Off until the Business Owner confirms it.
    "flag_missing_readiness_date": False,
    # Team decisions where the PMO interview was silent (docs/business-rules.md, "Team defaults").
    "required_responsibilities": DEFAULT_REQUIRED_RESPONSIBILITIES,
    "project_manager_can_assign": True,
    # employee: only the employee's own test confirms access (starter pack). designated: a named tester per system.
    "access_tester_policy": "employee",
    # Display titles per canonical role code. Display only: never changes permissions.
    "role_labels": {},
    # Clock and calendar. "as_of" keeps the demo deterministic; private orgs are created with "real".
    "clock_mode": "as_of",
    "timezone": "Europe/Tirane",
    "working_hours": {"start": "09:00", "end": "17:00", "days": [0, 1, 2, 3, 4]},
    "holidays": [],
    # Overdue obligations: remind the owner when overdue, escalate to coordinators after N working days overdue.
    "escalation_working_days": 2,
    # Final sign-off exceptions (bypassing unmet milestones/blocking access with a reason). Off unless the org
    # documents and approves such a policy; hard criteria (rationale, citations) can never be bypassed.
    "allow_closure_exceptions": False,
}


class Org(IdMixin, CreatedMixin, Base):
    __tablename__ = "orgs"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class User(IdMixin, CreatedMixin, Base):
    """A person. Production identities come from OIDC SSO and have no password. Only the fictional accounts of demo
    organisations carry a password hash (salted scrypt, services/passwords.py)."""

    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Membership(IdMixin, CreatedMixin, Base):
    """Organisation membership only. Roles are granted separately (RoleAssignment), so one person can hold
    several roles at different scopes."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    org_id: Mapped[str] = org_fk()
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="active")  # invited | active | suspended
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(IdMixin, CreatedMixin, Base):
    __tablename__ = "projects"
    org_id: Mapped[str] = org_fk()
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Setting(IdMixin, Base):
    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("org_id", "key"),)
    org_id: Mapped[str] = org_fk()
    key: Mapped[str] = mapped_column(String(60))
    value: Mapped[object] = mapped_column(JSON)


class AuditEvent(IdMixin, CreatedMixin, Base):
    __tablename__ = "audit_events"
    org_id: Mapped[str] = org_fk()
    actor_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[object | None] = mapped_column(JSON, nullable=True)
    after: Mapped[object | None] = mapped_column(JSON, nullable=True)


class Notification(IdMixin, CreatedMixin, Base):
    __tablename__ = "notifications"
    org_id: Mapped[str] = org_fk()
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class UserIdentity(IdMixin, CreatedMixin, Base):
    """An external identity (OIDC issuer + subject) linked to a Graft user. SSO users never have a password."""

    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    issuer: Mapped[str] = mapped_column(String(300))
    subject: Mapped[str] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
