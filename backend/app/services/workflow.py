"""Workflow writers: templates, requirement snapshots, task creation with deterministic routing and assignment
history. Called only from human API routes (cases, tasks, import). The AI layer has no import path here
(tests/test_agent_boundaries.py)."""
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CaseRequirement, EmployeeCase, Finding, Membership, Notification, Task, TaskAssignment, WorkflowTemplate,
)
from . import audit
from .org_settings import as_of, get_org_settings
from .responsibilities import ResponsibilityIndex
from .roles import RESPONSIBILITY_TYPES

# Initial templates. Admins version them per org; cases snapshot the version they were created with.
DEFAULT_TEMPLATES = {
    "new_hire": {
        "name": "New hire onboarding", "movement": "new_hire",
        "milestones": [
            {"key": "access_ready", "title": "Required systems confirmed usable by the employee", "kind": "access",
             "applicability": "required", "evidence_expectation": "The employee's own successful test per system",
             "due_offset_days": 5, "assignee_role": "access_responsible"},
            {"key": "kt_plan", "title": "KT plan and training owner agreed", "kind": "milestone",
             "applicability": "required", "evidence_expectation": "Training plan or KT schedule referenced in a source",
             "due_offset_days": 3, "assignee_role": "training_responsible"},
            {"key": "shadowing", "title": "Shadowing observed", "kind": "milestone", "applicability": "optional",
             "evidence_expectation": "Observation of shadowed work", "due_offset_days": 10,
             "assignee_role": "technical_owner"},
            {"key": "supported_execution", "title": "Standard requests handled with support (observed)",
             "kind": "milestone", "applicability": "required",
             "evidence_expectation": "Technical lead's observation of real work", "due_offset_days": 15,
             "assignee_role": "technical_owner"},
            {"key": "complex_scenarios", "title": "Complex scenarios covered (observed)", "kind": "milestone",
             "applicability": "required", "evidence_expectation": "Each complex scenario executed and observed",
             "due_offset_days": 25, "assignee_role": "technical_owner"},
            {"key": "kt_docs", "title": "KT documentation location recorded", "kind": "milestone",
             "applicability": "optional", "evidence_expectation": "Project-owned folder reference",
             "due_offset_days": 5, "assignee_role": "training_responsible"},
        ],
    },
    "project_transfer": {
        "name": "Project transfer (reallocation)", "movement": "reallocation",
        "milestones": [
            {"key": "handover", "title": "Handover from the previous project acknowledged", "kind": "milestone",
             "applicability": "required", "evidence_expectation": "Handover note from the previous project lead",
             "due_offset_days": 2, "assignee_role": "project_manager"},
            {"key": "access_ready", "title": "New project systems confirmed usable by the employee", "kind": "access",
             "applicability": "required", "evidence_expectation": "The employee's own successful test per system",
             "due_offset_days": 3, "assignee_role": "access_responsible"},
            {"key": "domain_kt", "title": "Project domain KT completed", "kind": "milestone",
             "applicability": "required", "evidence_expectation": "KT sessions recorded with observations",
             "due_offset_days": 8, "assignee_role": "training_responsible"},
            {"key": "supported_execution", "title": "Standard requests handled with support (observed)",
             "kind": "milestone", "applicability": "required",
             "evidence_expectation": "Technical lead's observation of real work", "due_offset_days": 12,
             "assignee_role": "technical_owner"},
            {"key": "complex_scenarios", "title": "Complex scenarios covered (observed)", "kind": "milestone",
             "applicability": "optional", "evidence_expectation": "Each complex scenario executed and observed",
             "due_offset_days": 20, "assignee_role": "technical_owner"},
        ],
    },
}
MOVEMENT_TEMPLATE = {"new_hire": "new_hire", "reallocation": "project_transfer"}

