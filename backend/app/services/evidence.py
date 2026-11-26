"""Read helpers for evidence and its current derived claims."""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.versions import PROMPT_VERSION, SCHEMA_VERSION
from ..models import AnalysisRun, Claim, RejectedCandidate, Source


def latest_sources(db: Session, org_id: str, *, case_id: str | None = None) -> list[Source]:
    """Current versions only: a source that another row supersedes is history, not current evidence."""
    superseded = select(Source.supersedes_id).where(Source.org_id == org_id, Source.supersedes_id.is_not(None))
    q = select(Source).where(Source.org_id == org_id, Source.id.not_in(superseded))
    if case_id is not None:
        q = q.where(Source.case_id == case_id)
    return list(db.execute(q.order_by(Source.date, Source.ref, Source.created_at)).scalars())


def current_run(db: Session, source: Source) -> AnalysisRun | None:
    """Latest successful run for this exact body and prompt/schema version, whatever its mode."""
    return db.execute(
        select(AnalysisRun)
        .where(
            AnalysisRun.source_id == source.id,
            AnalysisRun.body_sha256 == source.body_sha256,
            AnalysisRun.prompt_version == PROMPT_VERSION,
            AnalysisRun.schema_version == SCHEMA_VERSION,
            AnalysisRun.status.in_(("ok", "partial")),
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def latest_attempt(db: Session, source: Source) -> AnalysisRun | None:
    return db.execute(
        select(AnalysisRun).where(AnalysisRun.source_id == source.id).order_by(AnalysisRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def current_claims(db: Session, sources: Iterable[Source]) -> tuple[list[Claim], list[RejectedCandidate], dict]:
    claims: list[Claim] = []
    rejected: list[RejectedCandidate] = []
    runs: dict[str, AnalysisRun] = {}
    for s in sources:
        run = current_run(db, s)
        if run is None:
            continue
        runs[s.id] = run
        claims += db.execute(select(Claim).where(Claim.run_id == run.id).order_by(Claim.start)).scalars().all()
        rejected += db.execute(select(RejectedCandidate).where(RejectedCandidate.run_id == run.id)).scalars().all()
    return claims, rejected, runs
