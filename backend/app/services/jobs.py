"""Durable, bounded background analysis.

enqueue_analysis() records an AnalysisJob in the caller's transaction (so a crash before commit leaves nothing
half-done). A worker claims ready jobs with a lease, runs the same extraction service used everywhere else
(ai/pipeline.analyze_source), then recomputes the case's derived findings. Jobs never touch tasks or reviews.

- One active job per source version (partial unique index); repeated delivery reuses it.
- A job whose source got a newer version (relink, correction) is marked superseded at run time.
- Model unavailable and no verified cache / recorded example: the job waits and retries without spending an
  attempt, so processing resumes by itself when the model returns. Invalid model output spends an attempt.
- A crashed worker's lease expires; the job is picked up again.

ANALYSIS_WORKER: thread (default: a daemon thread in the web process), external (python -m app.worker),
inline (process right after the request commits; used by the test suite and the CLI)."""
import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AnalysisJob, EmployeeCase, Source
from .org_settings import get_org_settings

log = logging.getLogger(__name__)
LEASE_SECONDS = 120
WAIT_BACKOFF = (30, 60, 120, 300, 600)
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


def is_current(db: Session, source: Source) -> bool:
    return db.execute(select(Source.id).where(Source.supersedes_id == source.id)).first() is None


def enqueue_analysis(db: Session, source: Source, *, reason: str, user_id: str | None = None) -> AnalysisJob | None:
    """Idempotent: returns the existing active job for this source version if there is one."""
    if source.case_id is None:
        return None  # unmatched evidence is analysed once a person links it to a case
    existing = db.execute(select(AnalysisJob).where(
        AnalysisJob.source_id == source.id, AnalysisJob.status.in_(("queued", "running", "waiting")))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    # A concurrent enqueue of the same version violates the partial unique index; the request then fails as a
    # whole and its retry finds the existing job above.
    job = AnalysisJob(org_id=source.org_id, source_id=source.id, case_id=source.case_id,
                      body_sha256=source.body_sha256, reason=reason, status="queued", run_after=_now(),
                      requested_by_user_id=user_id)
    db.add(job)
    db.flush()
    return job


def _claim(db: Session, job_id: str | None = None) -> AnalysisJob | None:
    now = _now()
    q = select(AnalysisJob.id).where(
        or_(AnalysisJob.status.in_(("queued", "waiting")) & (AnalysisJob.run_after <= now),
            (AnalysisJob.status == "running") & (AnalysisJob.lease_until < now)))
    if job_id:
        q = q.where(AnalysisJob.id == job_id)
    for jid in db.execute(q.order_by(AnalysisJob.run_after).limit(5)).scalars().all():
        claimed = db.execute(update(AnalysisJob).where(
            AnalysisJob.id == jid,
            or_(AnalysisJob.status.in_(("queued", "waiting")),
                (AnalysisJob.status == "running") & (AnalysisJob.lease_until < now)))
            .values(status="running", worker=WORKER_ID, lease_until=now + timedelta(seconds=LEASE_SECONDS))
            .execution_options(synchronize_session=False))
        db.commit()
        if claimed.rowcount:
            job = db.get(AnalysisJob, jid)
            db.refresh(job)
            return job
    return None


def process(db: Session, job: AnalysisJob) -> AnalysisJob:
    """Run one claimed job. Writes derived tables only (via the pipeline and the rules)."""
    from ..ai.pipeline import analyze_source  # deferred: keeps this module importable without the AI client
    from .rules import recompute_case

    source = db.get(Source, job.source_id)
    if source is None or source.body_sha256 != job.body_sha256 or not is_current(db, source):
        job.status, job.finished_at, job.last_error = "superseded", _now(), "A newer source version exists"
        job.lease_until = None
        db.commit()
        return job
    settings = get_org_settings(db, job.org_id)
    try:
        outcome = analyze_source(db, source, ai_enabled=bool(settings["ai_enabled"]), defer_when_unavailable=True)
    except Exception as e:  # noqa: BLE001 - a bad job must not stop the worker
        db.rollback()
        log.exception("analysis job %s failed", job.id)
        job = db.get(AnalysisJob, job.id)
        job.attempts += 1
        job.last_error = f"{type(e).__name__}: {e}"[:500]
        job.status = "failed" if job.attempts >= job.max_attempts else "queued"
        job.run_after = _now() + timedelta(seconds=30 * job.attempts)
        job.lease_until = None
        db.commit()
        return job
    if outcome.served_mode == "deferred":
        # Attempts are not spent while the model is unavailable; back off and retry until it returns.
        waited = (_now() - _aware(job.created_at)).total_seconds()
        step = next((i for i, s in enumerate(WAIT_BACKOFF) if waited < s * 4), len(WAIT_BACKOFF) - 1)
        job.status, job.last_error = "waiting", outcome.note
        job.run_after, job.lease_until = _now() + timedelta(seconds=WAIT_BACKOFF[step]), None
        db.commit()
        return job
    if outcome.served_mode == "live" and outcome.run is not None and outcome.run.status == "failed":
        job.attempts += 1
        if job.attempts < job.max_attempts:
            job.status, job.run_after = "queued", _now() + timedelta(seconds=30 * job.attempts)
            job.last_error, job.lease_until = outcome.note or outcome.run.error, None
            db.commit()
            return job
    # Late completion is harmless: the run is bound to this exact source version and body hash, and findings use
    # current versions only. Re-check before recomputing so a relink that happened meanwhile wins.
    job.status = "done" if outcome.served_mode != "unavailable" else "failed"
    job.outcome_mode = outcome.served_mode
    job.analysis_run_id = outcome.run.id if outcome.run else None
    job.last_error = outcome.note
    job.finished_at, job.lease_until = _now(), None
    if source.case_id and is_current(db, source):
        case = db.get(EmployeeCase, source.case_id)
        if case is not None:
            recompute_case(db, case)
    db.commit()
    return job


def run_once(db: Session, limit: int = 10) -> int:
    n = 0
    while n < limit:
        job = _claim(db)
        if job is None:
            break
        process(db, job)
        n += 1
    return n


def run_jobs(db: Session, jobs: list[AnalysisJob | None]) -> list[AnalysisJob]:
    """Process specific jobs now (inline mode, CLI, tests)."""
    out = []
    for j in jobs:
        if j is None:
            continue
        claimed = _claim(db, j.id)
        out.append(process(db, claimed) if claimed else db.get(AnalysisJob, j.id))
    return out


from .job_status import case_status  # noqa: E402,F401  (re-export for API callers)


def after_commit(db: Session, jobs: list[AnalysisJob | None]) -> None:
    """Called by routes after they commit: inline mode processes immediately, other modes leave it to a worker."""
    if get_settings().ANALYSIS_WORKER == "inline":
        run_jobs(db, jobs)


# ---------- worker loop ----------

_thread: threading.Thread | None = None


def worker_loop(stop: threading.Event | None = None, interval: float = 2.0) -> None:
    from ..db import SessionLocal
    from .workflow import run_reminders

    last_reminders = 0.0
    while not (stop and stop.is_set()):
        try:
            with SessionLocal() as db:
                busy = run_once(db)
                if time.monotonic() - last_reminders > 600:
                    run_reminders(db)
                    last_reminders = time.monotonic()
        except Exception:  # noqa: BLE001
            log.exception("worker iteration failed")
            busy = 0
        time.sleep(0 if busy else interval)


def start_thread() -> None:
    global _thread
    if _thread is None and get_settings().ANALYSIS_WORKER == "thread":
        _thread = threading.Thread(target=worker_loop, name="graft-worker", daemon=True)
        _thread.start()