# Deterministic routing: which responsibility should own work arising from a finding.
FINDING_ROUTES = {
    "CLOSURE_CONFLICT": "technical_owner",
    "ACCESS_NOT_CONFIRMED": "access_responsible",
    "MISSING_TECH_OWNER": None,  # nobody to route to: coordinator queue
    "MISSING_PROJECT": None,
    "MISSING_MANAGER": None,
    "MISSING_READINESS_DATE": None,
    "STALE_TRACKER": None,
    "UNANSWERED_REQUEST": None,
}
COORDINATOR_QUEUE = "unowned"


def validate_definition(defn: dict) -> dict:
    ms = defn.get("milestones")
    if not isinstance(ms, list) or not ms:
        raise HTTPException(422, "A template needs at least one milestone")
    keys = set()
    out = []
    for i, m in enumerate(ms):
        key = str(m.get("key", "")).strip()
        if not key or not key.replace("_", "").isalnum() or key in keys:
            raise HTTPException(422, f"Milestone {i + 1}: a unique snake_case key is required")
        keys.add(key)
        if m.get("kind", "milestone") not in ("milestone", "access"):
            raise HTTPException(422, f"Milestone {key}: kind must be milestone or access")
        if m.get("applicability", "required") not in ("required", "optional", "not_applicable"):
            raise HTTPException(422, f"Milestone {key}: applicability must be required, optional or not_applicable")
        role = m.get("assignee_role")
        if role is not None and role not in RESPONSIBILITY_TYPES:
            raise HTTPException(422, f"Milestone {key}: assignee_role must be a responsibility type")
        offset = m.get("due_offset_days")
        if offset is not None and (not isinstance(offset, int) or not 0 <= offset <= 365):
            raise HTTPException(422, f"Milestone {key}: due_offset_days must be 0-365")
        title = str(m.get("title", "")).strip()
        if len(title) < 3:
            raise HTTPException(422, f"Milestone {key}: a title is required")
        out.append({"key": key, "title": title[:300], "kind": m.get("kind", "milestone"),
                    "applicability": m.get("applicability", "required"),
                    "evidence_expectation": (m.get("evidence_expectation") or "").strip()[:1000] or None,
                    "due_offset_days": offset, "assignee_role": role})
    return {"milestones": out}


def ensure_default_templates(db: Session, org_id: str) -> None:
    have = set(db.execute(select(WorkflowTemplate.key).where(WorkflowTemplate.org_id == org_id)).scalars())
    for key, t in DEFAULT_TEMPLATES.items():
        if key not in have:
            db.add(WorkflowTemplate(org_id=org_id, key=key, version=1, name=t["name"], movement=t["movement"],
                                    definition=validate_definition({"milestones": t["milestones"]}),
                                    is_current=True, note="Initial template shipped with Graft"))
    db.flush()


def current_template(db: Session, org_id: str, key: str) -> WorkflowTemplate:
    ensure_default_templates(db, org_id)
    t = db.execute(select(WorkflowTemplate).where(WorkflowTemplate.org_id == org_id, WorkflowTemplate.key == key,
                                                  WorkflowTemplate.is_current.is_(True))).scalar_one_or_none()
    if t is None:
        raise HTTPException(422, f"Unknown template '{key}'")
    return t


