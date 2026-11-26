from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import client
from ..ai.pipeline import analyze_source
from ..ai.versions import SUGGEST_PROMPT_VERSION
from ..config import get_settings
from ..db import get_db
from ..models import Finding
from ..services import audit
from ..services.cases import case_detail, case_rows, load_case
from ..services.evidence import current_claims, latest_sources
from ..services.org_settings import get_org_settings
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, require_roles

router = APIRouter(prefix="/cases", tags=["cases"])
COORD = ("admin", "pmo_coordinator")


@router.get("")
def list_cases(view: str = "needs_attention", q: str | None = None, ctx: Ctx = Depends(get_ctx),
               db: Session = Depends(get_db)):
    if view not in ("needs_attention", "mine", "stale", "access_blocked", "all"):
        raise HTTPException(422, "Unknown view")
    return case_rows(db, ctx, view, q)


@router.get("/{case_id}")
def get_case(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return case_detail(db, ctx, load_case(db, ctx, case_id))


@router.post("/{case_id}/analyze")
def analyze(case_id: str, ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    """Writes analysis tables and recomputed findings only. Tasks and reviews are untouched."""
    case = load_case(db, ctx, case_id)
    settings = get_org_settings(db, ctx.org_id)
    outcomes = []
    for s in latest_sources(db, ctx.org_id, case_id=case.id):
        o = analyze_source(db, s, ai_enabled=bool(settings["ai_enabled"]))
        outcomes.append({"source_id": s.id, "ref": s.ref, "mode": o.served_mode, "note": o.note,
                         "status": o.run.status if o.run else None})
    recompute_case(db, case)
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case", entity_id=case.id,
                 action="analyzed", after={"outcomes": outcomes})
    db.commit()
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
    except client.AIUnavailable as e:
        raise HTTPException(503, f"AI suggestion unavailable ({e}). Write the task manually.")
    known = {c.id for c in claims}
    draft["cited_claim_ids"] = [i for i in draft.get("cited_claim_ids", []) if i in known]
    by_id = {c.id: c for c in claims}
    draft["cited_source_ids"] = list(dict.fromkeys(by_id[i].source_id for i in draft["cited_claim_ids"]))
    return {**draft, "mode": "live", "model": get_settings().LLM_MODEL, "prompt_version": SUGGEST_PROMPT_VERSION}
