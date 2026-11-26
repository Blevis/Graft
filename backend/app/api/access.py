"""Access items: requested != approved != active != confirmed_usable.

Coordination (request / approve / activate) belongs to coordinators, the project manager and the case's access
responsible (for the whole case or one system). Usability is confirmed only by the appropriate tester: the
employee by default (starter pack); a designated tester per system when the org's access_tester_policy is
"designated". AI has no import path to this writer."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AccessItem, Membership, Source
from ..models._base import utcnow
from ..schemas.requests import AccessCreate, AccessUpdate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.permissions import Policy
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, get_scoped, scoped

router = APIRouter(tags=["access"])


@router.get("/cases/{case_id}/access-items")
def list_access(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    rows = list(db.execute(scoped(AccessItem, ctx).where(AccessItem.case_id == case.id)
                           .order_by(AccessItem.system)).scalars())
    lk = ser.Lookup(db, ctx.org_id)
    return [ser.access_out(a, lk) for a in Policy(db, ctx).access_items_in_scope(case, rows)]


@router.post("/cases/{case_id}/access-items", status_code=201)
def create_access(case_id: str, body: AccessCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    if not Policy(db, ctx).can_edit_access(case):
        raise HTTPException(403, "Only a coordinator, the project manager or the case's access responsible can "
                                 "add access items")
    if body.state == "confirmed_usable":
        raise HTTPException(422, "Only the tester's successful test can mark access as usable")
    for sid in body.evidence_source_ids:
        s = db.execute(scoped(Source, ctx).where(Source.id == sid)).scalar_one_or_none()
        if s is None or s.case_id != case.id:
            raise HTTPException(422, "Evidence source does not belong to this case")
    a = AccessItem(org_id=ctx.org_id, case_id=case.id, **body.model_dump())
    db.add(a)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="access_item", entity_id=a.id,
                 action="created", after=audit.snapshot(a))
    recompute_case(db, case)
    db.commit()
    return ser.access_out(a, ser.Lookup(db, ctx.org_id))


@router.patch("/access-items/{item_id}")
def update_access(item_id: str, body: AccessUpdate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    a = get_scoped(db, AccessItem, ctx, item_id)
    case = load_case(db, ctx, a.case_id)
    policy = Policy(db, ctx)
    if a not in policy.access_items_in_scope(case, [a]):
        raise HTTPException(404, "Not found")
    changes = body.model_fields_set
    if "tester_user_id" in changes:
        if not policy.can_edit_access(case, a):
            raise HTTPException(403, "You cannot designate the tester for this system")
        if policy.settings.get("access_tester_policy") != "designated":
            raise HTTPException(422, "This organisation confirms access only through the employee's own test "
                                     "(setting access_tester_policy)")
        if body.tester_user_id is not None:
            m = db.execute(select(Membership).where(Membership.org_id == ctx.org_id,
                                                    Membership.user_id == body.tester_user_id)).scalar_one_or_none()
            if m is None or m.status != "active":
                raise HTTPException(422, "Tester is not an active member of this organisation")
    if "state" in changes and body.state is not None:
        if body.state == "confirmed_usable":
            if not policy.can_confirm_access(case, a):
                raise HTTPException(403, "Only the designated tester (by default the employee) can confirm a "
                                         "successful test of this access")
        elif not policy.can_edit_access(case, a):
            raise HTTPException(403, "Only a coordinator, the project manager or the access responsible can change "
                                     "an access state")
    if "next_follow_up" in changes and not policy.can_edit_access(case, a):
        raise HTTPException(403, "You cannot change the follow-up date for this system")
    before = audit.snapshot(a)
    if "state" in changes and body.state is not None and body.state != a.state:
        a.state = body.state
        if body.state == "confirmed_usable":
            a.tested_by_user_id, a.tested_at = ctx.user_id, utcnow()
    if body.next_follow_up is not None:
        a.next_follow_up = body.next_follow_up
    if "tester_user_id" in changes:
        a.tester_user_id = body.tester_user_id
    db.flush()
    held = sorted(policy.responsibilities_held(case))
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="access_item", entity_id=a.id,
                 action="state_changed", before=before,
                 after={**audit.snapshot(a), "capacity": held[0] if held else ("tester" if a.tested_by_user_id ==
                                                                               ctx.user_id else "coordinator")})
    recompute_case(db, case)
    db.commit()
    return ser.access_out(a, ser.Lookup(db, ctx.org_id))
