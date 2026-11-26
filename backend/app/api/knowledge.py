from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import KnowledgeRef
from ..services import serialize as ser
from ..services.org_settings import as_of, get_org_settings
from ..services.permissions import EMPLOYEE, FULL, SUMMARY, Policy
from ..services.tenancy import Ctx, get_ctx, scoped
from ..services.visibility import sees_all, visible_cases

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge")
def list_knowledge(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Project references (locations, never copied documents). Each shows provenance, last verification and whether
    it needs re-verification; stale material is flagged, not presented as current truth."""
    lk = ser.Lookup(db, ctx.org_id)
    today = as_of(get_org_settings(db, ctx.org_id))
    rows = db.execute(scoped(KnowledgeRef, ctx).order_by(KnowledgeRef.title)).scalars().all()
    if not sees_all(ctx):
        # Project references follow project access: project roles, or a case in that project the caller may read.
        policy = Policy(db, ctx)
        projects = set(ctx.project_ids()) | {c.project_id for c in db.execute(visible_cases(ctx)).scalars()
                                              if c.project_id and policy.level(c) in (FULL, EMPLOYEE, SUMMARY)}
        rows = [k for k in rows if k.project_id in projects]
    return [ser.knowledge_out(k, lk, today) for k in rows]
