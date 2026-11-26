"""Who may do what (role grants), who is accountable for what (case responsibilities), and how the AI presents
information to each person (preferences, versioned PMO guidance). Three separate concepts, three tables."""
import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk


class RoleAssignment(IdMixin, CreatedMixin, Base):
    """Grants one canonical role at one scope. Revocation is soft (is_active=false + revoked_*), so history stays.

    scope_type organization: applies throughout the org (scope_id NULL).
    scope_type project: applies to that project only. With default_for_cases=true the holder is the project
    default for the matching case responsibility; cases inherit it unless they carry a case-level override.
    scope_type case: applies to that case only."""

    __tablename__ = "role_assignments"
    org_id: Mapped[str] = org_fk()
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    role_code: Mapped[str] = mapped_column(String(32))
    scope_type: Mapped[str] = mapped_column(String(12))  # organization | project | case
    scope_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    default_for_cases: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)


class CaseResponsibility(IdMixin, Base):
    """Who is accountable for one responsibility on one employee case (a case-level assignment or override).
    Inherited project defaults are not copied here: they are resolved from project grants at read time, so a
    case override never mutates the project default or any other case."""

    __tablename__ = "case_responsibilities"
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    responsibility_type: Mapped[str] = mapped_column(String(32))
    # Optional: an access responsible may be assigned for one system only.
    access_item_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("access_items.id"), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # case_override | manual | migrated
    assigned_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)  # never sensitive HR commentary
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)


class UserPreference(IdMixin, Base):
    """Presentation preferences for one person in one org. Never consulted for authorization."""

    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)
    org_id: Mapped[str] = org_fk()
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class AIGuidanceVersion(IdMixin, CreatedMixin, Base):
    """Organisation-level PMO guidance for how the assistant presents information. Append-only: each save is a
    new version. It shapes wording and ordering only; it cannot disable citations or grant access."""

    __tablename__ = "ai_guidance_versions"
    __table_args__ = (UniqueConstraint("org_id", "version"),)
    org_id: Mapped[str] = org_fk()
    version: Mapped[int] = mapped_column(Integer)
    terminology: Mapped[str] = mapped_column(Text, default="")
    report_structure: Mapped[str] = mapped_column(Text, default="")
    escalation_summary: Mapped[str] = mapped_column(Text, default="")
    formatting: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")
    created_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
