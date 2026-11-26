"""Cases and evidence. Sources are immutable: a correction or re-link is a new version row."""
import datetime as dt

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk

ACCESS_STATES = ("requested", "awaiting_approval", "approved", "not_provisioned", "active", "confirmed_usable")


class EmployeeCase(IdMixin, CreatedMixin, Base):
    """One onboarding / reallocation. Tracker fields are one report among others and stay NULL when missing.
    `stage` is not stored: it is derived from the latest technical review."""

    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("org_id", "ref"),)
    org_id: Mapped[str] = org_fk()
    ref: Mapped[str] = mapped_column(String(30))
    employee: Mapped[str] = mapped_column(String(200))
    employee_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    movement: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("projects.id"), nullable=True)
    manager_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    line_manager_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    tracker_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracker_updated_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    tech_owner_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    # Not in the starter-pack tracker: set by a coordinator. NULL until someone records it.
    expected_readiness_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    exact_role: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Source(IdMixin, CreatedMixin, Base):
    __tablename__ = "sources"
    org_id: Mapped[str] = org_fk()
    ref: Mapped[str | None] = mapped_column(String(30), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # email | update | tracker_note | tracker_row
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    case_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("cases.id"), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("projects.id"), nullable=True)
    author_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recipient_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    header: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    body_sha256: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("sources.id"), nullable=True)
    ingested_via: Mapped[str] = mapped_column(String(20))  # seed | paste | upload | webhook
    created_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)


class AccessItem(IdMixin, CreatedMixin, Base):
    __tablename__ = "access_items"
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    system: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(30))
    requested_at: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    owner_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_follow_up: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    evidence_source_ids: Mapped[list] = mapped_column(JSON, default=list)


class KnowledgeRef(IdMixin, CreatedMixin, Base):
    """A reference to a project-owned location. Never a copied document."""

    __tablename__ = "knowledge_refs"
    org_id: Mapped[str] = org_fk()
    project_id: Mapped[str] = mapped_column(String(32), ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(Text)
    owner_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_verified: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("sources.id"), nullable=True)
