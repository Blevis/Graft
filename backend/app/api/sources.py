"""Direct source links (used by citations). A source is readable only if the caller may read original evidence on
its case: the case team or the employee, or a task assignee for exactly the sources their tasks cite. Unlinked
evidence is visible to coordinators only. Anything else is a 404, like another org's id."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import EmployeeCase, Source
from ..services import serialize as ser
from ..services.permissions import TASK_ONLY, Policy
from ..services.tenancy import Ctx, get_ctx, get_scoped
from ..services.visibility import visible_cases

router = APIRouter(tags=["sources"])


def readable_source(db: Session, ctx: Ctx, source_id: str) -> Source:
    s = get_scoped(db, Source, ctx, source_id)
    policy = Policy(db, ctx)
    if s.case_id is None:
        if policy.is_coordinator():
            return s
        raise HTTPException(404, "Not found")
    case = db.execute(visible_cases(ctx).where(EmployeeCase.id == s.case_id)).scalar_one_or_none()
    if case is None:
        raise HTTPException(404, "Not found")
    if policy.sees_evidence(case):
        return s
    if policy.level(case) == TASK_ONLY and s.id in policy.task_cited_source_ids(case):
        return s
    raise HTTPException(404, "Not found")


@router.get("/sources/{source_id}")
def get_source(source_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    s = readable_source(db, ctx, source_id)
    case = db.get(EmployeeCase, s.case_id) if s.case_id else None
    return {**ser.source_out(s), "case": {"id": case.id, "ref": case.ref, "employee": case.employee} if case else None}
