"""Tenancy and directory: Org, User, Membership, Project, Setting, AuditEvent, Notification."""
from sqlalchemy import JSON, Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk

ROLES = ("admin", "pmo_coordinator", "technical_owner", "line_manager", "employee", "viewer")

DEFAULT_SETTINGS = {
    "stale_days": 7,
    "unanswered_working_days": 3,
    "as_of_date": "2026-10-14",
    "ai_enabled": True,
    "default_sla_hours": 48,
}


class Org(IdMixin, CreatedMixin, Base):
    __tablename__ = "orgs"
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class User(IdMixin, CreatedMixin, Base):
    """A person. No passwords are stored: demo login now, OIDC SSO in production."""

    __tablename__ = "users"
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Membership(IdMixin, CreatedMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    org_id: Mapped[str] = org_fk()
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))


class Project(IdMixin, CreatedMixin, Base):
    __tablename__ = "projects"
    org_id: Mapped[str] = org_fk()
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tech_owner_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)


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
