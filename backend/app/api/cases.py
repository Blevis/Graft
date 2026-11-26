from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import client
from ..ai.versions import SUGGEST_PROMPT_VERSION
from ..config import get_settings
from ..db import get_db
from ..models import AnalysisJob, Finding
from ..schemas.requests import CasePatch
from ..services import audit
from ..services.cases import case_detail, case_rows, load_case
from ..services.evidence import current_claims, latest_sources
from ..services.jobs import after_commit, enqueue_analysis
from ..services.org_settings import get_org_settings
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, require_roles

router = APIRouter(prefix="/cases", tags=["cases"])
COORD = ("admin", "pmo_coordinator")


@router.get("")
def list_cases(view: str = "needs_attention", q: str | None = None, ctx: Ctx = Depends(get_ctx),
               db: Session = Depends(get_db)):
    if view not in ("needs_attention", "mine", "stale", "access_blocked", "missing_owner", "all"):
        raise HTTPException(422, "Unknown view")
    return case_rows(db, ctx, view, q)


@router.get("/{case_id}")
def get_case(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return case_detail(db, ctx, load_case(db, ctx, case_id))


@router.patch("/{case_id}")
def patch_case(case_id: str, body: CasePatch, ctx: Ctx = Depends(require_roles(*COORD)),
               db: Session = Depends(get_db)):
    """Coordinator-maintained fields (expected readiness date, exact role). Tracker fields stay as reported."""
    case = load_case(db, ctx, case_id)
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    if "exact_role" in changes and changes["exact_role"] is not None:
        changes["exact_role"] = changes["exact_role"].strip() or None
    before = {k: audit.snapshot(case)[k] for k in changes}
    for k, v in changes.items():
        setattr(case, k, v)
    db.flush()
    after = {k: audit.snapshot(case)[k] for k in changes}
    if before != after:
        audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case", entity_id=case.id,
                     action="updated", before=before, after=after)
        recompute_case(db, case)
    db.commit()
    return case_detail(db, ctx, case)


@router.post("/{case_id}/analyze")
def analyze(case_id: str, ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    """Queues one background analysis job per current source version (derived tables only; tasks and reviews are
    untouched). Returns the jobs' state: done at once in inline mode, queued otherwise."""
    case = load_case(db, ctx, case_id)
    sources = latest_sources(db, ctx.org_id, case_id=case.id)
    jobs = [enqueue_analysis(db, s, reason="manual", user_id=ctx.user_id) for s in sources]
    recompute_case(db, case)
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case", entity_id=case.id,
                 action="analyzed", after={"jobs": [j.id for j in jobs if j]})
    db.commit()
    after_commit(db, jobs)
    outcomes = []
    for s, j in zip(sources, jobs):
        j = db.get(AnalysisJob, j.id) if j else None
        outcomes.append({"source_id": s.id, "ref": s.ref, "job_id": j.id if j else None,
                         "mode": (j.outcome_mode or j.status) if j else "skipped",
                         "note": j.last_error if j else None, "status": j.status if j else None})
    db.expire_all()
    return {"outcomes": outcomes, "detail": case_detail(db, ctx, case)}


@router.post("/{case_id}/suggest-task")
def suggest_task(case_id: str, ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    """AI draft only. Nothing is persisted; a human edits it and saves through POST /cases/{id}/tasks."""
    case = load_case(db, ctx, case_id)
    if not get_org_settings(db, ctx.org_id)["ai_enabled"]:
        raise HTTPException(503, "AI is disabled for this organisation. Write the task manually.")
    sources = latest_sources(db, ctx.org_id, case_id=case.id)
    claims, _, _ = current_claims(db, sources)
    findings = db.execute(select(Finding).where(Finding.org_id == ctx.org_id, Finding.case_id == case.id)).scalars()
    src = {s.id: s for s in sources}
    payload = {
        "case": {"ref": case.ref, "employee": case.employee, "tracker_status": case.tracker_status},
        "flags": [{"rule_id": f.rule_id, "message": f.message, "detail": f.detail} for f in findings],
        "claims": [{"id": c.id, "scope": c.scope, "value": c.value, "quote": c.quote,
                    "source": src[c.source_id].ref, "author_role": src[c.source_id].author_role,
                    "date": src[c.source_id].date.isoformat() if src[c.source_id].date else None} for c in claims],
    }
    try:
        draft = client.suggest_task(payload)
    except client.AIBusy:
        raise HTTPException(503, "The model is busy. Try again shortly, or write the task manually.")
    except client.AIUnavailable as e:
        raise HTTPException(503, f"AI suggestion unavailable ({e}). Write the task manually.")
    known = {c.id for c in claims}
    draft["cited_claim_ids"] = [i for i in draft.get("cited_claim_ids", []) if i in known]
    by_id = {c.id: c for c in claims}
    draft["cited_source_ids"] = list(dict.fromkeys(by_id[i].source_id for i in draft["cited_claim_ids"]))
    return {**draft, "mode": "live", "model": get_settings().LLM_MODEL, "provider": client.PROVIDER,
            "model_digest": client.model_digest(), "prompt_version": SUGGEST_PROMPT_VERSION}