def apply_template(db: Session, case: EmployeeCase, template: WorkflowTemplate, *, actor_user_id: str | None,
                   create_tasks: bool = True) -> list[CaseRequirement]:
    """Snapshot the template version onto the case: requirements plus, optionally, one routed task per
    applicable milestone. Existing requirements with the same key are left untouched."""
    existing = {r.key for r in db.execute(select(CaseRequirement).where(CaseRequirement.case_id == case.id)).scalars()}
    start = case.start_date or as_of(get_org_settings(db, case.org_id))
    created = []
    for i, m in enumerate(template.definition["milestones"]):
        if m["key"] in existing:
            continue
        due = start + timedelta(days=m["due_offset_days"]) if m.get("due_offset_days") is not None else None
        r = CaseRequirement(org_id=case.org_id, case_id=case.id, key=m["key"], title=m["title"], kind=m["kind"],
                            applicability=m["applicability"], evidence_expectation=m.get("evidence_expectation"),
                            due_date=due, assignee_role=m.get("assignee_role"), position=i,
                            template_id=template.id, changed_by_user_id=actor_user_id)
        db.add(r)
        created.append(r)
    case.template_id = template.id
    db.flush()
    audit.record(db, org_id=case.org_id, actor_user_id=actor_user_id, entity="case", entity_id=case.id,
                 action="template_applied", after={"template": template.key, "version": template.version,
                                                   "requirements": [r.key for r in created]})
    if create_tasks and actor_user_id:
        for r in created:
            if r.applicability == "not_applicable":
                continue
            create_task(db, org_id=case.org_id, case=case, title=f"{r.title}",
                        actor_user_id=actor_user_id, owner_user_id=None, owner_role=None,
                        route_role=r.assignee_role, due_date=r.due_date, requirement_id=r.id, origin="automation")
    return created


def route(db: Session, case: EmployeeCase, role: str | None) -> tuple[str | None, str | None, str | None, str]:
    """(owner_user_id, owner_role, queue, explanation). The responsibility holder if there is exactly one primary;
    otherwise the coordinator queue. Deterministic: same case state, same result."""
    if role is None or role not in RESPONSIBILITY_TYPES:
        return None, "pmo_coordinator", COORDINATOR_QUEUE, "No owning responsibility: coordinator queue"
    idx = ResponsibilityIndex(db, case.org_id, as_of(get_org_settings(db, case.org_id)))
    holder = idx.primary(case, role)
    if holder:
        return holder, None, None, f"Routed to the case's {role.replace('_', ' ')}"
    return None, "pmo_coordinator", COORDINATOR_QUEUE, f"No {role.replace('_', ' ')} assigned: coordinator queue"


def route_for_finding(db: Session, case: EmployeeCase, finding_id: str | None):
    rule = None
    if finding_id:
        f = db.get(Finding, finding_id)
        rule = f.rule_id if f else None
    return route(db, case, FINDING_ROUTES.get(rule))


def create_task(db: Session, *, org_id: str, case: EmployeeCase, title: str, actor_user_id: str,
                owner_user_id: str | None, owner_role: str | None, route_role: str | None = None,
                route_finding: str | None = None, due_date: date | None = None, sla_hours: int | None = None,
                finding_id: str | None = None, cited_source_ids: list[str] | None = None, origin: str = "manual",
                requirement_id: str | None = None, auto_route: bool = False) -> Task:
    settings = get_org_settings(db, org_id)
    queue, why = None, "Assigned by a person"
    if owner_user_id is None and owner_role is None:
        if route_role is not None or auto_route or route_finding is not None:
            owner_user_id, owner_role, queue, why = (route(db, case, route_role) if route_role is not None
                                                     else route_for_finding(db, case, route_finding))
        else:
            raise HTTPException(422, "A task needs a named owner, an owner role, or routing")
    elif owner_user_id is None and owner_role is not None:
        queue = owner_role  # a shared role queue anyone holding that role on the case can claim
    if owner_user_id:
        m = db.execute(select(Membership).where(Membership.org_id == org_id,
                                                Membership.user_id == owner_user_id)).scalar_one_or_none()
        if m is None or m.status != "active":
            raise HTTPException(422, "Owner is not an active member of this organisation")
    sla = sla_hours or int(settings["default_sla_hours"])
    due = due_date or (as_of(settings) + timedelta(days=max(1, round(sla / 24))))
    t = Task(org_id=org_id, case_id=case.id, finding_id=finding_id, title=title.strip(), owner_user_id=owner_user_id,
             owner_role=None if owner_user_id else owner_role, due_date=due, sla_hours=sla, status="open",
             cited_source_ids=cited_source_ids or [], origin=origin, created_by_user_id=actor_user_id,
             requirement_id=requirement_id, queue=None if owner_user_id else queue)
    db.add(t)
    db.flush()
    audit.record(db, org_id=org_id, actor_user_id=actor_user_id, entity="task", entity_id=t.id, action="created",
                 after=audit.snapshot(t))
    action = "queued" if t.queue else ("routed" if why.startswith("Routed") else "created")
    db.add(TaskAssignment(org_id=org_id, task_id=t.id, action=action,
                          to_user_id=owner_user_id, to_role=t.owner_role, queue=t.queue, reason=why,
                          actor_user_id=actor_user_id))
    if t.owner_user_id and t.owner_user_id != actor_user_id:
        db.add(Notification(org_id=org_id, user_id=t.owner_user_id,
                            text=f"New task: {t.title} ({case.ref})", link=f"/app/cases/{case.ref}"))
    return t


