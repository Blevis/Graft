"""Case Stakeholders & Responsibilities, and the training log. The only writers of case_responsibilities and
training_entries. AI has no import path here (tests/test_agent_boundaries.py).

Responsibilities: a coordinator (or, when the org allows it, the project's manager) assigns them. The assignee
must already hold the matching role at organization, project or case scope, and nobody assigns themselves.
Replacing a primary holder ends the previous row instead of deleting it, so history stays."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AccessItem, CaseResponsibility, Membership, Notification, RoleAssignment, Source, TrainingEntry
from ..models._base import utcnow
from ..schemas.requests import ResponsibilityCreate, ResponsibilityPatch, TrainingCreate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.permissions import Policy
from ..services.roles import RESPONSIBILITY_TYPES
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, get_scoped, scoped

router = APIRouter(tags=["responsibilities"])


def _eligible_ids(db: Session, ctx: Ctx, case, rtype: str) -> set[str]:
    """Active members holding role `rtype` at org scope, on the case's project, or on the case itself."""
    q = select(RoleAssignment.user_id).join(
        Membership, (Membership.user_id == RoleAssignment.user_id) & (Membership.org_id == RoleAssignment.org_id)
    ).where(RoleAssignment.org_id == ctx.org_id, RoleAssignment.role_code == rtype,
            RoleAssignment.is_active.is_(True), Membership.status == "active")
    rows = db.execute(q.add_columns(RoleAssignment.scope_type, RoleAssignment.scope_id)).all()
    return {uid for uid, st, sid in rows
            if st == "organization" or (st == "project" and sid and sid == case.project_id)
            or (st == "case" and sid == case.id)}


def _payload(db: Session, ctx: Ctx, case) -> dict:
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    access = {a.id: a.system for a in db.execute(scoped(AccessItem, ctx).where(AccessItem.case_id == case.id))
              .scalars()}
    history = db.execute(scoped(CaseResponsibility, ctx).where(CaseResponsibility.case_id == case.id,
                                                               CaseResponsibility.is_active.is_(False))
                         .order_by(CaseResponsibility.ended_at.desc())).scalars().all()
    can_assign = policy.can_assign(case)
    return {
        "stakeholders": ser.stakeholders_out(case, lk, access),
        "ownership_gaps": lk.idx.gaps(case, list(lk.settings.get("required_responsibilities") or [])),
        "history": [{
            "id": r.id, "responsibility_type": r.responsibility_type, "user": lk.user_ref(r.user_id),
            "source": r.source, "assigned_at": ser.iso(r.assigned_at), "assigned_by": lk.user_ref(r.assigned_by_user_id),
            "ended_at": ser.iso(r.ended_at), "ended_by": lk.user_ref(r.ended_by_user_id),
            "system": access.get(r.access_item_id) if r.access_item_id else None,
        } for r in history],
        "can_assign": can_assign,
        "reason": None if can_assign else "You can view these stakeholders but cannot change their assignments.",
        "eligible": {t: [lk.user_ref(u) for u in sorted(_eligible_ids(db, ctx, case, t) - {ctx.user_id},
                                                        key=lambda u: lk.users[u].name if u in lk.users else u)
                         if u in lk.users]
                     for t in RESPONSIBILITY_TYPES} if can_assign else {},
        "access_items": [{"id": i, "system": s} for i, s in access.items()],
    }


@router.get("/cases/{case_id}/responsibilities")
def list_responsibilities(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return _payload(db, ctx, load_case(db, ctx, case_id))


def _end(db: Session, ctx: Ctx, r: CaseResponsibility, action: str) -> None:
    before = audit.snapshot(r)
    r.is_active, r.ended_at, r.ended_by_user_id = False, utcnow(), ctx.user_id
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case_responsibility", entity_id=r.id,
                 action=action, before=before, after=audit.snapshot(r))


