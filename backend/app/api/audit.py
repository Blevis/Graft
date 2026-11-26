from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent
from ..services import serialize as ser
from ..services.tenancy import Ctx, require_roles, scoped

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_audit(entity: str | None = None, entity_id: str | None = None, limit: int = 200,
               ctx: Ctx = Depends(require_roles("admin", "pmo_coordinator")), db: Session = Depends(get_db)):
    q = scoped(AuditEvent, ctx)
    if entity:
        q = q.where(AuditEvent.entity == entity)
    if entity_id:
        q = q.where(AuditEvent.entity_id == entity_id)
    lk = ser.Lookup(db, ctx.org_id)
    rows = db.execute(q.order_by(AuditEvent.created_at.desc()).limit(min(limit, 500))).scalars()
    return [{"id": e.id, "actor": lk.user_ref(e.actor_user_id), "entity": e.entity, "entity_id": e.entity_id,
             "action": e.action, "before": e.before, "after": e.after, "created_at": ser.iso(e.created_at)}
            for e in rows]
