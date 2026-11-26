"""The only route module that writes tasks (creation goes through services/workflow.create_task).

Shared queues: a task with an owner role but no named owner sits in that role's queue; anyone holding the role for
the case may claim it. Unroutable work lands in the coordinator queue ("unowned"). Reassignment is limited to
coordinators, the case's project manager and the current owner (who may only hand it back to a role queue). Every
ownership change is appended to task_assignments and audited. Pausing records an explicit waiting reason and stops
the working-time clock until resumed."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents import decide_proposal
from ..db import get_db
from ..models import (
    CaseRequirement, EmployeeCase, Finding, Membership, Notification, Review, Source, Task, TaskAssignment, TaskPause,
)
from ..models._base import utcnow
from ..schemas.requests import TaskCreate, TaskPauseBody, TaskReassign, TaskUpdate
from ..services import audit
from ..services import serialize as ser
from ..services.cases import load_case, task_is_mine
from ..services.org_settings import get_org_settings
from ..services.permissions import ACCESS_ONLY, Policy
from ..services.readiness import derive, requirement_status
from ..services.sla import task_clock, today as org_today
from ..services.tenancy import Ctx, get_ctx, get_scoped, scoped
from ..services.visibility import visible_cases
from ..services.workflow import COORDINATOR_QUEUE, create_task as create_task_record

router = APIRouter(tags=["tasks"])
QUEUES = {
    "mine": "My tasks",
    "claimable": "Shared queues I can claim from",
    "unowned": "Unowned (coordinator queue)",
    "overdue": "Overdue",
    "waiting": "Waiting",
    "review_ready": "Ready for technical review",
}


class TaskWithProposal(TaskCreate):
    proposal_id: str | None = None


def _pauses(db: Session, org_id: str, task_ids) -> dict[str, list[TaskPause]]:
    out: dict[str, list[TaskPause]] = {}
    if not task_ids:
        return out
    for p in db.execute(select(TaskPause).where(TaskPause.org_id == org_id, TaskPause.task_id.in_(list(task_ids)))
                        .order_by(TaskPause.paused_at)).scalars():
        out.setdefault(p.task_id, []).append(p)
    return out


def _visible_tasks(db: Session, ctx: Ctx, status: str | None = "open"):
    """(tasks the caller may see, cases by id, policy, roles per case). Access-only / task-only viewers see only
    their own tasks on a case."""
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    q = scoped(Task, ctx).where(Task.case_id.in_(cases))
    if status in ("open", "done"):
        q = q.where(Task.status == status)
    tasks = db.execute(q.order_by(Task.due_date.is_(None), Task.due_date, Task.created_at)).scalars().all()
    policy = Policy(db, ctx)
    roles_here = {cid: policy.roles_for_case(c) for cid, c in cases.items()}
    out = []
    for t in tasks:
        level = policy.level(cases[t.case_id])
        if level in (None, ACCESS_ONLY, "task_only") and not task_is_mine(t, ctx, roles_here[t.case_id]):
            continue
        out.append(t)
    return out, cases, policy, roles_here


def _out(db: Session, ctx: Ctx, tasks, cases) -> list[dict]:
    lk = ser.Lookup(db, ctx.org_id)
    settings = get_org_settings(db, ctx.org_id)
    today = org_today(settings)
    pauses = _pauses(db, ctx.org_id, [t.id for t in tasks])
    return [ser.task_out(t, lk, cases.get(t.case_id), today, clock=task_clock(t, pauses.get(t.id, []), settings))
            for t in tasks]


@router.get("/tasks")
def list_tasks(mine: int = 0, status: str | None = "open", ctx: Ctx = Depends(get_ctx),
               db: Session = Depends(get_db)):
    tasks, cases, _, roles_here = _visible_tasks(db, ctx, status)
    if mine:
        tasks = [t for t in tasks if task_is_mine(t, ctx, roles_here[t.case_id])]
    return _out(db, ctx, tasks, cases)


@router.get("/queues")
def queues(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return [{"key": k, "label": v, "count": len(_queue(db, ctx, k)["items"])} for k, v in QUEUES.items()
            if k != "unowned" or ctx.org_roles & {"org_admin", "pmo_coordinator"}]


@router.get("/queues/{key}")
def queue(key: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    if key not in QUEUES:
        raise HTTPException(404, "Unknown queue")
    return _queue(db, ctx, key)


def _queue(db: Session, ctx: Ctx, key: str) -> dict:
    """Server-owned saved filters. Every item is drawn from the caller's visible tasks/cases."""
    tasks, cases, policy, roles_here = _visible_tasks(db, ctx)
    coordinator = policy.is_coordinator()
    if key == "review_ready":
        rows = []
        reviews: dict[str, list[Review]] = {}
        for r in db.execute(scoped(Review, ctx).where(Review.case_id.in_(cases))).scalars():
            reviews.setdefault(r.case_id, []).append(r)
        reqs: dict[str, list[CaseRequirement]] = {}
        for r in db.execute(scoped(CaseRequirement, ctx).where(CaseRequirement.case_id.in_(cases))).scalars():
            reqs.setdefault(r.case_id, []).append(r)
        from ..models import AccessItem
        access: dict[str, list] = {}
        for a in db.execute(scoped(AccessItem, ctx).where(AccessItem.case_id.in_(cases))).scalars():
            access.setdefault(a.case_id, []).append(a)
        for cid, c in sorted(cases.items(), key=lambda kv: kv[1].ref):
            if not (coordinator or policy.can_review(c)):
                continue
            st = derive(reviews.get(cid, []))
            req = [r for r in reqs.get(cid, []) if r.applicability == "required"]
            if st.status == "signed_off" or not req:
                continue
            if all(requirement_status(r, st, access.get(cid, []))["status"] == "satisfied" for r in req):
                rows.append({"id": c.id, "ref": c.ref, "employee": c.employee, "readiness": st.status})
        return {"key": key, "label": QUEUES[key], "kind": "cases", "items": rows}
    today = org_today(policy.settings)
    pauses = _pauses(db, ctx.org_id, [t.id for t in tasks])
    pick = {
        "mine": lambda t: t.owner_user_id == ctx.user_id,
        "claimable": lambda t: t.owner_user_id is None and task_is_mine(t, ctx, roles_here[t.case_id])
        and t.queue != COORDINATOR_QUEUE,
        "unowned": lambda t: coordinator and t.owner_user_id is None and t.queue == COORDINATOR_QUEUE,
        "overdue": lambda t: bool(t.due_date and t.due_date < today) and not _waiting(pauses.get(t.id)),
        "waiting": lambda t: _waiting(pauses.get(t.id)),
    }[key]
    chosen = [t for t in tasks if pick(t)]
    return {"key": key, "label": QUEUES[key], "kind": "tasks", "items": _out(db, ctx, chosen, cases)}