@router.post("/cases/{case_id}/responsibilities", status_code=201)
def assign(case_id: str, body: ResponsibilityCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    policy = Policy(db, ctx)
    if not policy.can_assign(case):
        raise HTTPException(403, "You can view these stakeholders but cannot change their assignments")
    if body.user_id == ctx.user_id:
        raise HTTPException(403, "You cannot assign a responsibility to yourself; ask a coordinator")
    if body.user_id not in _eligible_ids(db, ctx, case, body.responsibility_type):
        raise HTTPException(422, f"This person does not hold the {body.responsibility_type.replace('_', ' ')} role "
                                 "for this case; an admin must grant it first")
    if body.access_item_id is not None:
        if body.responsibility_type != "access_responsible":
            raise HTTPException(422, "Only an access responsible can be assigned per system")
        item = get_scoped(db, AccessItem, ctx, body.access_item_id)
        if item.case_id != case.id:
            raise HTTPException(422, "Access item does not belong to this case")
    existing = db.execute(scoped(CaseResponsibility, ctx).where(
        CaseResponsibility.case_id == case.id, CaseResponsibility.responsibility_type == body.responsibility_type,
        CaseResponsibility.is_active.is_(True))).scalars().all()
    same_scope = [r for r in existing if r.access_item_id == body.access_item_id]
    if any(r.user_id == body.user_id for r in same_scope):
        raise HTTPException(409, "This person already holds that responsibility here")
    inherited = policy.idx.project_default(case.project_id, body.responsibility_type)
    source = "case_override" if inherited is not None and not existing else ("manual" if not existing else
                                                                               existing[0].source)
    if body.is_primary:
        for r in same_scope:
            if r.is_primary:
                _end(db, ctx, r, "replaced")
    r = CaseResponsibility(org_id=ctx.org_id, case_id=case.id, user_id=body.user_id,
                           responsibility_type=body.responsibility_type, access_item_id=body.access_item_id,
                           is_primary=body.is_primary, source=source, assigned_by_user_id=ctx.user_id,
                           assigned_at=utcnow(), valid_from=body.valid_from, valid_until=body.valid_until,
                           notes=(body.notes or "").strip() or None, is_active=True)
    db.add(r)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case_responsibility", entity_id=r.id,
                 action="assigned", after={**audit.snapshot(r), "case_ref": case.ref})
    db.add(Notification(org_id=ctx.org_id, user_id=body.user_id,
                        text=f"{ctx.user.name} made you {body.responsibility_type.replace('_', ' ')} for {case.ref}",
                        link=f"/app/cases/{case.ref}"))
    recompute_case(db, case)
    db.commit()
    return _payload(db, ctx, case)


def _row(db: Session, ctx: Ctx, case_id: str, assignment_id: str):
    case = load_case(db, ctx, case_id)
    if not Policy(db, ctx).can_assign(case):
        raise HTTPException(403, "You can view these stakeholders but cannot change their assignments")
    r = get_scoped(db, CaseResponsibility, ctx, assignment_id)
    if r.case_id != case.id:
        raise HTTPException(404, "Not found")
    if not r.is_active:
        raise HTTPException(409, "This assignment has already ended")
    return case, r


@router.patch("/cases/{case_id}/responsibilities/{assignment_id}")
def patch_responsibility(case_id: str, assignment_id: str, body: ResponsibilityPatch, ctx: Ctx = Depends(get_ctx),
                         db: Session = Depends(get_db)):
    case, r = _row(db, ctx, case_id, assignment_id)
    if r.user_id == ctx.user_id:
        raise HTTPException(403, "You cannot change your own responsibility")
    before = audit.snapshot(r)
    changes = body.model_fields_set
    if "is_primary" in changes and body.is_primary is not None:
        r.is_primary = body.is_primary
    if "notes" in changes:
        r.notes = (body.notes or "").strip() or None
    if "valid_until" in changes:
        r.valid_until = body.valid_until
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case_responsibility", entity_id=r.id,
                 action="updated", before=before, after=audit.snapshot(r))
    recompute_case(db, case)
    db.commit()
    return _payload(db, ctx, case)


@router.delete("/cases/{case_id}/responsibilities/{assignment_id}")
def end_responsibility(case_id: str, assignment_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Soft end. If a project default exists the case falls back to it; otherwise the gap becomes visible."""
    case, r = _row(db, ctx, case_id, assignment_id)
    _end(db, ctx, r, "ended")
    recompute_case(db, case)
    db.commit()
    return _payload(db, ctx, case)


# ---------- training log ----------

@router.get("/cases/{case_id}/training")
def list_training(case_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    policy = Policy(db, ctx)
    if not policy.can_view_field("training", case):
        return []
    lk = ser.Lookup(db, ctx.org_id)
    notes = policy.can_view_field("training_notes", case)
    rows = db.execute(scoped(TrainingEntry, ctx).where(TrainingEntry.case_id == case.id)
                      .order_by(TrainingEntry.activity_date.desc(), TrainingEntry.created_at.desc())).scalars()
    return [ser.training_out(e, lk, with_notes=notes) for e in rows]


@router.post("/cases/{case_id}/training", status_code=201)
def record_training(case_id: str, body: TrainingCreate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """Append-only. Recording a session never changes the stage or readiness: only the technical owner's review
    does (training completed != can execute)."""
    case = load_case(db, ctx, case_id)
    policy = Policy(db, ctx)
    if not policy.can_record_training(case):
        raise HTTPException(403, "Only the case's training responsible, technical owner, project manager or a "
                                 "coordinator can record training")
    for sid in body.cited_source_ids:
        s = db.execute(scoped(Source, ctx).where(Source.id == sid)).scalar_one_or_none()
        if s is None or s.case_id != case.id:
            raise HTTPException(422, "Cited source does not belong to this case")
    e = TrainingEntry(org_id=ctx.org_id, case_id=case.id, kind=body.kind, title=body.title.strip(),
                      notes=body.notes.strip(), activity_date=body.activity_date or policy.today,
                      cited_source_ids=body.cited_source_ids, recorded_by_user_id=ctx.user_id,
                      capacity=policy.training_capacity(case))
    db.add(e)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="training_entry", entity_id=e.id,
                 action="recorded", after=audit.snapshot(e))
    db.commit()
    return ser.training_out(e, ser.Lookup(db, ctx.org_id))
