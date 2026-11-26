"""Access items: requested != approved != active != confirmed_usable.
Only the employee's own successful test can set confirmed_usable."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AccessItem, Source
from ..schemas.requests import AccessCreate, AccessUpdate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, get_scoped, scoped

router = APIRouter(tags=["access"])
COORD = ("admin", "pmo_coordinator")


@router.get("/cases/{case_id}/access-items")
def list_access(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    rows = db.execute(scoped(AccessItem, ctx).where(AccessItem.case_id == case.id)
                      .order_by(AccessItem.system)).scalars()
    return [ser.access_out(a) for a in rows]


@router.post("/cases/{case_id}/access-items", status_code=201)
def create_access(case_id: str, body: AccessCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    if ctx.role not in COORD:
        raise HTTPException(403, "Only a coordinator can add access items")
    case = load_case(db, ctx, case_id)
    if body.state == "confirmed_usable":
        raise HTTPException(422, "Only the employee's successful test can mark access as usable")
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
    return ser.access_out(a)


@router.patch("/access-items/{item_id}")
def update_access(item_id: str, body: AccessUpdate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    a = get_scoped(db, AccessItem, ctx, item_id)
    case = load_case(db, ctx, a.case_id)
    if body.state == "confirmed_usable":
        if ctx.user_id != case.employee_user_id:
            raise HTTPException(403, "Only the employee can confirm a successful test of their access")
    elif ctx.role not in COORD:
        raise HTTPException(403, "Only a coordinator can change an access state")
    before = audit.snapshot(a)
    a.state = body.state
    if body.next_follow_up is not None:
        a.next_follow_up = body.next_follow_up
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="access_item", entity_id=a.id,
                 action="state_changed", before=before, after=audit.snapshot(a))
    recompute_case(db, case)
    db.commit()
    return ser.access_out(a)
