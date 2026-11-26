"""Evidence intake and background processing: service identities for trusted relays, durable analysis jobs."""
import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk


class ServiceCredential(IdMixin, CreatedMixin, Base):
    """A scoped service identity (e.g. a mail or ITSM relay) bound to one org. Only the SHA-256 of the token is
    stored; the token is shown once when an operator creates it (python -m app.ops service-token)."""

    __tablename__ = "service_credentials"
    org_id: Mapped[str] = org_fk()
    name: Mapped[str] = mapped_column(String(100))
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["inbound:write"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalysisJob(IdMixin, CreatedMixin, Base):
    """One extraction to run for one source version. Durable: survives restarts; a crashed worker's lease
    expires and the job is retried. At most one queued/running job per source version (partial unique index).

    status: queued | running | done | waiting | failed | superseded
      waiting    the model is unavailable and no verified cache applies; retried when it returns
      superseded the source got a newer version before the job ran; nothing derived is written"""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("uq_analysis_job_active", "source_id", unique=True,
              sqlite_where=text("status in ('queued','running','waiting')"),
              postgresql_where=text("status in ('queued','running','waiting')")),
        Index("ix_analysis_job_ready", "status", "run_after"),
    )
    org_id: Mapped[str] = org_fk()
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    case_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("cases.id"), nullable=True, index=True)
    body_sha256: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(40))  # ingested | linked | manual | submitted | inbound
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    run_after: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    outcome_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    analysis_run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("analysis_runs.id"), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
