"""Read-only analysis job status (safe for the AI layer and the case page to import)."""
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AnalysisJob


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def case_status(db: Session, org_id: str, case_id: str) -> dict:
    rows = db.execute(select(AnalysisJob).where(AnalysisJob.org_id == org_id, AnalysisJob.case_id == case_id)
                      .order_by(AnalysisJob.created_at.desc())).scalars().all()
    latest: dict[str, AnalysisJob] = {}
    for j in rows:
        latest.setdefault(j.source_id, j)
    counts: dict[str, int] = {}
    for j in latest.values():
        counts[j.status] = counts.get(j.status, 0) + 1
    return {"counts": counts, "per_source": {sid: {"status": j.status, "attempts": j.attempts,
                                                   "outcome_mode": j.outcome_mode, "last_error": j.last_error,
                                                   "updated_at": (_aware(j.finished_at) or _aware(j.created_at)).isoformat()}
                                             for sid, j in latest.items()}}
