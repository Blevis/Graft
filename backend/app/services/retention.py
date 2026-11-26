"""Retention: what Graft keeps, for how long, and what becomes eligible for deletion. Dry run by default.

Canonical records (sources, reviews, tasks, training entries, responsibilities, audit events) are kept: they are
the evidence and decision record. Copies and operational byproducts are minimised:

  raw model output on analysis runs          cleared (kept only for committed fictional recorded examples)
  agent tool-step traces                     deleted after `agent_trace_days`; runs, assessments and decisions kept
  finished analysis jobs                     deleted after `job_days`
  read notifications                         deleted after `notification_days`
  unmatched sources nobody linked            eligible after `unmatched_source_days`, unless any review or task
                                             cites them (legal hold); their derived runs/claims go with them

Org setting `retention` overrides the defaults below."""
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..models import (
    AgentRun, AgentStep, AnalysisJob, AnalysisRun, Claim, Notification, RejectedCandidate, Review, Source, Task,
)
from ..models._base import utcnow
from . import audit
from .org_settings import get_org_settings

DEFAULTS = {"agent_trace_days": 180, "job_days": 30, "notification_days": 90, "unmatched_source_days": 365}


def policy(db: Session, org_id: str) -> dict:
    return {**DEFAULTS, **(get_org_settings(db, org_id).get("retention") or {})}


def apply_retention(db: Session, org_id: str, *, apply: bool = False) -> dict:
    p = policy(db, org_id)
    now = utcnow()
    report: dict = {"policy": p, "applied": apply}

    raw = select(AnalysisRun.id).where(AnalysisRun.org_id == org_id, AnalysisRun.raw_response.is_not(None),
                                       AnalysisRun.provider != "recorded")
    report["raw_model_outputs"] = len(db.execute(raw).all())

    old_runs = select(AgentRun.id).where(AgentRun.org_id == org_id,
                                         AgentRun.created_at < now - timedelta(days=p["agent_trace_days"]))
    report["agent_steps"] = len(db.execute(select(AgentStep.id).where(AgentStep.run_id.in_(old_runs))).all())

    jobs = select(AnalysisJob.id).where(AnalysisJob.org_id == org_id,
                                        AnalysisJob.status.in_(("done", "superseded", "failed")),
                                        AnalysisJob.created_at < now - timedelta(days=p["job_days"]))
    report["analysis_jobs"] = len(db.execute(jobs).all())

    notes = select(Notification.id).where(Notification.org_id == org_id, Notification.read.is_(True),
                                          Notification.created_at < now - timedelta(days=p["notification_days"]))
    report["notifications"] = len(db.execute(notes).all())

    held: set[str] = set()
    for ids in db.execute(select(Review.cited_source_ids).where(Review.org_id == org_id)).scalars():
        held |= set(ids or [])
    for ids in db.execute(select(Task.cited_source_ids).where(Task.org_id == org_id)).scalars():
        held |= set(ids or [])
    superseded = select(Source.supersedes_id).where(Source.supersedes_id.is_not(None))
    candidates = db.execute(select(Source).where(
        Source.org_id == org_id, Source.case_id.is_(None), Source.project_id.is_(None),
        Source.id.not_in(superseded),
        Source.created_at < now - timedelta(days=p["unmatched_source_days"]))).scalars().all()
    eligible = [s for s in candidates if s.id not in held]
    report["unmatched_sources"] = {"eligible": len(eligible), "held_by_citation": len(candidates) - len(eligible)}

    if apply:
        db.execute(update(AnalysisRun).where(AnalysisRun.id.in_(raw)).values(raw_response=None)
                   .execution_options(synchronize_session=False))
        db.execute(delete(AgentStep).where(AgentStep.run_id.in_(old_runs)).execution_options(synchronize_session=False))
        db.execute(delete(AnalysisJob).where(AnalysisJob.id.in_(jobs)).execution_options(synchronize_session=False))
        db.execute(delete(Notification).where(Notification.id.in_(notes))
                   .execution_options(synchronize_session=False))
        for s in eligible:
            run_ids = select(AnalysisRun.id).where(AnalysisRun.source_id == s.id)
            db.execute(delete(Claim).where(Claim.run_id.in_(run_ids)).execution_options(synchronize_session=False))
            db.execute(delete(RejectedCandidate).where(RejectedCandidate.run_id.in_(run_ids))
                       .execution_options(synchronize_session=False))
            db.execute(delete(AnalysisJob).where(AnalysisJob.source_id == s.id)
                       .execution_options(synchronize_session=False))
            db.execute(delete(AnalysisRun).where(AnalysisRun.source_id == s.id)
                       .execution_options(synchronize_session=False))
            db.delete(s)
        audit.record(db, org_id=org_id, actor_user_id=None, entity="retention", entity_id=org_id, action="applied",
                     after={k: v for k, v in report.items() if k != "policy"})
        db.flush()
    return report