def _waiting(ps) -> bool:
    return bool(ps) and ps[-1].resumed_at is None


@router.post("/cases/{case_id}/tasks", status_code=201)
def create_task(case_id: str, body: TaskWithProposal, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    if not Policy(db, ctx).can_create_task(case):
        raise HTTPException(403, "You can view this case but cannot assign follow-ups on it")
    if body.finding_id:
        f = db.execute(scoped(Finding, ctx).where(Finding.id == body.finding_id,
                                                  Finding.case_id == case.id)).scalar_one_or_none()
        if f is None:
            raise HTTPException(422, "Finding does not belong to this case")
    if body.requirement_id:
        r = db.execute(scoped(CaseRequirement, ctx).where(CaseRequirement.id == body.requirement_id,
                                                          CaseRequirement.case_id == case.id)).scalar_one_or_none()
        if r is None:
            raise HTTPException(422, "Requirement does not belong to this case")
    for sid in body.cited_source_ids:
        s = db.execute(scoped(Source, ctx).where(Source.id == sid)).scalar_one_or_none()
        if s is None or s.case_id != case.id:
            raise HTTPException(422, "Cited source does not belong to this case")
    if not body.owner_user_id and not body.owner_role and not (body.route or body.finding_id):
        raise HTTPException(422, "A task needs a named owner or an owner role (or route it)")
    if body.proposal_id is not None:
        decide_proposal(db, ctx, body.proposal_id, case_id=case.id)
    t = create_task_record(
        db, org_id=ctx.org_id, case=case, title=body.title, actor_user_id=ctx.user_id,
        owner_user_id=body.owner_user_id, owner_role=body.owner_role,
        route_finding=body.finding_id if not (body.owner_user_id or body.owner_role) else None,
        auto_route=body.route, due_date=body.due_date, sla_hours=body.sla_hours, finding_id=body.finding_id,
        cited_source_ids=body.cited_source_ids, requirement_id=body.requirement_id,
        origin="ai_suggested_edited" if body.proposal_id is not None else body.origin)
    db.commit()
    return _out(db, ctx, [t], {case.id: case})[0]


def _task_case(db: Session, ctx: Ctx, task_id: str) -> tuple[Task, EmployeeCase, Policy]:
    t = get_scoped(db, Task, ctx, task_id)
    case = load_case(db, ctx, t.case_id)
    return t, case, Policy(db, ctx)


def _history(db: Session, ctx: Ctx, t: Task, action: str, *, frm, to_user=None, to_role=None, queue=None,
             reason=None) -> None:
    db.add(TaskAssignment(org_id=ctx.org_id, task_id=t.id, action=action, from_user_id=frm, to_user_id=to_user,
                          to_role=to_role, queue=queue, reason=reason, actor_user_id=ctx.user_id))


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t, case, policy = _task_case(db, ctx, task_id)
    is_owner = task_is_mine(t, ctx, policy.roles_for_case(case))
    if not (is_owner or "org_admin" in ctx.org_roles):
        raise HTTPException(403, "Only the task owner can change its status")
    before = audit.snapshot(t)
    if body.status != t.status:
        t.status = body.status
        t.completed_at = utcnow() if body.status == "done" else None
        if body.status == "done":  # completing ends any waiting interval
            for p in _pauses(db, ctx.org_id, [t.id]).get(t.id, []):
                if p.resumed_at is None:
                    p.resumed_at, p.resumed_by_user_id = utcnow(), ctx.user_id
        db.flush()
        audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id,
                     action=f"status_{body.status}", before=before, after=audit.snapshot(t))
        if t.created_by_user_id != ctx.user_id:
            db.add(Notification(org_id=ctx.org_id, user_id=t.created_by_user_id,
                                text=f"{ctx.user.name} marked {body.status}: {t.title}", link=f"/app/cases/{case.ref}"))
    db.commit()
    return _out(db, ctx, [t], {case.id: case})[0]


