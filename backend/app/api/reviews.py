"""The only writer of the reviews table. Append-only: there is no update or delete route.

Sign-off policy v1 (docs/business-rules.md, "Readiness and sign-off"):
- Only the case's primary technical owner records a review.
- validate_scope validates a named scope, optionally one case milestone; it never sets overall readiness.
- close is final sign-off: a rationale, at least one citation of a current source version bound to this case,
  every required milestone validated and no blocking access. Unmet milestones/access may be bypassed only when the
  org enables documented exceptions, with an exception reason; the bypassed criteria are stored and audited.
- reopen reverses the current sign-off (or one milestone validation) with a reason; nothing is edited."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AccessItem, CaseRequirement, Notification, Review, Source, Task
from ..schemas.requests import ReviewCreate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case, reviews_for
from ..services.evidence import latest_sources
from ..services.permissions import Policy
from ..services.readiness import closure_gate, derive, snapshot
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["reviews"])


@router.get("/cases/{case_id}/reviews")
def list_reviews(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    policy = Policy(db, ctx)
    if not policy.can_view_field("reviews", case):
        return []
    lk = ser.Lookup(db, ctx.org_id)
    rationale = policy.can_view_field("review_rationale", case)
    return [{**ser.review_out(r, lk), **({} if rationale else {"rationale": None, "cited_source_ids": []})}
            for r in reviews_for(db, ctx.org_id, case.id)]


@router.post("/cases/{case_id}/reviews", status_code=201)
def create_review(case_id: str, body: ReviewCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    if not policy.can_review(case):
        raise HTTPException(403, "Only the case's assigned technical owner can record a readiness review")
    if body.task_id:
        t = db.execute(scoped(Task, ctx).where(Task.id == body.task_id)).scalar_one_or_none()
        if t is None or t.case_id != case.id:
            raise HTTPException(422, "Linked task does not belong to this case")
    current = latest_sources(db, ctx.org_id, case_id=case.id)
    current_ids = {s.id for s in current}
    cited = list(dict.fromkeys(body.cited_source_ids))
    for sid in cited:
        s = db.execute(scoped(Source, ctx).where(Source.id == sid)).scalar_one_or_none()
        if s is None or s.case_id != case.id:
            raise HTTPException(422, "Cited source does not belong to this case")
        if sid not in current_ids:
            raise HTTPException(422, f"{s.ref or 'A cited source'} has a newer version; cite the current version")

    reviews = reviews_for(db, ctx.org_id, case.id)
    st = derive(reviews)
    reqs = list(db.execute(scoped(CaseRequirement, ctx).where(CaseRequirement.case_id == case.id)).scalars())
    milestone = None
    if body.milestone_key:
        milestone = next((r for r in reqs if r.key == body.milestone_key), None)
        if milestone is None or milestone.kind != "milestone":
            raise HTTPException(422, "Unknown milestone for this case")
        if milestone.applicability == "not_applicable":
            raise HTTPException(422, "This milestone is marked not applicable for the case")
    supersedes = None
    exception_reason = (body.exception_reason or "").strip() or None
    bypassed: list[str] | None = None

    if body.disposition == "validate_scope":
        if not cited:
            raise HTTPException(422, "A scope validation must cite the evidence it relies on")
        if milestone is not None and milestone.key in st.validated:
            raise HTTPException(409, "This milestone is already validated; reopen it first to record a new decision")
    elif body.disposition == "close":
        if milestone is not None:
            raise HTTPException(422, "Final sign-off covers the whole case; validate milestones with validate_scope")
        if st.status == "signed_off":
            raise HTTPException(409, "The case is already signed off; record a reopen first")
        access = list(db.execute(scoped(AccessItem, ctx).where(AccessItem.case_id == case.id)).scalars())
        hard, waivable = closure_gate(cited_ids=cited, current_sources=current, reqs=reqs, st=st, access=access)
        if hard:
            raise HTTPException(422, {"message": "Final sign-off is blocked", "unmet": hard + waivable})
        if waivable:
            if not (policy.settings.get("allow_closure_exceptions") and exception_reason):
                raise HTTPException(422, {"message": "Final sign-off is blocked: required checks are not met",
                                          "unmet": waivable,
                                          "exceptions_allowed": bool(policy.settings.get("allow_closure_exceptions"))})
            bypassed = waivable
        elif exception_reason:
            exception_reason = None  # nothing to bypass: do not record a misleading exception
    elif body.disposition == "reopen":
        if milestone is not None:
            if milestone.key not in st.validated:
                raise HTTPException(409, "This milestone is not currently validated")
            supersedes = st.validated[milestone.key].id
        else:
            if st.status != "signed_off":
                raise HTTPException(409, "There is no final sign-off to reopen")
            supersedes = st.final_review.id
    if exception_reason and body.disposition != "close":
        raise HTTPException(422, "An exception reason applies only to final sign-off")

    r = Review(org_id=ctx.org_id, case_id=case.id, disposition=body.disposition, scope=body.scope.strip(),
               rationale=body.rationale.strip(), observed_stage=body.observed_stage,
               cited_source_ids=cited, task_id=body.task_id, reviewer_user_id=ctx.user_id,
               milestone_key=milestone.key if milestone else None, supersedes_review_id=supersedes,
               exception_reason=exception_reason, bypassed_criteria=bypassed, policy_version="v1",
               evidence_snapshot=snapshot(current))
    db.add(r)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="review", entity_id=r.id,
                 action="exception_sign_off" if bypassed else ("reopened" if body.disposition == "reopen"
                                                               else "created"),
                 after={**audit.snapshot(r), "capacity": "technical_owner", "bypassed_criteria": bypassed})
    verb = body.disposition.replace("_", " ")
    for uid in {lk.line_manager_id(case)} - {None, ctx.user_id}:
        db.add(Notification(org_id=ctx.org_id, user_id=uid, text=f"{ctx.user.name} recorded '{verb}' for {case.ref}",
                            link=f"/app/cases/{case.ref}"))
    db.commit()
    return ser.review_out(r, lk)
