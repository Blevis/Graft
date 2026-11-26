"""Personal AI presentation preferences and the organisation's versioned PMO AI guidance.
Both change presentation only (services/presentation.py); neither is read by an authorization check."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AIGuidanceVersion, UserPreference
from ..schemas.requests import AIGuidancePatch, PreferencesPatch
from ..services import audit
from ..services import serialize as ser
from ..services.permissions import Policy
from ..services.presentation import FORBIDDEN_GUIDANCE, PROFILES, get_preferences, guidance_out, resolve
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["preferences"])


@router.get("/me/preferences")
def read_preferences(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return {"preferences": get_preferences(db, ctx), "effective": resolve(db, ctx),
            "available_roles": sorted(ctx.roles),
            "profiles": {code: {"label": p["label"], "emphasis": p["emphasis"]} for code, p in PROFILES.items()}}


@router.patch("/me/preferences")
def patch_preferences(body: PreferencesPatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    changes = {k: getattr(body, k) for k in body.model_fields_set}
    if changes.get("working_role") is not None and changes["working_role"] not in ctx.roles:
        # A working context is chosen among roles you already hold; it can never add one.
        raise HTTPException(422, "You can only switch to a role you hold")
    row = db.execute(select(UserPreference).where(UserPreference.org_id == ctx.org_id,
                                                  UserPreference.user_id == ctx.user_id)).scalar_one_or_none()
    before = dict(row.value or {}) if row else {}
    value = {**before, **changes}
    if row is None:
        row = UserPreference(org_id=ctx.org_id, user_id=ctx.user_id, value=value)
        db.add(row)
    else:
        row.value = value
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="user_preference", entity_id=row.id,
                 action="updated", before=before, after=value)
    db.commit()
    return read_preferences(ctx, db)


@router.get("/settings/ai-guidance")
def read_guidance(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lk = ser.Lookup(db, ctx.org_id)
    rows = db.execute(scoped(AIGuidanceVersion, ctx).order_by(AIGuidanceVersion.version.desc())).scalars().all()
    hist = [{**guidance_out(g), "created_by": lk.user_ref(g.created_by_user_id)} for g in rows]
    return {"current": hist[0] if hist else None, "history": hist,
            "can_edit": Policy(db, ctx).can_edit_ai_guidance(),
            "guardrails": [
                "Guidance changes wording, terminology, ordering and report structure only.",
                "It cannot disable citations, widen what anyone can see, or let the AI decide readiness.",
                "Every save is a new version and is recorded in the audit trail.",
            ]}


@router.patch("/settings/ai-guidance")
def save_guidance(body: AIGuidancePatch, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    if not Policy(db, ctx).can_edit_ai_guidance():
        raise HTTPException(403, "Only an admin or the PMO can change the organisation's AI guidance")
    fields = body.model_dump()
    for name, text in fields.items():
        if FORBIDDEN_GUIDANCE.search(text or ""):
            raise HTTPException(422, f"'{name.replace('_', ' ')}' tries to change rules, not presentation "
                                     "(citations, permissions and readiness decisions are fixed)")
    prev = db.execute(scoped(AIGuidanceVersion, ctx).order_by(AIGuidanceVersion.version.desc()).limit(1)
                      ).scalar_one_or_none()
    g = AIGuidanceVersion(org_id=ctx.org_id, version=(prev.version + 1) if prev else 1,
                          created_by_user_id=ctx.user_id, **{k: (v or "").strip() for k, v in fields.items()})
    db.add(g)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="ai_guidance", entity_id=g.id,
                 action="version_saved", before=guidance_out(prev), after=guidance_out(g))
    db.commit()
    return read_guidance(ctx, db)
