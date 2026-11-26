from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.serialize import Lookup
from ..services.tenancy import Ctx, get_ctx

router = APIRouter(tags=["users"])


@router.get("/users")
def list_users(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lk = Lookup(db, ctx.org_id)
    return sorted(
        ({"id": u.id, "name": u.name, "title": u.title, "role": lk.roles[u.id],
          "roles": sorted(lk.role_codes.get(u.id, set())), "status": lk.status[u.id]}
         for u in lk.users.values() if lk.status[u.id] == "active"),
        key=lambda u: u["name"],
    )
