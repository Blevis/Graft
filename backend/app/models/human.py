"""Human records. Written only by their API routes (tasks.py, reviews.py). Reviews are append-only."""
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk


class Task(IdMixin, CreatedMixin, Base):
    __tablename__ = "tasks"
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    finding_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # stable finding hash, no FK
    title: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    owner_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="open")
    cited_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    origin: Mapped[str] = mapped_column(String(30), default="manual")
    created_by_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Workflow: the milestone this task serves, the shared queue it waits in while unowned, reminder state.
    requirement_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("case_requirements.id"), nullable=True)
    queue: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Review(IdMixin, CreatedMixin, Base):
    __tablename__ = "reviews"
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    disposition: Mapped[str] = mapped_column(String(20))  # keep_open | validate_scope | close
    scope: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    observed_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cited_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    task_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("tasks.id"), nullable=True)
    reviewer_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    # Sign-off record (policy v1). Reviews saved before the closure gate keep policy_version "legacy".
    milestone_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    supersedes_review_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("reviews.id"), nullable=True)
    exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    bypassed_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(10), default="v1")
    # The evidence (source version + body hash) current when the decision was recorded: drives "reassess".
    evidence_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)


class TrainingEntry(IdMixin, CreatedMixin, Base):
    """Training and KT activity: a plan item, a delivered session or an observation. Append-only.
    Completing training never sets a stage or readiness: only the technical owner's review does."""

    __tablename__ = "training_entries"
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # plan | session | observation
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str] = mapped_column(Text, default="")
    activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cited_source_ids: Mapped[list] = mapped_column(JSON, default=list)
    recorded_by_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"))
    # The responsibility the author acted in (training_responsible, technical_owner, ...), for the audit trail.
    capacity: Mapped[str] = mapped_column(String(32))
