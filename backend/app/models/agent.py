"""Case investigations and draft actions. A proposal is never an authoritative review."""
from datetime import date

from sqlalchemy import JSON, CheckConstraint, Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk


class AgentRun(IdMixin, CreatedMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("status in ('running','completed','failed','unavailable')", name="ck_agent_run_status"),
        Index("uq_agent_active_case", "org_id", "case_id", unique=True,
              sqlite_where=text("status = 'running'"), postgresql_where=text("status = 'running'")),
        Index("ix_agent_case_history", "org_id", "case_id", "created_at"),
    )

    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))
    requested_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20))
    assessment: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(20), default="ollama")
    model_digest: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AgentStep(IdMixin, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("run_id", "index", name="uq_agent_step_index"),)

    org_id: Mapped[str] = org_fk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    index: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict] = mapped_column(JSON)
    result_summary: Mapped[str] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)


class AgentProposal(IdMixin, CreatedMixin, Base):
    __tablename__ = "agent_proposals"
    __table_args__ = (
        CheckConstraint("status in ('open','accepted','dismissed')", name="ck_agent_proposal_status"),
        CheckConstraint("kind in ('task','message','access_followup')", name="ck_agent_proposal_kind"),
    )

    org_id: Mapped[str] = org_fk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    owner_role: Mapped[str | None] = mapped_column(String(50))
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    cited_source_ids: Mapped[list[str]] = mapped_column(JSON)
    cited_claim_ids: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="open")
    dismiss_reason: Mapped[str | None] = mapped_column(Text)
