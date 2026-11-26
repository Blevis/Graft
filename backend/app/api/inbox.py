"""Shared inbox for incoming evidence. Sources are immutable: linking creates a new version row."""
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai.pipeline import analyze_source
from ..db import get_db
from ..models import EmployeeCase, Source
from ..schemas.requests import InboxLink, InboxPost
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.evidence import current_run, latest_attempt, latest_sources
from ..services.matching import match_case
from ..services.org_settings import get_org_settings
from ..services.rules import recompute_case
from ..services.visibility import sees_all, visible_cases
from ..services.tenancy import Ctx, get_ctx, get_scoped, require_roles, scoped

router = APIRouter(prefix="/inbox", tags=["inbox"])
COORD = ("admin", "pmo_coordinator")


def _item(db: Session, s: Source, cases: dict[str, EmployeeCase], lk: ser.Lookup) -> dict:
    c = cases.get(s.case_id) if s.case_id else None
    run = current_run(db, s) or latest_attempt(db, s)
    return {
        "source": ser.source_out(s),
        "status": "matched" if (s.case_id or s.project_id) else "unmatched",
        "matched_case": {"id": c.id, "ref": c.ref, "employee": c.employee} if c else None,
        "matched_project": lk.project_ref(s.project_id) if not c else None,
        "analysis": ser.run_out(run) if run else None,
    }


@router.get("")
def list_inbox(status: str | None = None, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lk = ser.Lookup(db, ctx.org_id)
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    sources = latest_sources(db, ctx.org_id)
    if not sees_all(ctx):
        # Members with a limited view see only evidence bound to their visible cases, never unmatched mail.
        sources = [s for s in sources if s.case_id in cases]
    items = [_item(db, s, cases, lk) for s in sources]
    if status in ("matched", "unmatched"):
        items = [i for i in items if i["status"] == status]
    return sorted(items, key=lambda i: (i["source"]["date"] or "", i["source"]["created_at"]), reverse=True)


@router.post("", status_code=201)
def post_inbox(body: InboxPost, ctx: Ctx = Depends(require_roles(*COORD)), db: Session = Depends(get_db)):
    case = match_case(db, ctx.org_id, body.title, body.body)
    s = Source(org_id=ctx.org_id, kind=body.kind, title=body.title.strip(), case_id=case.id if case else None,
               project_id=case.project_id if case else None, author_role=body.author_role.strip(),
               recipient_role=(body.recipient_role or "").strip() or None, date=body.date, body=body.body,
               body_sha256=hashlib.sha256(body.body.encode("utf-8")).hexdigest(), version=1,
               ingested_via="paste", created_by_user_id=ctx.user_id)
    db.add(s)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=s.id,
                 action="ingested", after=audit.snapshot(s))
    outcome = None
    if case:
        o = analyze_source(db, s, ai_enabled=bool(get_org_settings(db, ctx.org_id)["ai_enabled"]))
        outcome = {"mode": o.served_mode, "note": o.note}
        recompute_case(db, case)
    db.commit()
    lk = ser.Lookup(db, ctx.org_id)
    return {**_item(db, s, {case.id: case} if case else {}, lk), "analysis_outcome": outcome}


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
                 created_by_user_id=ctx.user_id)
    db.add(new)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=new.id,
                 action="linked", before={"source_id": old.id, "case_id": old.case_id},
                 after={"source_id": new.id, "case_id": case.id, "version": new.version})
    analyze_source(db, new, ai_enabled=bool(get_org_settings(db, ctx.org_id)["ai_enabled"]))
    recompute_case(db, case)
    if old.case_id and old.case_id != case.id:
        prev = db.get(EmployeeCase, old.case_id)
        if prev is not None:
            recompute_case(db, prev)
    db.commit()
    return _item(db, new, {case.id: case}, ser.Lookup(db, ctx.org_id))
