from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import client
from ..config import get_settings
from ..db import get_db
from ..models import EmployeeCase, Setting
from ..schemas.requests import SettingsPatch
from ..services import audit
from ..services.org_settings import get_org_settings
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, require_roles, scoped

router = APIRouter(prefix="/settings", tags=["settings"])


def _out(db: Session, org_id: str) -> dict:
    return {**get_org_settings(db, org_id),
            "llm": {"model": get_settings().LLM_MODEL, "configured": client.is_configured()}}


@router.get("")
def read_settings(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return _out(db, ctx.org_id)


@router.patch("")
def patch_settings(body: SettingsPatch, ctx: Ctx = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    before = get_org_settings(db, ctx.org_id)
    changes = {k: (v.isoformat() if hasattr(v, "isoformat") else v)
               for k, v in body.model_dump(exclude_none=True).items()}
    for k, v in changes.items():
        row = db.execute(select(Setting).where(Setting.org_id == ctx.org_id, Setting.key == k)).scalar_one_or_none()
        if row is None:
            db.add(Setting(org_id=ctx.org_id, key=k, value=v))
        else:
            row.value = v
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="settings", entity_id=ctx.org_id,
                 action="updated", before={k: before.get(k) for k in changes}, after=changes)
    # Thresholds and as-of date change derived findings; recompute them (derived tables only).
    for case in db.execute(scoped(EmployeeCase, ctx)).scalars():
        recompute_case(db, case)
    db.commit()
    return _out(db, ctx.org_id)
