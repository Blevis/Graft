"""The only writer of the tasks table."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .agents import decide_proposal
from ..db import get_db
from ..models import EmployeeCase, Finding, Membership, Notification, Source, Task
from ..models._base import utcnow
from ..schemas.requests import TaskCreate, TaskUpdate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case
from ..services.org_settings import as_of, get_org_settings
from ..services.visibility import sees_all, visible_case_ids, visible_cases
from ..services.tenancy import Ctx, get_ctx, get_scoped, require_roles, scoped

router = APIRouter(tags=["tasks"])


class TaskWithProposal(TaskCreate):
    proposal_id: str | None = None


@router.get("/tasks")
def list_tasks(mine: int = 0, status: str | None = "open", ctx: Ctx = Depends(get_ctx),
               db: Session = Depends(get_db)):
    q = scoped(Task, ctx)
    if not sees_all(ctx):
        q = q.where(Task.case_id.in_(visible_case_ids(ctx)))
    if status in ("open", "done"):
        q = q.where(Task.status == status)
    if mine:
        q = q.where(or_(Task.owner_user_id == ctx.user_id,
                        (Task.owner_user_id.is_(None)) & (Task.owner_role == ctx.role)))
    tasks = db.execute(q.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at)).scalars().all()
    lk = ser.Lookup(db, ctx.org_id)
    today = as_of(get_org_settings(db, ctx.org_id))
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    return [ser.task_out(t, lk, cases.get(t.case_id), today) for t in tasks]


@router.post("/cases/{case_id}/tasks", status_code=201)
def create_task(case_id: str, body: TaskWithProposal, ctx: Ctx = Depends(require_roles("admin", "pmo_coordinator")),
                db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    if not body.owner_user_id and not body.owner_role:
        raise HTTPException(422, "A task needs a named owner or an owner role")
    if body.owner_user_id:
        m = db.execute(select(Membership).where(Membership.org_id == ctx.org_id,
                                                Membership.user_id == body.owner_user_id)).scalar_one_or_none()
        if m is None:
            raise HTTPException(422, "Owner is not a member of this organisation")
    if body.finding_id:
        f = db.execute(scoped(Finding, ctx).where(Finding.id == body.finding_id,
                                                  Finding.case_id == case.id)).scalar_one_or_none()
        if f is None:
            raise HTTPException(422, "Finding does not belong to this case")
    for sid in body.cited_source_ids:
        s = db.execute(scoped(Source, ctx).where(Source.id == sid)).scalar_one_or_none()
        if s is None or s.case_id != case.id:
            raise HTTPException(422, "Cited source does not belong to this case")
    if body.proposal_id is not None:
        decide_proposal(db, ctx, body.proposal_id, case_id=case.id)
    settings = get_org_settings(db, ctx.org_id)
    sla = body.sla_hours or int(settings["default_sla_hours"])
    due = body.due_date or (as_of(settings) + timedelta(days=max(1, round(sla / 24))))
    t = Task(org_id=ctx.org_id, case_id=case.id, finding_id=body.finding_id, title=body.title.strip(),
             owner_user_id=body.owner_user_id, owner_role=None if body.owner_user_id else body.owner_role,
             due_date=due, sla_hours=sla, status="open", cited_source_ids=body.cited_source_ids,
             origin="ai_suggested_edited" if body.proposal_id is not None else body.origin, created_by_user_id=ctx.user_id)
    db.add(t)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id, action="created",
                 after=audit.snapshot(t))
    if t.owner_user_id and t.owner_user_id != ctx.user_id:
        db.add(Notification(org_id=ctx.org_id, user_id=t.owner_user_id,
                            text=f"{ctx.user.name} assigned you: {t.title} ({case.ref})",
                            link=f"/app/cases/{case.ref}"))
    db.commit()
    return ser.task_out(t, ser.Lookup(db, ctx.org_id), case, as_of(settings))


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t = get_scoped(db, Task, ctx, task_id)
    is_owner = t.owner_user_id == ctx.user_id or (t.owner_user_id is None and t.owner_role == ctx.role)
    if not (is_owner or ctx.role == "admin"):
        raise HTTPException(403, "Only the task owner can change its status")
    before = audit.snapshot(t)
    if body.status != t.status:
        t.status = body.status
        t.completed_at = utcnow() if body.status == "done" else None
        db.flush()
        audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id,
                     action=f"status_{body.status}", before=before, after=audit.snapshot(t))
        if t.created_by_user_id != ctx.user_id:
            case = db.get(EmployeeCase, t.case_id)
            db.add(Notification(org_id=ctx.org_id, user_id=t.created_by_user_id,
                                text=f"{ctx.user.name} marked {body.status}: {t.title}",
                                link=f"/app/cases/{case.ref}" if case else None))
    db.commit()
    return ser.task_out(t, ser.Lookup(db, ctx.org_id), db.get(EmployeeCase, t.case_id),
                        as_of(get_org_settings(db, ctx.org_id)))
