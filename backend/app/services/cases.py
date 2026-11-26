"""Case queries: list rows, record page payload, timeline."""
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..ai import client
from ..models import (
    AccessItem, CaseRequirement, CaseResponsibility, EmployeeCase, Finding, KnowledgeRef, Review, Source, Task,
    TrainingEntry,
)
from . import serialize as ser
from .evidence import current_claims, latest_attempt, latest_sources
from .org_settings import as_of, get_org_settings
from .permissions import ACCESS_ONLY, EMPLOYEE, FULL, RESTRICTED_SECTIONS, SUMMARY, TASK_ONLY, Policy

MINIMAL = (ACCESS_ONLY, TASK_ONLY)
from .readiness import derive, reassessment, requirement_status
from .job_status import case_status
from .tenancy import Ctx
from .visibility import visible_cases

ATTENTION = {"high", "medium"}


def load_case(db: Session, ctx: Ctx, id_or_ref: str) -> EmployeeCase:
    """The single entry point for one case: org scoping + per-role visibility. Hidden = 404."""
    case = db.execute(
        visible_cases(ctx).where(or_(EmployeeCase.id == id_or_ref, EmployeeCase.ref == id_or_ref))
    ).scalar_one_or_none()
    if case is None:
        raise HTTPException(404, "Not found")
    return case


def reviews_for(db: Session, org_id: str, case_id: str) -> list[Review]:
    return list(db.execute(
        select(Review).where(Review.org_id == org_id, Review.case_id == case_id).order_by(Review.created_at.desc())
    ).scalars())


def task_is_mine(t: Task, ctx: Ctx, roles_here: set[str]) -> bool:
    """A task is mine if it names me, or names a role I hold for that case (org grant or responsibility)."""
    if t.owner_user_id:
        return t.owner_user_id == ctx.user_id
    return bool(t.owner_role) and t.owner_role in (set(ctx.org_roles) | roles_here)


def case_rows(db: Session, ctx: Ctx, view: str = "all", q: str | None = None) -> list[dict]:
    settings = get_org_settings(db, ctx.org_id)
    today = as_of(settings)
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    required = list(settings.get("required_responsibilities") or [])
    cases = db.execute(visible_cases(ctx).order_by(EmployeeCase.ref)).scalars().all()
    findings: dict[str, list] = {}
    for f in db.execute(select(Finding).where(Finding.org_id == ctx.org_id)).scalars():
        findings.setdefault(f.case_id, []).append(f)
    tasks: dict[str, list[Task]] = {}
    for t in db.execute(select(Task).where(Task.org_id == ctx.org_id, Task.status == "open")
                        .order_by(Task.due_date)).scalars():
        tasks.setdefault(t.case_id, []).append(t)
    latest: dict[str, Review] = {}
    by_case: dict[str, list[Review]] = {}
    for r in db.execute(select(Review).where(Review.org_id == ctx.org_id).order_by(Review.created_at)).scalars():
        latest[r.case_id] = r
        by_case.setdefault(r.case_id, []).append(r)

    rows = []
    for c in cases:
        level = policy.level(c)
        if level is None:
            continue
        held = policy.responsibilities_held(c)
        roles_here = policy.roles_for_case(c)
        fs = sorted(findings.get(c.id, []), key=lambda f: ser.SEVERITY_ORDER.get(f.severity, 9))
        open_tasks = tasks.get(c.id, [])
        if level in MINIMAL:
            fs = [f for f in fs if f.rule_id == "ACCESS_NOT_CONFIRMED"] if level == ACCESS_ONLY else []
            open_tasks = [t for t in open_tasks if task_is_mine(t, ctx, roles_here)]
        review = latest.get(c.id)
        overdue = any(t.due_date and t.due_date < today for t in open_tasks)
        rule_ids = {f.rule_id for f in fs}
        gaps = lk.idx.gaps(c, required)
        mine = bool(held) or c.employee_user_id == ctx.user_id or any(
            task_is_mine(t, ctx, roles_here) for t in open_tasks)
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
            "missing_owner": bool(gaps),
        }.get(view, True)
        if not include:
            continue
        nt = open_tasks[0] if open_tasks else None
        tracker = level not in MINIMAL
        st = derive(by_case.get(c.id, []))
        rows.append({
            "id": c.id, "ref": c.ref, "employee": c.employee,
            "project": lk.projects[c.project_id].name if c.project_id in lk.projects else None,
            "tracker_status": c.tracker_status if tracker else None,
            "tracker_age_days": (today - c.tracker_updated_at).days if c.tracker_updated_at and tracker else None,
            "stage": (review.observed_stage or ("validated" if st.status == "signed_off" else None))
            if review and tracker else None,
            "reasons": [{"rule_id": f.rule_id, "severity": f.severity, "message": f.message} for f in fs],
            "next_task": {
                "id": nt.id, "title": nt.title, "due_date": ser.iso(nt.due_date),
                "owner_name": (lk.user_ref(nt.owner_user_id) or {}).get("name") or nt.owner_role,
                "overdue": bool(nt.due_date and nt.due_date < today),
            } if nt else None,
            "open_task_count": len(open_tasks),
            "review_state": (review.disposition if review else "none") if tracker else "none",
            "readiness": st.status if tracker else None,
            "validated_milestones": sorted(st.validated) if tracker else [],
            "ownership_gaps": gaps if tracker else [],
            "my_responsibilities": sorted(held),
            "view_level": level,
        })
    return rows