@router.post("/tasks/{task_id}/claim")
def claim(task_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t, case, policy = _task_case(db, ctx, task_id)
    if t.status != "open" or t.owner_user_id is not None:
        raise HTTPException(409, "Only an open, unowned task can be claimed")
    if not (task_is_mine(t, ctx, policy.roles_for_case(case)) or
            (t.queue == COORDINATOR_QUEUE and policy.is_coordinator())):
        raise HTTPException(403, "You do not hold the role this task is queued for")
    before = audit.snapshot(t)
    _history(db, ctx, t, "claimed", frm=None, to_user=ctx.user_id, reason=f"claimed from {t.queue or t.owner_role}")
    t.owner_user_id, t.owner_role, t.queue = ctx.user_id, None, None
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id, action="claimed",
                 before=before, after=audit.snapshot(t))
    db.commit()
    return _out(db, ctx, [t], {case.id: case})[0]


@router.post("/tasks/{task_id}/reassign")
def reassign(task_id: str, body: TaskReassign, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t, case, policy = _task_case(db, ctx, task_id)
    if t.status != "open":
        raise HTTPException(409, "Only open tasks can be reassigned")
    if bool(body.owner_user_id) == bool(body.owner_role):
        raise HTTPException(422, "Reassign to exactly one person or one role queue")
    is_owner = t.owner_user_id == ctx.user_id
    if not (policy.can_assign(case) or (is_owner and body.owner_role)):
        raise HTTPException(403, "Only a coordinator or the case's project manager can reassign this task; "
                                 "as its owner you may hand it back to a role queue")
    if body.owner_user_id:
        m = db.execute(select(Membership).where(Membership.org_id == ctx.org_id,
                                                Membership.user_id == body.owner_user_id)).scalar_one_or_none()
        if m is None or m.status != "active":
            raise HTTPException(422, "New owner is not an active member of this organisation")
    before = audit.snapshot(t)
    _history(db, ctx, t, "reassigned", frm=t.owner_user_id, to_user=body.owner_user_id, to_role=body.owner_role,
             queue=body.owner_role, reason=body.reason.strip())
    t.owner_user_id = body.owner_user_id
    t.owner_role = body.owner_role if not body.owner_user_id else None
    t.queue = body.owner_role if not body.owner_user_id else None
    t.reminded_at = t.escalated_at = None
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id,
                 action="reassigned", before=before, after={**audit.snapshot(t), "reason": body.reason.strip()})
    if body.owner_user_id and body.owner_user_id != ctx.user_id:
        db.add(Notification(org_id=ctx.org_id, user_id=body.owner_user_id,
                            text=f"{ctx.user.name} reassigned to you: {t.title} ({case.ref})",
                            link=f"/app/cases/{case.ref}"))
    db.commit()
    return _out(db, ctx, [t], {case.id: case})[0]


