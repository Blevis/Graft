from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import KnowledgeRef
from ..services import serialize as ser
from ..services.org_settings import as_of, get_org_settings
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge")
def list_knowledge(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Project references (locations, never copied documents). Each shows provenance, last verification and whether
    it needs re-verification; stale material is flagged, not presented as current truth."""
    lk = ser.Lookup(db, ctx.org_id)
    today = as_of(get_org_settings(db, ctx.org_id))
    rows = db.execute(scoped(KnowledgeRef, ctx).order_by(KnowledgeRef.title)).scalars()
    return [ser.knowledge_out(k, lk, today) for k in rows]