def case_detail(db: Session, ctx: Ctx, case: EmployeeCase) -> dict:
    """The record page, shaped by the caller's view level before anything leaves the server."""
    settings = get_org_settings(db, ctx.org_id)
    today = as_of(settings)
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    level = policy.level(case) or ACCESS_ONLY
    evidence = level in (FULL, EMPLOYEE)
    sources = latest_sources(db, ctx.org_id, case_id=case.id) if evidence else []
    if level == TASK_ONLY:  # exactly the sources the caller's own tasks cite
        cited_by_mine = policy.task_cited_source_ids(case)
        sources = [s for s in latest_sources(db, ctx.org_id, case_id=case.id) if s.id in cited_by_mine]
    claims, rejected, runs = current_claims(db, sources) if evidence or level == TASK_ONLY else ([], [], {})
    findings = sorted(
        db.execute(select(Finding).where(Finding.org_id == ctx.org_id, Finding.case_id == case.id)).scalars(),
        key=lambda f: ser.SEVERITY_ORDER.get(f.severity, 9)) if level not in MINIMAL else []
    tasks = db.execute(select(Task).where(Task.org_id == ctx.org_id, Task.case_id == case.id)
                       .order_by(Task.status.desc(), Task.created_at.desc())).scalars().all()
    roles_here = policy.roles_for_case(case)
    if level in MINIMAL:
        tasks = [t for t in tasks if task_is_mine(t, ctx, roles_here)]
    all_access = db.execute(select(AccessItem).where(AccessItem.org_id == ctx.org_id, AccessItem.case_id == case.id)
                            .order_by(AccessItem.system)).scalars().all()
    access = policy.access_items_in_scope(case, list(all_access))
    reviews = reviews_for(db, ctx.org_id, case.id) if level not in MINIMAL else []
    knowledge = db.execute(select(KnowledgeRef).where(
        KnowledgeRef.org_id == ctx.org_id, KnowledgeRef.project_id == case.project_id)).scalars().all() \
        if case.project_id and level not in MINIMAL else []
    training = db.execute(select(TrainingEntry).where(TrainingEntry.org_id == ctx.org_id,
                                                      TrainingEntry.case_id == case.id)
                          .order_by(TrainingEntry.activity_date.desc(), TrainingEntry.created_at.desc())
                          ).scalars().all() if level not in MINIMAL else []

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

    def review(r):
        out = ser.review_out(r, lk)
        if level != FULL:
            out.update(rationale=None, cited_source_ids=[])
        return out

    def finding(f):
        out = ser.finding_out(f)
        if not evidence:
            out.update(detail=None, evidence=[])
        return out

    st = derive(reviews)
    case_view = ser.case_out(case, lk, today, reviews[0] if reviews else None, st)
    reqs = db.execute(select(CaseRequirement).where(CaseRequirement.org_id == ctx.org_id,
                                                    CaseRequirement.case_id == case.id)
                      .order_by(CaseRequirement.position)).scalars().all() if level not in MINIMAL else []
    review_by_id = {r.id: r for r in reviews}

    def requirement(r):
        status = requirement_status(r, st, list(all_access))
        rv = review_by_id.get(status.get("review_id"))
        return {"id": r.id, "key": r.key, "title": r.title, "kind": r.kind, "applicability": r.applicability,
                "evidence_expectation": r.evidence_expectation, "due_date": ser.iso(r.due_date),
                "assignee_role": r.assignee_role, "status": status["status"], "detail": status.get("detail"),
                "validated_by": lk.user_ref(rv.reviewer_user_id) if rv else None,
                "validated_at": ser.iso(rv.created_at) if rv else None, "review_id": rv.id if rv else None,
                "change_reason": r.change_reason}

    # Citations stay resolvable against the exact source version reviewed, even after a newer version exists.
    current_ids = {s.id for s in sources}
    cited = {sid for r in reviews for sid in (r.cited_source_ids or [])} | \
        {sid for t in tasks for sid in (t.cited_source_ids or [])}
    historic = db.execute(select(Source).where(Source.org_id == ctx.org_id, Source.id.in_(cited - current_ids))
                          ).scalars().all() if evidence and cited - current_ids else []
    if level in MINIMAL:
        case_view.update(tracker_status=None, tracker_updated_at=None, tracker_age_days=None, stage=None,
                         expected_readiness_date=None, exact_role=None, manager=None)
    access_names = {a.id: a.system for a in all_access}
    return {
        "case": case_view,
        "sources": [ser.source_out(s) for s in sources],
        "claims": [ser.claim_out(c) for c in claims],
        "rejected": [ser.rejected_out(r) for r in rejected] if level == FULL else [],
        "findings": [finding(f) for f in findings],
        "tasks": [ser.task_out(t, lk, today=today) for t in tasks],
        "access_items": [ser.access_out(a, lk) for a in access],
        "latest_review": review(reviews[0]) if reviews else None,
        "reviews": [review(r) for r in reviews],
        "knowledge": [ser.knowledge_out(k, lk, today) for k in knowledge],
        "training": [ser.training_out(e, lk, with_notes=evidence) for e in training],
        "requirements": [requirement(r) for r in reqs],
        "readiness": case_view["readiness"],
        "reassessment": reassessment(reviews[0] if reviews else None, sources) if evidence else
        {"needed": False, "reasons": []},
        "historic_sources": [{**ser.source_out(s), "superseded": True} for s in historic],
        "jobs": case_status(db, ctx.org_id, case.id)["per_source"] if evidence else {},
        "stakeholders": ser.stakeholders_out(case, lk, access_names),
        "ownership_gaps": lk.idx.gaps(case, list(settings.get("required_responsibilities") or [])),
        "my_responsibilities": sorted(policy.responsibilities_held(case)),
        "view": {"level": level, "restricted": RESTRICTED_SECTIONS[level]},
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
            **policy.case_permissions(case),
            "can_confirm_access_ids": [a.id for a in access if policy.can_confirm_access(case, a)],
        },
    }


