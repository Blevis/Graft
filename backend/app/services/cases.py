"""Case queries: list rows, record page payload, timeline."""
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..ai import client
from ..models import AccessItem, EmployeeCase, Finding, KnowledgeRef, Review, Task
from . import serialize as ser
from .evidence import current_claims, latest_attempt, latest_sources
from .org_settings import as_of, get_org_settings
from .tenancy import Ctx

ATTENTION = {"high", "medium"}


def load_case(db: Session, ctx: Ctx, id_or_ref: str) -> EmployeeCase:
    case = db.execute(
        select(EmployeeCase).where(
            EmployeeCase.org_id == ctx.org_id, or_(EmployeeCase.id == id_or_ref, EmployeeCase.ref == id_or_ref)
        )
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(404, "Not found")
    return case


def reviews_for(db: Session, org_id: str, case_id: str) -> list[Review]:
    return list(db.execute(
        select(Review).where(Review.org_id == org_id, Review.case_id == case_id).order_by(Review.created_at.desc())
    ).scalars())


def case_rows(db: Session, ctx: Ctx, view: str = "all", q: str | None = None) -> list[dict]:
    settings = get_org_settings(db, ctx.org_id)
    today = as_of(settings)
    lk = ser.Lookup(db, ctx.org_id)
    cases = db.execute(
        select(EmployeeCase).where(EmployeeCase.org_id == ctx.org_id).order_by(EmployeeCase.ref)).scalars().all()
    findings: dict[str, list] = {}
    for f in db.execute(select(Finding).where(Finding.org_id == ctx.org_id)).scalars():
        findings.setdefault(f.case_id, []).append(f)
    tasks: dict[str, list[Task]] = {}
    for t in db.execute(select(Task).where(Task.org_id == ctx.org_id, Task.status == "open")
                        .order_by(Task.due_date)).scalars():
        tasks.setdefault(t.case_id, []).append(t)
    latest: dict[str, Review] = {}
    for r in db.execute(select(Review).where(Review.org_id == ctx.org_id).order_by(Review.created_at)).scalars():
        latest[r.case_id] = r

    rows = []
    for c in cases:
        fs = sorted(findings.get(c.id, []), key=lambda f: ser.SEVERITY_ORDER.get(f.severity, 9))
        open_tasks = tasks.get(c.id, [])
        review = latest.get(c.id)
        overdue = any(t.due_date and t.due_date < today for t in open_tasks)
        rule_ids = {f.rule_id for f in fs}
        mine = ctx.user_id in {lk.tech_owner_id(c), c.line_manager_user_id, c.employee_user_id} or any(
            t.owner_user_id == ctx.user_id or (t.owner_user_id is None and t.owner_role == ctx.role)
            for t in open_tasks)
        if q:
            needle = q.lower()
            if needle not in c.employee.lower() and needle not in c.ref.lower():
                continue
        include = {
            "all": True,
            "needs_attention": any(f.severity in ATTENTION for f in fs) or overdue,
            "mine": mine,
            "stale": "STALE_TRACKER" in rule_ids,
            "access_blocked": "ACCESS_NOT_CONFIRMED" in rule_ids,
        }.get(view, True)
        if not include:
            continue
        nt = open_tasks[0] if open_tasks else None
        rows.append({
            "id": c.id, "ref": c.ref, "employee": c.employee,
            "project": lk.projects[c.project_id].name if c.project_id in lk.projects else None,
            "tracker_status": c.tracker_status,
            "tracker_age_days": (today - c.tracker_updated_at).days if c.tracker_updated_at else None,
            "stage": review.observed_stage if review else None,
            "reasons": [{"rule_id": f.rule_id, "severity": f.severity, "message": f.message} for f in fs],
            "next_task": {
                "id": nt.id, "title": nt.title, "due_date": ser.iso(nt.due_date),
                "owner_name": (lk.user_ref(nt.owner_user_id) or {}).get("name") or nt.owner_role,
                "overdue": bool(nt.due_date and nt.due_date < today),
            } if nt else None,
            "open_task_count": len(open_tasks),
            "review_state": review.disposition if review else "none",
        })
    return rows


def case_detail(db: Session, ctx: Ctx, case: EmployeeCase) -> dict:
    settings = get_org_settings(db, ctx.org_id)
    today = as_of(settings)
    lk = ser.Lookup(db, ctx.org_id)
    sources = latest_sources(db, ctx.org_id, case_id=case.id)
    claims, rejected, runs = current_claims(db, sources)
    findings = sorted(
        db.execute(select(Finding).where(Finding.org_id == ctx.org_id, Finding.case_id == case.id)).scalars(),
        key=lambda f: ser.SEVERITY_ORDER.get(f.severity, 9))
    tasks = db.execute(select(Task).where(Task.org_id == ctx.org_id, Task.case_id == case.id)
                       .order_by(Task.status.desc(), Task.created_at.desc())).scalars().all()
    access = db.execute(select(AccessItem).where(AccessItem.org_id == ctx.org_id, AccessItem.case_id == case.id)
                        .order_by(AccessItem.system)).scalars().all()
    reviews = reviews_for(db, ctx.org_id, case.id)
    knowledge = db.execute(select(KnowledgeRef).where(
        KnowledgeRef.org_id == ctx.org_id, KnowledgeRef.project_id == case.project_id)).scalars().all() \
        if case.project_id else []

    per_source = []
    for s in sources:
        run = runs.get(s.id)
        attempt = latest_attempt(db, s)
        per_source.append({
            "source_id": s.id,
            "run": ser.run_out(run) if run else None,
            "last_attempt": ser.run_out(attempt) if attempt else None,
        })
    used = [r for r in runs.values()]
    modes = {r.mode for r in used}
    mode = "unavailable" if not used else ("live" if modes == {"live"} else
                                          "replay" if modes == {"replay"} else sorted(modes)[0])
    latest_run = max(used, key=lambda r: ser.utc(r.created_at)) if used else None
    tech_owner_id = lk.tech_owner_id(case)
    return {
        "case": ser.case_out(case, lk, today, reviews[0] if reviews else None),
        "sources": [ser.source_out(s) for s in sources],
        "claims": [ser.claim_out(c) for c in claims],
        "rejected": [ser.rejected_out(r) for r in rejected],
        "findings": [ser.finding_out(f) for f in findings],
        "tasks": [ser.task_out(t, lk, today=today) for t in tasks],
        "access_items": [ser.access_out(a) for a in access],
        "latest_review": ser.review_out(reviews[0], lk) if reviews else None,
        "reviews": [ser.review_out(r, lk) for r in reviews],
        "knowledge": [ser.knowledge_out(k, lk) for k in knowledge],
        "analysis": {
            "mode": mode,
            "model": latest_run.model if latest_run else None,
            "prompt_version": latest_run.prompt_version if latest_run else None,
            "last_run_at": ser.iso(latest_run.created_at) if latest_run else None,
            "runs": [ser.run_out(r) for r in used],
            "per_source": per_source,
            "ai_enabled": bool(settings["ai_enabled"]),
            "ai_configured": client.is_configured(),
        },
        "permissions": {
            "can_create_task": ctx.role in ("admin", "pmo_coordinator"),
            "can_analyze": ctx.role in ("admin", "pmo_coordinator"),
            "can_review": ctx.user_id == tech_owner_id,
            "can_edit_access": ctx.role in ("admin", "pmo_coordinator"),
            "can_confirm_access": ctx.user_id == case.employee_user_id,
        },
    }


def timeline(db: Session, ctx: Ctx, case: EmployeeCase) -> list[dict]:
    lk = ser.Lookup(db, ctx.org_id)
    events: list[dict] = []
    sources = latest_sources(db, ctx.org_id, case_id=case.id)
    for s in sources:
        events.append({"id": f"src-{s.id}", "type": "source_received",
                       "at": ser.iso(s.date) or ser.iso(s.created_at),
                       "title": f"{s.ref + ' · ' if s.ref else ''}{s.title or s.kind}",
                       "actor": s.author_role, "ref": {"entity": "source", "id": s.id}})
    _, _, runs = current_claims(db, sources)
    for r in runs.values():
        events.append({"id": f"run-{r.id}", "type": "analysis_run", "at": ser.iso(r.created_at),
                       "title": f"Evidence analysed ({r.mode}, {r.status})", "actor": r.model,
                       "ref": {"entity": "source", "id": r.source_id}})
    for f in db.execute(select(Finding).where(Finding.org_id == ctx.org_id, Finding.case_id == case.id)).scalars():
        events.append({"id": f"fnd-{f.id}", "type": "finding_raised", "at": ser.iso(f.created_at),
                       "title": f.message, "actor": "Rules " + f.rule_version,
                       "ref": {"entity": "finding", "id": f.id}})
    for t in db.execute(select(Task).where(Task.org_id == ctx.org_id, Task.case_id == case.id)).scalars():
        creator = lk.user_ref(t.created_by_user_id)
        events.append({"id": f"tsk-{t.id}", "type": "task_created", "at": ser.iso(t.created_at),
                       "title": f"Task created: {t.title}", "actor": creator["name"] if creator else None,
                       "ref": {"entity": "task", "id": t.id}})
        if t.completed_at:
            owner = lk.user_ref(t.owner_user_id)
            events.append({"id": f"tsd-{t.id}", "type": "task_done", "at": ser.iso(t.completed_at),
                           "title": f"Task done: {t.title}", "actor": owner["name"] if owner else t.owner_role,
                           "ref": {"entity": "task", "id": t.id}})
    for r in reviews_for(db, ctx.org_id, case.id):
        reviewer = lk.user_ref(r.reviewer_user_id)
        events.append({"id": f"rev-{r.id}", "type": "review_saved", "at": ser.iso(r.created_at),
                       "title": f"Technical review: {r.disposition.replace('_', ' ')} — {r.scope}",
                       "actor": reviewer["name"] if reviewer else None, "ref": {"entity": "review", "id": r.id}})
    return sorted(events, key=lambda e: e["at"] or "", reverse=True)