def _pause_guard(t: Task, case: EmployeeCase, policy: Policy, ctx: Ctx) -> None:
    if t.status != "open":
        raise HTTPException(409, "Only open tasks can wait")
    if not (task_is_mine(t, ctx, policy.roles_for_case(case)) or policy.is_coordinator()):
        raise HTTPException(403, "Only the task owner or a coordinator can pause or resume it")


@router.post("/tasks/{task_id}/pause")
def pause(task_id: str, body: TaskPauseBody, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t, case, policy = _task_case(db, ctx, task_id)
    _pause_guard(t, case, policy, ctx)
    if _waiting(_pauses(db, ctx.org_id, [t.id]).get(t.id)):
        raise HTTPException(409, "Already waiting")
    p = TaskPause(org_id=ctx.org_id, task_id=t.id, reason=body.reason.strip(), paused_at=utcnow(),
                  paused_by_user_id=ctx.user_id)
    db.add(p)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id, action="paused",
                 after={"reason": p.reason})
    db.commit()
    return _out(db, ctx, [t], {case.id: case})[0]


@router.post("/tasks/{task_id}/resume")
def resume(task_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t, case, policy = _task_case(db, ctx, task_id)
    _pause_guard(t, case, policy, ctx)
    ps = _pauses(db, ctx.org_id, [t.id]).get(t.id) or []
    if not _waiting(ps):
        raise HTTPException(409, "Not waiting")
    ps[-1].resumed_at, ps[-1].resumed_by_user_id = utcnow(), ctx.user_id
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="task", entity_id=t.id, action="resumed",
                 after={"reason": ps[-1].reason})
    db.commit()
    return _out(db, ctx, [t], {case.id: case})[0]


@router.get("/tasks/{task_id}/history")
def history(task_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    t, case, policy = _task_case(db, ctx, task_id)
    if policy.level(case) in (ACCESS_ONLY, "task_only") and not task_is_mine(t, ctx, policy.roles_for_case(case)):
        raise HTTPException(404, "Not found")
    lk = ser.Lookup(db, ctx.org_id)
    rows = db.execute(select(TaskAssignment).where(TaskAssignment.org_id == ctx.org_id, TaskAssignment.task_id == t.id)
                      .order_by(TaskAssignment.created_at)).scalars()
    pauses = _pauses(db, ctx.org_id, [t.id]).get(t.id, [])
    return {"assignments": [{"action": a.action, "from": lk.user_ref(a.from_user_id), "to": lk.user_ref(a.to_user_id),
                             "to_role": a.to_role, "queue": a.queue, "reason": a.reason,
                             "by": lk.user_ref(a.actor_user_id), "at": ser.iso(a.created_at)} for a in rows],
            "pauses": [{"reason": p.reason, "paused_at": ser.iso(p.paused_at), "resumed_at": ser.iso(p.resumed_at),
                        "by": lk.user_ref(p.paused_by_user_id)} for p in pauses]}
