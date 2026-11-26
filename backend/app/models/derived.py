"""Derived data: recomputable from evidence. Holds no human state."""
from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ._base import CreatedMixin, IdMixin, org_fk


class AnalysisRun(IdMixin, CreatedMixin, Base):
    """One extraction attempt for one source version."""

    __tablename__ = "analysis_runs"
    org_id: Mapped[str] = org_fk()
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    body_sha256: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))  # live | cached | replay | unavailable
    status: Mapped[str] = mapped_column(String(20))  # ok | partial | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Claim(IdMixin, CreatedMixin, Base):
    __tablename__ = "claims"
    org_id: Mapped[str] = org_fk()
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("analysis_runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    scope: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(50))
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    quote: Mapped[str] = mapped_column(Text)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)


class RejectedCandidate(IdMixin, CreatedMixin, Base):
    __tablename__ = "rejected_candidates"
    org_id: Mapped[str] = org_fk()
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("analysis_runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(32), ForeignKey("sources.id"), index=True)
    raw: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)


class Finding(CreatedMixin, Base):
    """Recomputed by services/rules.py. The id is a stable hash of (case, rule, evidence) so a task can keep
    pointing at the same finding across re-analysis."""

    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = org_fk()
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(50))
    rule_version: Mapped[str] = mapped_column(String(10))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
