from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import KnowledgeRef
from ..services import serialize as ser
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["knowledge"])


@router.get("/knowledge")
def list_knowledge(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lk = ser.Lookup(db, ctx.org_id)
    return [ser.knowledge_out(k, lk) for k in db.execute(scoped(KnowledgeRef, ctx).order_by(KnowledgeRef.title)).scalars()]
