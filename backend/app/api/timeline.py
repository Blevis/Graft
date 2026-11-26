from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.cases import load_case, timeline
from ..services.tenancy import Ctx, get_ctx

router = APIRouter(tags=["timeline"])


@router.get("/cases/{case_id}/timeline")
def case_timeline(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return timeline(db, ctx, load_case(db, ctx, case_id))
