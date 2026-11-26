"""Extraction pipeline: verified local cache -> live Ollama call -> recorded example -> unavailable (or deferred).

Cache identity: (source version, body hash, prompt version, schema version, provider, model tag, model digest).
During a model outage only a current *local* verified cache (provider ollama) or an eligible recorded example is
served; historic Groq runs stay viewable as history but are never served as a fallback.

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
from .versions import PROMPT_VERSION, REPLAY_MODEL, REPLAY_PROMPT_VERSION, REPLAY_SCHEMA_VERSION, SCHEMA_VERSION

REPLAY_DIR = Path(__file__).resolve().parent / "cache" / "replay"


@dataclass
class Outcome:
    run: AnalysisRun | None
    served_mode: str  # live | cached | replay | unavailable | skipped
    note: str | None = None


def _replay_fixture(source: Source) -> dict | None:
    path = REPLAY_DIR / f"{source.ref}.json" if source.ref else None
    if path is None or not path.is_file():
        from .recorded import lookup  # showcase examples, matched on the exact body hash
        return lookup(source.body_sha256)
    fx = json.loads(path.read_text(encoding="utf-8"))
    # A recorded example only applies to the exact body it was recorded for.
    if fx.get("body_sha256") != source.body_sha256:
        return None
    return fx["response"]


def _successful_run(db: Session, source: Source, model: str | None, *, digest: str | None = None,
                    providers: tuple[str, ...] = (client.PROVIDER, "recorded"),
                    current_versions: bool = False) -> AnalysisRun | None:
    q = select(AnalysisRun).where(
        AnalysisRun.source_id == source.id,
        AnalysisRun.body_sha256 == source.body_sha256,
        AnalysisRun.status.in_(("ok", "partial")),
        AnalysisRun.provider.in_(providers),
    )
    if current_versions:  # the live cache: identical prompt and schema only
        q = q.where(AnalysisRun.prompt_version == PROMPT_VERSION, AnalysisRun.schema_version == SCHEMA_VERSION)
    if model is not None:
        q = q.where(AnalysisRun.model == model)
    if digest is not None:
        q = q.where(AnalysisRun.model_digest == digest)
    return db.execute(q.order_by(AnalysisRun.created_at.desc()).limit(1)).scalar_one_or_none()


def _store(db: Session, source: Source, *, model: str, mode: str, response: object, provider: str,
           digest: str | None = None, versions: tuple[str, str] = (PROMPT_VERSION, SCHEMA_VERSION)) -> AnalysisRun:
    label = source.ref or "source"
    v = verify(source.body, response, label)
    run = AnalysisRun(
        org_id=source.org_id,
        source_id=source.id,
        body_sha256=source.body_sha256,
        prompt_version=versions[0],
        schema_version=versions[1],
        model=model,
        provider=provider,
        model_digest=digest,
        mode=mode,
        status=v.status,
        error=v.error,
        # Raw model output is kept only when debug capture is explicitly on (and always for recorded examples,
        # which are committed fictional fixtures). Verified claims and rejections carry what the UI needs.
        raw_response=response if isinstance(response, dict) and (provider == "recorded" or
                                                                   get_settings().AI_DEBUG_CAPTURE) else None,
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


def analyze_source(db: Session, source: Source, *, ai_enabled: bool, allow_live: bool = True,
                   defer_when_unavailable: bool = False) -> Outcome:
    """defer_when_unavailable (background jobs): if the model is down or busy and neither a local verified cache nor
    a recorded example applies, return served_mode "deferred" without recording anything, so the job can retry."""
    model = get_settings().LLM_MODEL
    note = None
    if ai_enabled and allow_live and client.is_configured():
        digest = client.model_digest()
        if digest is not None:
            existing = _successful_run(db, source, model, digest=digest, providers=(client.PROVIDER,),
                                       current_versions=True)
            if existing is not None:
                # Identical input already extracted by the same pinned model: reuse, never duplicate.
                return Outcome(existing, "cached")
            try:
                response = client.extract(_payload(source))
                run = _store(db, source, model=model, mode="live", response=response, provider=client.PROVIDER,
                             digest=digest)
                if run.status != "failed":
                    return Outcome(run, "live")
                return Outcome(run, "live", run.error)
            except client.AIUnavailable as e:
                note = str(e)
        else:
            note = client.status().get("detail") or "model unavailable"
    elif not ai_enabled:
        note = "AI disabled for this organisation"
    elif allow_live:
        note = client.configuration_error()

    cached = _successful_run(db, source, None)
    if cached is not None:
        return Outcome(cached, "cached" if cached.mode != "replay" else "replay", note)

    fixture = _replay_fixture(source)
    if fixture is not None:
        run = _store(db, source, model=REPLAY_MODEL, mode="replay", response=fixture, provider="recorded",
                     versions=(REPLAY_PROMPT_VERSION, REPLAY_SCHEMA_VERSION))
        return Outcome(run, "replay", note)

    if not allow_live:
        return Outcome(None, "skipped")
    if defer_when_unavailable and ai_enabled and client.is_configured():
        return Outcome(None, "deferred", note)
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
            prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, model=model, provider=client.PROVIDER,
            mode="unavailable", status="failed", error=note,
        )
        db.add(failed)
        db.flush()
    else:
        failed.error = note
    return Outcome(failed, "unavailable", note)
