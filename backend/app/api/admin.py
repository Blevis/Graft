from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..seed.seed import run as run_seed
from ..services.tenancy import Ctx, require_roles

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/reset")
def reset_demo(ctx: Ctx = Depends(require_roles("admin"))):
    """DEMO_MODE only: rebuild both demo orgs from data/seed.json. Explicit, never on startup."""
    if not get_settings().DEMO_MODE or not ctx.org.is_demo:
        raise HTTPException(404, "Not found")
    return {"ok": True, "message": run_seed(reset=True)}
