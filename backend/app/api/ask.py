from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..ai.ask import AskRequest, answer_question
from ..db import get_db
from ..services.tenancy import Ctx, get_ctx

router = APIRouter(tags=["ask"])


@router.post("/ask")
def ask(body: AskRequest, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return answer_question(db, ctx, body.question, body.case_id)