def run_reminders(db: Session, org_id: str | None = None) -> dict:
    """Overdue obligations: remind the owner once when a task is overdue, escalate to the org's coordinators once
    when it is overdue by `escalation_working_days`. Waiting tasks are skipped and their due date moves by the
    working days spent waiting. Idempotent (reminded_at / escalated_at). Uses the org clock (as-of in demo orgs)."""
    from ..models import Org, RoleAssignment, TaskPause
    from .sla import add_working_days, task_clock, today, working_days_between

    report = {"reminded": 0, "escalated": 0}
    orgs = db.execute(select(Org.id) if org_id is None else select(Org.id).where(Org.id == org_id)).scalars().all()
    for oid in orgs:
        settings = get_org_settings(db, oid)
        now_day = today(settings)
        coordinators = set(db.execute(select(RoleAssignment.user_id).where(
            RoleAssignment.org_id == oid, RoleAssignment.role_code == "pmo_coordinator",
            RoleAssignment.scope_type == "organization", RoleAssignment.is_active.is_(True))).scalars())
        tasks = db.execute(select(Task).where(Task.org_id == oid, Task.status == "open",
                                              Task.due_date.is_not(None), Task.due_date < now_day)).scalars().all()
        for t in tasks:
            pauses = list(db.execute(select(TaskPause).where(TaskPause.task_id == t.id)
                                     .order_by(TaskPause.paused_at)).scalars())
            clock = task_clock(t, pauses, settings)
            if clock["waiting"]:
                continue
            due = add_working_days(t.due_date, clock["paused_working_days"], settings)
            if due >= now_day:
                continue
            case = db.get(EmployeeCase, t.case_id)
            link = f"/app/cases/{case.ref}" if case else None
            if t.reminded_at is None:
                targets = {t.owner_user_id} if t.owner_user_id else coordinators
                for uid in targets - {None}:
                    db.add(Notification(org_id=oid, user_id=uid, link=link,
                                        text=f"Overdue since {due.isoformat()}: {t.title}"))
                t.reminded_at = _utc_now()
                audit.record(db, org_id=oid, actor_user_id=None, entity="task", entity_id=t.id, action="reminded",
                             after={"due": due.isoformat(), "notified": sorted(targets - {None})})
                report["reminded"] += 1
            if t.escalated_at is None and working_days_between(due, now_day, settings) >= int(
                    settings.get("escalation_working_days", 2)):
                for uid in coordinators:
                    db.add(Notification(org_id=oid, user_id=uid, link=link,
                                        text=f"Escalated: '{t.title}' is overdue by "
                                             f"{working_days_between(due, now_day, settings)} working days"))
                t.escalated_at = _utc_now()
                audit.record(db, org_id=oid, actor_user_id=None, entity="task", entity_id=t.id, action="escalated",
                             after={"due": due.isoformat(), "notified": sorted(coordinators)})
                report["escalated"] += 1
    db.commit()
    return report


def _utc_now():
    from ..models._base import utcnow
    return utcnow()
