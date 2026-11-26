"""Extraction pipeline: live call -> verified cache -> recorded example -> unavailable.

This module writes ONLY derived tables (analysis_runs, claims, rejected_candidates).
It has no import path to task or review writers."""
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AnalysisRun, Claim, RejectedCandidate, Source
from . import client
from .verifier import verify
from .versions import PROMPT_VERSION, REPLAY_MODEL, SCHEMA_VERSION

REPLAY_DIR = Path(__file__).resolve().parent / "cache" / "replay"


@dataclass
class Outcome:
    run: AnalysisRun | None
    served_mode: str  # live | cached | replay | unavailable | skipped
    note: str | None = None


def _replay_fixture(source: Source) -> dict | None:
    if not source.ref:
        return None
    path = REPLAY_DIR / f"{source.ref}.json"
    if not path.is_file():
        return None
    fx = json.loads(path.read_text(encoding="utf-8"))
    # A recorded example only applies to the exact body it was recorded for.
    if fx.get("body_sha256") != source.body_sha256:
        return None
    return fx["response"]


def _successful_run(db: Session, source: Source, model: str | None) -> AnalysisRun | None:
    q = select(AnalysisRun).where(
        AnalysisRun.source_id == source.id,
        AnalysisRun.body_sha256 == source.body_sha256,
        AnalysisRun.prompt_version == PROMPT_VERSION,
        AnalysisRun.schema_version == SCHEMA_VERSION,
        AnalysisRun.status.in_(("ok", "partial")),
    )
    if model is not None:
        q = q.where(AnalysisRun.model == model)
    return db.execute(q.order_by(AnalysisRun.created_at.desc()).limit(1)).scalar_one_or_none()


def _store(db: Session, source: Source, *, model: str, mode: str, response: object) -> AnalysisRun:
    label = source.ref or "source"
    v = verify(source.body, response, label)
    run = AnalysisRun(
        org_id=source.org_id,
        source_id=source.id,
        body_sha256=source.body_sha256,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        model=model,
        mode=mode,
        status=v.status,
        error=v.error,
        raw_response=response if isinstance(response, dict) else None,
    )
    db.add(run)
    db.flush()
    for c in v.accepted:
        db.add(Claim(org_id=source.org_id, run_id=run.id, source_id=source.id, **c))
    for r in v.rejected:
        db.add(RejectedCandidate(org_id=source.org_id, run_id=run.id, source_id=source.id, **r))
    # The session does not autoflush: flush so the rules that run next see these claims.
    db.flush()
    return run


def _payload(source: Source) -> dict:
    return {
        "source_id": source.ref or source.id,
        "case_id": source.case_id,
        "source_type": source.kind,
        "author_role": source.author_role,
        "source_date": source.date.isoformat() if source.date else None,
        "original_body": source.body,
    }


def analyze_source(db: Session, source: Source, *, ai_enabled: bool, allow_live: bool = True) -> Outcome:
    model = get_settings().LLM_MODEL

    if ai_enabled and allow_live and client.is_configured():
        existing = _successful_run(db, source, model)
        if existing is not None:
            # Identical input already extracted: reuse, never duplicate.
            return Outcome(existing, "cached")
        try:
            response = client.extract(_payload(source))
            run = _store(db, source, model=model, mode="live", response=response)
            if run.status != "failed":
                return Outcome(run, "live")
            note = run.error
        except client.AIUnavailable as e:
            note = str(e)
    else:
        note = "AI disabled for this organisation" if not ai_enabled else (
            "GROQ_API_KEY is not set" if allow_live else None)

    cached = _successful_run(db, source, None)
    if cached is not None:
        return Outcome(cached, "cached" if cached.mode != "replay" else "replay", note)

    fixture = _replay_fixture(source)
    if fixture is not None:
        run = _store(db, source, model=REPLAY_MODEL, mode="replay", response=fixture)
        return Outcome(run, "replay", note)

    if not allow_live:
        return Outcome(None, "skipped")
    # Record the failed attempt once per input so the UI can explain it; originals stay visible.
    failed = db.execute(
        select(AnalysisRun).where(
            AnalysisRun.source_id == source.id,
            AnalysisRun.body_sha256 == source.body_sha256,
            AnalysisRun.mode == "unavailable",
        )
    ).scalar_one_or_none()
    if failed is None:
        failed = AnalysisRun(
            org_id=source.org_id, source_id=source.id, body_sha256=source.body_sha256,
            prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, model=model,
            mode="unavailable", status="failed", error=note,
        )
        db.add(failed)
        db.flush()
    else:
        failed.error = note
    return Outcome(failed, "unavailable", note)
