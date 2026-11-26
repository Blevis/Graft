from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Notification
from ..services import serialize as ser
from ..services.org_settings import get_org_settings
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["org"])


@router.get("/org")
def get_org(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return ser.org_out(ctx.org, get_org_settings(db, ctx.org_id))


@router.get("/notifications")
def notifications(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    rows = db.execute(scoped(Notification, ctx).where(Notification.user_id == ctx.user_id)
                      .order_by(Notification.created_at.desc()).limit(30)).scalars()
    return [{"id": n.id, "text": n.text, "link": n.link, "read": n.read, "created_at": ser.iso(n.created_at)}
            for n in rows]


@router.post("/notifications/read-all")
def read_all(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    for n in db.execute(scoped(Notification, ctx).where(Notification.user_id == ctx.user_id,
                                                        Notification.read.is_(False))).scalars():
        n.read = True
    db.commit()
    return {"ok": True}