def timeline(db: Session, ctx: Ctx, case: EmployeeCase) -> list[dict]:
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    level = policy.level(case)
    events: list[dict] = []
    if level in (FULL, EMPLOYEE, SUMMARY):
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
        for r in reviews_for(db, ctx.org_id, case.id):
            reviewer = lk.user_ref(r.reviewer_user_id)
            events.append({"id": f"rev-{r.id}", "type": "review_saved", "at": ser.iso(r.created_at),
                           "title": f"Technical review: {r.disposition.replace('_', ' ')} — {r.scope}",
                           "actor": reviewer["name"] if reviewer else None, "ref": {"entity": "review", "id": r.id}})
        for e in db.execute(select(TrainingEntry).where(TrainingEntry.org_id == ctx.org_id,
                                                        TrainingEntry.case_id == case.id)).scalars():
            who = lk.user_ref(e.recorded_by_user_id)
            events.append({"id": f"trn-{e.id}", "type": "training_recorded", "at": ser.iso(e.created_at),
                           "title": f"Training {e.kind}: {e.title}",
                           "actor": f"{who['name']} ({e.capacity.replace('_', ' ')})" if who else None,
                           "ref": {"entity": "training_entry", "id": e.id}})
    roles_here = policy.roles_for_case(case)
    for t in db.execute(select(Task).where(Task.org_id == ctx.org_id, Task.case_id == case.id)).scalars():
        if level in MINIMAL and not task_is_mine(t, ctx, roles_here):
            continue
        creator = lk.user_ref(t.created_by_user_id)
        events.append({"id": f"tsk-{t.id}", "type": "task_created", "at": ser.iso(t.created_at),
                       "title": f"Task created: {t.title}", "actor": creator["name"] if creator else None,
                       "ref": {"entity": "task", "id": t.id}})
        if t.completed_at:
            owner = lk.user_ref(t.owner_user_id)
            events.append({"id": f"tsd-{t.id}", "type": "task_done", "at": ser.iso(t.completed_at),
                           "title": f"Task done: {t.title}", "actor": owner["name"] if owner else t.owner_role,
                           "ref": {"entity": "task", "id": t.id}})
    # Responsibility history: assignments and their replacement/removal stay visible.
    for r in db.execute(select(CaseResponsibility).where(CaseResponsibility.org_id == ctx.org_id,
                                                         CaseResponsibility.case_id == case.id)).scalars():
        who, by = lk.user_ref(r.user_id), lk.user_ref(r.assigned_by_user_id)
        label = lk.labels.get(r.responsibility_type, r.responsibility_type)
        events.append({"id": f"rsp-{r.id}", "type": "responsibility_assigned", "at": ser.iso(r.assigned_at),
                       "title": f"{label}: {who['name'] if who else '?'} assigned ({r.source.replace('_', ' ')})",
                       "actor": by["name"] if by else "System (migration)",
                       "ref": {"entity": "case_responsibility", "id": r.id}})
        if r.ended_at:
            ender = lk.user_ref(r.ended_by_user_id)
            events.append({"id": f"rse-{r.id}", "type": "responsibility_ended", "at": ser.iso(r.ended_at),
                           "title": f"{label}: {who['name'] if who else '?'} unassigned",
                           "actor": ender["name"] if ender else None,
                           "ref": {"entity": "case_responsibility", "id": r.id}})
    return sorted(events, key=lambda e: e["at"] or "", reverse=True)
