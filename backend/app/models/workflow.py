"""Onboarding workflow: versioned templates, per-case requirements (milestones), task assignment history.

Requirements are snapshotted from a template version when a case is created, so later template edits never change
an existing case. Whether a milestone is *satisfied* is not stored: it is derived from the technical owner's
reviews (validate_scope / reopen), so the decision record stays append-only."""
import datetime as dt

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk


class WorkflowTemplate(IdMixin, CreatedMixin, Base):
    """One version of an onboarding template. Editing creates a new version row; is_current marks the one new
    cases receive. definition = {"milestones": [{key, title, kind, applicability, evidence_expectation,
    due_offset_days, assignee_role}]}."""

    __tablename__ = "workflow_templates"
    __table_args__ = (UniqueConstraint("org_id", "key", "version"),)
    org_id: Mapped[str] = org_fk()
    key: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    movement: Mapped[str | None] = mapped_column(String(30), nullable=True)  # new_hire | reallocation | None
    definition: Mapped[dict] = mapped_column(JSON)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)


class CaseRequirement(IdMixin, CreatedMixin, Base):
    """A milestone or check a case must (required), may (optional) or need not (not_applicable) meet before final
    sign-off. kind: milestone (validated by a technical-owner review), access (all tracked systems confirmed usable
    by the tester)."""

    __tablename__ = "case_requirements"
    __table_args__ = (UniqueConstraint("case_id", "key"),)
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    key: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20), default="milestone")
    applicability: Mapped[str] = mapped_column(String(20), default="required")
    evidence_expectation: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    assignee_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    template_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("workflow_templates.id"), nullable=True)
    changed_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskAssignment(IdMixin, CreatedMixin, Base):
    """Append-only assignment history: creation, claim, reassignment, routing to a queue."""

    __tablename__ = "task_assignments"
    org_id: Mapped[str] = org_fk()
    task_id: Mapped[str] = mapped_column(String(32), ForeignKey("tasks.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))  # created | routed | claimed | reassigned | queued
    from_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    to_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    to_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    queue: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)


class TaskPause(IdMixin, Base):
    """A waiting interval on a task's SLA clock. resumed_at NULL = currently waiting."""

    __tablename__ = "task_pauses"
    org_id: Mapped[str] = org_fk()
    task_id: Mapped[str] = mapped_column(String(32), ForeignKey("tasks.id"), index=True)
    reason: Mapped[str] = mapped_column(String(300))
    paused_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    resumed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    resumed_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
