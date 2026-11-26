"""Shared inbox for incoming evidence. Sources are immutable: linking creates a new version row."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from sqlalchemy import select

from ..models import AnalysisJob, EmployeeCase, Source
from ..schemas.requests import InboxLink, InboxPost
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.evidence import current_run, latest_attempt, latest_sources
from ..services.jobs import after_commit, enqueue_analysis
from ..services.matching import match_detail
from ..services.org_settings import get_org_settings
from ..services.rules import recompute_case
from ..services.permissions import Policy
from ..services.visibility import visible_cases
from ..services.tenancy import Ctx, get_ctx, get_scoped, require_roles, scoped

router = APIRouter(prefix="/inbox", tags=["inbox"])
COORD = ("admin", "pmo_coordinator")


def _item(db: Session, s: Source, cases: dict[str, EmployeeCase], lk: ser.Lookup) -> dict:
    c = cases.get(s.case_id) if s.case_id else None
    run = current_run(db, s) or latest_attempt(db, s)
    job = db.execute(select(AnalysisJob).where(AnalysisJob.source_id == s.id)
                     .order_by(AnalysisJob.created_at.desc()).limit(1)).scalar_one_or_none()
    status = "matched" if (s.case_id or s.project_id) else ("needs_review" if s.match_status == "needs_review"
                                                              else "unmatched")
    candidates = [cases[i] for i in (s.match_candidates or []) if i in cases] if status == "needs_review" else []
    return {
        "source": ser.source_out(s),
        "status": status,
        "candidates": [{"id": x.id, "ref": x.ref, "employee": x.employee} for x in candidates],
        "job": ser.job_out(job) if job else None,
        "matched_case": {"id": c.id, "ref": c.ref, "employee": c.employee} if c else None,
        "matched_project": lk.project_ref(s.project_id) if not c else None,
        "analysis": ser.run_out(run) if run else None,
    }


@router.get("")
def list_inbox(status: str | None = None, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    sources = latest_sources(db, ctx.org_id)
    if not policy.is_coordinator():
        # Everyone else sees only evidence bound to cases where their view level includes original evidence,
        # never unmatched mail. Management viewers and auditors read summaries, not raw evidence.
        sources = [s for s in sources if s.case_id in cases and policy.sees_evidence(cases[s.case_id])]
    items = [_item(db, s, cases, lk) for s in sources]
    if status in ("matched", "unmatched", "needs_review"):
        items = [i for i in items if i["status"] == status]
    return sorted(items, key=lambda i: (i["source"]["date"] or "", i["source"]["created_at"]), reverse=True)


@router.post("", status_code=201)
def post_inbox(body: InboxPost, ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    m = match_detail(db, ctx.org_id, body.title, body.body)
    case = m.case
    s = Source(org_id=ctx.org_id, kind=body.kind, title=body.title.strip(), case_id=case.id if case else None,
               project_id=case.project_id if case else None, author_role=body.author_role.strip(),
               recipient_role=(body.recipient_role or "").strip() or None, date=body.date, body=body.body,
               body_sha256=hashlib.sha256(body.body.encode("utf-8")).hexdigest(), version=1,
               ingested_via="paste", created_by_user_id=ctx.user_id, channel="paste", sender=ctx.user.name,
               match_status=m.status, match_candidates=[c.id for c in m.candidates] or None)
    db.add(s)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=s.id,
                 action="ingested", after={**ser.source_meta(s), "match": m.reason})
    job = enqueue_analysis(db, s, reason="ingested", user_id=ctx.user_id) if case else None
    if case:
        recompute_case(db, case)
    db.commit()
    after_commit(db, [job])
    db.expire_all()
    job = db.get(AnalysisJob, job.id) if job else None
    outcome = {"mode": job.outcome_mode or job.status, "note": job.last_error} if job else None
    lk = ser.Lookup(db, ctx.org_id)
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    return {**_item(db, db.get(Source, s.id), cases, lk), "analysis_outcome": outcome}


@router.post("/{source_id}/link")
def link(source_id: str, body: InboxLink, ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    old = get_scoped(db, Source, ctx, source_id)
    if old.id not in {x.id for x in latest_sources(db, ctx.org_id)}:
        raise HTTPException(409, "Only the current version of a source can be linked")
    case = load_case(db, ctx, body.case_id)
    if old.case_id == case.id:
        raise HTTPException(409, "Already linked to this case")
    new = Source(org_id=ctx.org_id, ref=old.ref, kind=old.kind, title=old.title, case_id=case.id,
                 project_id=case.project_id, author_role=old.author_role, recipient_role=old.recipient_role,
                 date=old.date, header=old.header, body=old.body, body_sha256=old.body_sha256,
                 version=old.version + 1, supersedes_id=old.id, ingested_via=old.ingested_via,
                 created_by_user_id=ctx.user_id, external_id=old.external_id, channel=old.channel,
                 sender=old.sender, received_at=old.received_at, match_status="matched", document=old.document)
    db.add(new)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=new.id,
                 action="linked", before={"source_id": old.id, "case_id": old.case_id},
                 after={"source_id": new.id, "case_id": case.id, "version": new.version})
    job = enqueue_analysis(db, new, reason="linked", user_id=ctx.user_id)
    recompute_case(db, case)
    if old.case_id and old.case_id != case.id:
        prev = db.get(EmployeeCase, old.case_id)
        if prev is not None:
            recompute_case(db, prev)
    db.commit()
    after_commit(db, [job])
    db.expire_all()
    return _item(db, db.get(Source, new.id), {case.id: case}, ser.Lookup(db, ctx.org_id))
