"""Coordinator-triggered case investigations and human decisions on draft actions."""
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai import agent
from ..config import get_settings
from ..db import get_db
from ..models import AgentProposal, AgentRun, AgentStep
from ..models._base import utcnow
from ..services import audit
from ..services.cases import case_detail, load_case
from ..services.serialize import iso
from ..services.tenancy import Ctx, get_ctx, get_scoped, scoped

router = APIRouter(tags=["agents"])
logger = logging.getLogger(__name__)


class Dismiss(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=2000)


def require_coordinator(ctx: Ctx) -> None:
    if not ctx.org_roles & {"org_admin", "pmo_coordinator"}:
        raise HTTPException(403, "Only a coordinator or administrator can manage agent proposals")


def record(db, ctx, entity, row, action, before=None):
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity=entity, entity_id=row.id,
                 action=action, before=before, after=audit.snapshot(row))


def proposal_out(p):
    return {"id": p.id, "kind": p.kind, "title": p.title, "body": p.body, "owner_role": p.owner_role,
            "owner_user_id": p.owner_user_id, "due_date": iso(p.due_date), "cited_source_ids": p.cited_source_ids,
            "cited_claim_ids": p.cited_claim_ids, "status": p.status, "dismiss_reason": p.dismiss_reason}


def runs_out(db, ctx, runs):
    if not runs:
        return []
    history = {r.id: {"id": r.id, "case_id": r.case_id, "status": r.status, "assessment": r.assessment,
                      "proposals": [], "steps": [], "model": r.model, "prompt_version": r.prompt_version,
                      "created_at": iso(r.created_at)} for r in runs}
    for step in db.scalars(scoped(AgentStep, ctx).where(AgentStep.run_id.in_(history)).order_by(AgentStep.index)):
        history[step.run_id]["steps"].append({"index": step.index, "tool": step.tool, "arguments": step.arguments,
                                              "result_summary": step.result_summary, "duration_ms": step.duration_ms})
    for p in db.scalars(scoped(AgentProposal, ctx).where(AgentProposal.run_id.in_(history))
                        .order_by(AgentProposal.created_at, AgentProposal.id)):
        history[p.run_id]["proposals"].append(proposal_out(p))
    return list(history.values())


def reserve_run(db, ctx, case):
    # A committed partial unique index arbitrates across processes. A dead worker
    # loses its lease after the maximum run time plus a short persistence allowance.
    expired = db.scalars(scoped(AgentRun, ctx).where(AgentRun.case_id == case.id, AgentRun.status == "running",
                                                     AgentRun.created_at < utcnow() - timedelta(seconds=65))).all()
    for old in expired:
        before = audit.snapshot(old)
        changed = db.execute(update(AgentRun).where(AgentRun.id == old.id, AgentRun.status == "running")
                             .values(status="failed", assessment="The previous investigation timed out."))
        if changed.rowcount:
            record(db, ctx, "agent_run", old, "failed", before)
    row = AgentRun(org_id=ctx.org_id, case_id=case.id, requested_by=ctx.user_id, status="running",
                   model=get_settings().LLM_MODEL, prompt_version=agent.PROMPT_VERSION,
                   evidence_hash=agent.evidence_hash(case_detail(db, ctx, case)))
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        # Inspect the violation itself: the winner may already have finished.
        pg_constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        sqlite_conflict = (str(exc.orig) == "UNIQUE constraint failed: agent_runs.org_id, agent_runs.case_id")
        if pg_constraint == "uq_agent_active_case" or sqlite_conflict:
            raise HTTPException(409, "An investigation is already running on this case") from None
        raise
    record(db, ctx, "agent_run", row, "started")
    db.commit()
    return row


@router.post("/cases/{case_id}/agent-runs")
def start_run(case_id: str, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)):
    case = load_case(db, ctx, case_id)
    require_coordinator(ctx)
    run = reserve_run(db, ctx, case)
    try:
        result = agent.run_agent(db, ctx, case)
    except Exception:
        logger.exception("Case investigation failed for run %s", run.id)
        db.rollback()
        result = {"status": "failed", "assessment": "The investigation could not finish.", "steps": [], "proposals": []}

    before = audit.snapshot(run)
    # A timed-out worker cannot overwrite a result after its lease was recovered.
    changed = db.execute(update(AgentRun).where(AgentRun.org_id == ctx.org_id, AgentRun.id == run.id,
                                                 AgentRun.status == "running")
                         .values(status=result["status"], assessment=result["assessment"],
                                 evidence_hash=result.get("evidence_hash", run.evidence_hash)))
    if not changed.rowcount:
        db.rollback()
        raise HTTPException(409, "The investigation expired")
    for step in result["steps"]:
        row = AgentStep(org_id=ctx.org_id, run_id=run.id, **step)
        db.add(row)
        db.flush()
        record(db, ctx, "agent_step", row, "recorded")
    for draft in result["proposals"]:
        fields = dict(draft)
        if isinstance(fields.get("due_date"), str):
            fields["due_date"] = date.fromisoformat(fields["due_date"])
        proposal = AgentProposal(org_id=ctx.org_id, run_id=run.id, **fields)
        db.add(proposal)
        db.flush()
        record(db, ctx, "agent_proposal", proposal, "proposed")
    record(db, ctx, "agent_run", run, result["status"], before)
    db.commit()
    return runs_out(db, ctx, [run])[0]


@router.get("/cases/{case_id}/agent-runs")
def list_runs(case_id: str, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)):
    case = load_case(db, ctx, case_id)
    rows = db.scalars(scoped(AgentRun, ctx).where(AgentRun.case_id == case.id, AgentRun.status != "running")
                      .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())).all()
    return runs_out(db, ctx, rows)


def decide_proposal(db, ctx, proposal_id, *, case_id=None, reason=None):
    """Accept or dismiss atomically in the caller's transaction. Visibility is checked first."""
    row = get_scoped(db, AgentProposal, ctx, proposal_id)
    run = get_scoped(db, AgentRun, ctx, row.run_id)
    case = load_case(db, ctx, run.case_id)
    if case_id is not None and case.id != case_id:
        raise HTTPException(404, "Not found")
    require_coordinator(ctx)
    if reason is None and run.evidence_hash != agent.evidence_hash(case_detail(db, ctx, case)):
        raise HTTPException(409, "Case evidence has changed. Run the investigation again.")
    status = "dismissed" if reason is not None else "accepted"
    before = audit.snapshot(row)
    changed = db.execute(update(AgentProposal).where(AgentProposal.id == row.id, AgentProposal.org_id == ctx.org_id,
                                                     AgentProposal.status == "open")
                         .values(status=status, dismiss_reason=reason))
    if not changed.rowcount:
        raise HTTPException(409, "This proposal has already been decided")
    record(db, ctx, "agent_proposal", row, status, before)
    return row


@router.post("/agent-proposals/{proposal_id}/dismiss")
def dismiss(proposal_id: str, body: Dismiss, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)):
    row = decide_proposal(db, ctx, proposal_id, reason=body.reason)
    db.commit()
    return proposal_out(row)
