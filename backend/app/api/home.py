"""Role-aware Home: one work queue built from the roles the user actually holds. Every row comes from the same
scoped reads as the rest of the app (visible_cases + field policy); the working context only reorders and filters
sections for presentation."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AccessItem, AuditEvent, Membership, RoleAssignment, Task, TrainingEntry
from ..services import serialize as ser
from ..services.cases import case_rows, task_is_mine
from ..services.permissions import Policy
from ..services.tenancy import Ctx, get_ctx, scoped
from ..services.visibility import visible_cases

router = APIRouter(tags=["home"])
ATTN = ("high", "medium")


def _attention(r):
    return any(x["severity"] in ATTN for x in r["reasons"])


@router.get("/home")
def home(context: str | None = None, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    policy = Policy(db, ctx)
    lk = ser.Lookup(db, ctx.org_id)
    today = policy.today
    rows = case_rows(db, ctx, "all")
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    roles = set(ctx.roles) | ({"employee"} if any(c.employee_user_id == ctx.user_id for c in cases.values()) else set())
    active = context if context in roles else (ctx.working_role if ctx.working_role in roles else None)
    show = {active} if active else roles

    open_tasks = db.execute(scoped(Task, ctx).where(Task.status == "open", Task.case_id.in_(cases))
                            .order_by(Task.due_date)).scalars().all()
    roles_here = {cid: policy.roles_for_case(c) for cid, c in cases.items()}
    my_tasks = [t for t in open_tasks if task_is_mine(t, ctx, roles_here[t.case_id])]
    sections: list[dict] = []

    def add(key, title, description, kind, items, role):
        sections.append({"key": key, "title": title, "description": description, "kind": kind,
                         "items": items, "role": role})

    def mine_where(rtype):
        return [r for r in rows if rtype in r["my_responsibilities"]]

    if show & {"org_admin"}:
        members = db.execute(scoped(Membership, ctx)).scalars().all()
        with_grants = set(db.execute(select(RoleAssignment.user_id).where(
            RoleAssignment.org_id == ctx.org_id, RoleAssignment.is_active.is_(True))).scalars())
        admins = db.execute(select(func.count()).select_from(RoleAssignment).where(
            RoleAssignment.org_id == ctx.org_id, RoleAssignment.role_code == "org_admin",
            RoleAssignment.is_active.is_(True))).scalar_one()
        issues = [{"text": f"{lk.users[m.user_id].name} has no role yet", "link": "/app/settings/people"}
                  for m in members if m.status == "active" and m.user_id not in with_grants]
        issues += [{"text": f"{lk.users[m.user_id].name} is suspended", "link": "/app/settings/people"}
                   for m in members if m.status == "suspended"]
        if admins < 2:
            issues.append({"text": "Only one organization admin: add a second so access can be recovered",
                           "link": "/app/settings/people"})
        add("workspace", "Workspace health",
            f"{sum(m.status == 'active' for m in members)} active members · "
            f"{sum(1 for r in rows if r['ownership_gaps'])} cases with ownership gaps", "notes", issues, "org_admin")
    if show & {"pmo_coordinator", "org_admin"}:
        add("attention", "Needs attention", "High or medium flags, or overdue follow-ups", "cases",
            [r for r in rows if _attention(r) or (r["next_task"] or {}).get("overdue")], "pmo_coordinator")
        add("gaps", "Missing owners", "Required responsibilities nobody holds. Assign them; Graft never fills "
            "them silently.", "cases", [r for r in rows if r["ownership_gaps"]], "pmo_coordinator")
        add("stale", "Stale tracker status", "Tracker not updated within the stale threshold", "cases",
            [r for r in rows if any(x["rule_id"] == "STALE_TRACKER" for x in r["reasons"])], "pmo_coordinator")
    if show & {"project_manager"}:
        pm_projects = ctx.project_ids("project_manager")
        pm_rows = [r for r in rows if cases[r["id"]].project_id in pm_projects] + \
            [r for r in mine_where("project_manager") if cases[r["id"]].project_id not in pm_projects]
        add("portfolio", "My project portfolio", "Cases in the projects you lead", "cases", pm_rows, "project_manager")
        add("pm_risks", "Cases at risk in my projects", "Blockers to coordinate, including missing responsibilities",
            "cases", [r for r in pm_rows if _attention(r) or r["ownership_gaps"]], "project_manager")
    if show & {"line_manager"}:
        add("reports", "My direct reports", "Development, training progress and follow-ups", "cases",
            mine_where("line_manager"), "line_manager")
    if show & {"technical_owner"}:
        to_rows = [r for r in rows if lk.idx.primary(cases[r["id"]], "technical_owner") == ctx.user_id]
        add("reviews", "Technical reviews awaiting me",
            "No review yet, kept open, or conflicting evidence. Only you can record the readiness decision.",
            "cases", [r for r in to_rows if r["review_state"] in ("none", "keep_open")
                      or any(x["rule_id"] == "CLOSURE_CONFLICT" for x in r["reasons"])], "technical_owner")
    if show & {"training_responsible"}:
        tr_rows = mine_where("training_responsible")
        last = dict(db.execute(select(TrainingEntry.case_id, func.max(TrainingEntry.activity_date)).where(
            TrainingEntry.org_id == ctx.org_id).group_by(TrainingEntry.case_id)).all())
        add("training", "My KT and training cases",
            "Assigned employees and their last recorded training activity", "cases",
            [{**r, "note": f"Last activity {ser.iso(last[r['id']])}" if r["id"] in last else "No training recorded yet"}
             for r in tr_rows], "training_responsible")
    if show & {"hr_business_partner"}:
        add("hr", "My employees", "Onboarding milestones for the employees you support", "cases",
            mine_where("hr_business_partner") or [r for r in rows if r["view_level"] == "summary"
                                                  and "hr_business_partner" in roles_here.get(r["id"], set())],
            "hr_business_partner")
    if show & {"access_responsible", "employee"}:
        items = []
        for c in cases.values():
            level = policy.level(c)
            for a in policy.access_items_in_scope(c, list(db.execute(scoped(AccessItem, ctx).where(
                    AccessItem.case_id == c.id)).scalars())):
                if a.state == "confirmed_usable":
                    continue
                tester = policy.can_confirm_access(c, a)
                editor = policy.can_edit_access(c, a) and not policy.is_coordinator()
                if (show & {"access_responsible"} and editor) or (show & {"employee"} and tester):
                    items.append({**ser.access_out(a, lk), "case": {"id": c.id, "ref": c.ref, "employee": c.employee},
                                  "action": "Test and confirm it works" if tester else "Chase approval / provisioning",
                                  "level": level})
        if items:
            add("access", "Access awaiting action",
                "Requested ≠ approved ≠ active ≠ usable. Only the tester's successful test counts.", "access", items,
                "access_responsible" if "access_responsible" in show else "employee")
    if show & {"employee"}:
        add("my_case", "My onboarding", "Your case as the team sees it", "cases",
            [r for r in rows if cases[r["id"]].employee_user_id == ctx.user_id], "employee")
    if show & {"project_member"}:
        add("project_updates", "My projects", "Cases in the projects you contribute to (summary only)", "cases",
            [r for r in rows if cases[r["id"]].project_id in ctx.project_ids("project_member")], "project_member")
    if show & {"auditor"}:
        events = db.execute(scoped(AuditEvent, ctx).order_by(AuditEvent.created_at.desc()).limit(15)).scalars()
        add("audit", "Recent audit activity", "Who changed what, newest first", "audit",
            [{"id": e.id, "actor": lk.user_ref(e.actor_user_id), "entity": e.entity, "action": e.action,
              "created_at": ser.iso(e.created_at)} for e in events], "auditor")

    totals = {
        "cases": len(rows),
        "needs_attention": sum(1 for r in rows if _attention(r)),
        "ownership_gaps": sum(1 for r in rows if r["ownership_gaps"]),
        "my_open_tasks": len(my_tasks),
        "overdue_tasks": sum(1 for t in open_tasks if t.due_date and t.due_date < today),
    }
    return {
        "roles": sorted(roles), "context": active, "totals": totals,
        "my_tasks": [ser.task_out(t, lk, cases.get(t.case_id), today) for t in my_tasks],
        "sections": sections,
    }
