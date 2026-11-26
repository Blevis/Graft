"""The only writer of the reviews table. Append-only: there is no update or delete route."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification, Review, Source, Task
from ..schemas.requests import ReviewCreate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case, reviews_for
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["reviews"])


@router.get("/cases/{case_id}/reviews")
def list_reviews(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    lk = ser.Lookup(db, ctx.org_id)
    return [ser.review_out(r, lk) for r in reviews_for(db, ctx.org_id, case.id)]


@router.post("/cases/{case_id}/reviews", status_code=201)
def create_review(case_id: str, body: ReviewCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    lk = ser.Lookup(db, ctx.org_id)
    if ctx.user_id != lk.tech_owner_id(case):
        raise HTTPException(403, "Only the case's assigned technical owner can record a readiness review")
    if body.task_id:
        t = db.execute(scoped(Task, ctx).where(Task.id == body.task_id)).scalar_one_or_none()
        if t is None or t.case_id != case.id:
            raise HTTPException(422, "Linked task does not belong to this case")
    for sid in body.cited_source_ids:
        s = db.execute(scoped(Source, ctx).where(Source.id == sid)).scalar_one_or_none()
        if s is None or s.case_id != case.id:
            raise HTTPException(422, "Cited source does not belong to this case")
    r = Review(org_id=ctx.org_id, case_id=case.id, disposition=body.disposition, scope=body.scope.strip(),
               rationale=body.rationale.strip(), observed_stage=body.observed_stage,
               cited_source_ids=body.cited_source_ids, task_id=body.task_id, reviewer_user_id=ctx.user_id)
    db.add(r)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="review", entity_id=r.id,
                 action="created", after=audit.snapshot(r))
    for uid in {case.line_manager_user_id} - {None, ctx.user_id}:
        db.add(Notification(org_id=ctx.org_id, user_id=uid,
                            text=f"{ctx.user.name} recorded '{body.disposition.replace('_', ' ')}' for {case.ref}",
                            link=f"/app/cases/{case.ref}"))
    db.commit()
    return ser.review_out(r, lk)
