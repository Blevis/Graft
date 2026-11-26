import datetime as dt
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AccessItem, CaseRequirement, Finding, Review, Task
from ..services import serialize as ser
from ..services.org_settings import as_of, get_org_settings
from ..services.evidence import current_claims, latest_sources
from ..services.readiness import derive, requirement_status
from ..services.permissions import EMPLOYEE, FULL, SUMMARY, Policy
from ..services.visibility import visible_cases
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["insights"])
ACCESS_STATES = ["requested", "awaiting_approval", "approved", "not_provisioned", "active", "confirmed_usable"]
ACTIVITY_DAYS = 28
STAGES = ["pre_onboarding", "access", "shadowing", "supported_execution", "independent_execution", "validated"]


@router.get("/insights")
def insights(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    today = as_of(get_org_settings(db, ctx.org_id))
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    # Every figure covers only cases this member may read at least as a summary; a task assignment or access-only
    # responsibility does not open portfolio figures.
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()
             if policy.level(c) in (FULL, EMPLOYEE, SUMMARY)}
    ids = list(cases)
    findings = db.execute(scoped(Finding, ctx).where(Finding.case_id.in_(ids))).scalars().all()
    open_tasks = db.execute(scoped(Task, ctx).where(Task.status == "open", Task.case_id.in_(ids))).scalars().all()
    latest: dict[str, Review] = {}
    per_case: dict[str, list[Review]] = {}
    for r in db.execute(scoped(Review, ctx).where(Review.case_id.in_(ids)).order_by(Review.created_at)).scalars():
        latest[r.case_id] = r
        per_case.setdefault(r.case_id, []).append(r)
    readiness = Counter(derive(per_case.get(c, [])).status for c in cases)

    by_reason = Counter((f.rule_id, f.message.split(":")[0]) for f in findings)
    by_rule = Counter(f.rule_id for f in findings)
    by_severity = Counter(f.severity for f in findings)
    flagged_by_project: Counter = Counter()
    cases_by_project: Counter = Counter()
    for c in cases.values():
        name = lk.projects[c.project_id].name if c.project_id in lk.projects else "— (no project)"
        cases_by_project[name] += 1
        if any(f.case_id == c.id and f.severity in ("high", "medium") for f in findings):
            flagged_by_project[name] += 1
    stage = Counter((latest[c].observed_stage or "unspecified") if c in latest else "none" for c in cases)
    overdue = [t for t in open_tasks if t.due_date and t.due_date < today]
    review_states = Counter(latest[c].disposition if c in latest else "none" for c in cases)

    # ---- figures behind the charts: counts only, each over the cases whose underlying section the caller may read
    stale_days = int(get_org_settings(db, ctx.org_id)["stale_days"])
    tracker_status = Counter(c.tracker_status or "Not reported" for c in cases.values())
    tracker_age = Counter()
    for c in cases.values():
        age = (today - c.tracker_updated_at).days if c.tracker_updated_at else None
        tracker_age["missing" if age is None else "fresh" if age <= stale_days else
                    "aging" if age <= 2 * stale_days else "stale"] += 1

    access_by_case: dict[str, list[AccessItem]] = {}
    for a in db.execute(scoped(AccessItem, ctx).where(AccessItem.case_id.in_(ids))).scalars():
        access_by_case.setdefault(a.case_id, []).append(a)
    access_state = Counter(a.state for items in access_by_case.values() for a in items)

    reqs_by_case: dict[str, list[CaseRequirement]] = {}
    for r in db.execute(scoped(CaseRequirement, ctx).where(CaseRequirement.case_id.in_(ids))).scalars():
        reqs_by_case.setdefault(r.case_id, []).append(r)
    progress = []
    for c in sorted(cases.values(), key=lambda c: c.ref):
        st = derive(per_case.get(c.id, []))
        required = [r for r in reqs_by_case.get(c.id, []) if r.applicability == "required"]
        met = sum(1 for r in required if requirement_status(r, st, access_by_case.get(c.id, []))["status"] == "satisfied")
        progress.append({"ref": c.ref, "employee": c.employee, "met": met, "required": len(required),
                         "readiness": st.status})

    # Evidence counts follow the timeline (who may see that a source arrived); claim and verifier counts follow the
    # stricter claim / rejected-candidate rules.
    sources = [s for s in latest_sources(db, ctx.org_id) if s.case_id in cases]
    claim_sources = [s for s in sources if policy.can_view_field("claims", cases[s.case_id])]
    claims, rejected, _runs = current_claims(db, claim_sources) if claim_sources else ([], [], {})
    full_ids = {s.id for s in sources if policy.can_view_field("rejected", cases[s.case_id])}
    start = today - dt.timedelta(days=ACTIVITY_DAYS - 1)
    per_day = Counter(s.date for s in sources if s.date and start <= s.date <= today)

    owners: dict[str, dict] = {}
    for t in open_tasks:
        name = lk.users[t.owner_user_id].name if t.owner_user_id in lk.users else (
            f"Any {t.owner_role.replace('_', ' ')}" if t.owner_role else "Unassigned")
        row = owners.setdefault(name, {"owner": name, "open": 0, "overdue": 0})
        row["open"] += 1
        row["overdue"] += bool(t.due_date and t.due_date < today)
    week_end = today + dt.timedelta(days=6 - today.weekday())
    due = Counter("no_date" if not t.due_date else "overdue" if t.due_date < today else
                  "this_week" if t.due_date <= week_end else
                  "next_week" if t.due_date <= week_end + dt.timedelta(days=7) else "later" for t in open_tasks)
    return {
        "tracker": {
            "by_status": [{"status": s, "count": n} for s, n in tracker_status.most_common()],
            "age": {k: tracker_age.get(k, 0) for k in ("fresh", "aging", "stale", "missing")},
            "stale_days": stale_days,
        },
        "access": {
            "by_state": [{"state": s, "count": access_state.get(s, 0)} for s in ACCESS_STATES],
            "systems": sum(access_state.values()),
            "cases_blocked": sum(1 for items in access_by_case.values() if any(a.state != "confirmed_usable" for a in items)),
        },
        "progress": progress,
        "checks": {"met": sum(p["met"] for p in progress), "required": sum(p["required"] for p in progress)},
        "evidence": {
            "sources": len(sources),
            "claims": len(claims),
            "rejected": sum(1 for r in rejected if r.source_id in full_ids),
            "claim_sources": len(claim_sources),
            "by_kind": [{"kind": k, "count": n} for k, n in Counter(s.kind for s in sources).most_common()],
            "by_day": [{"date": (start + dt.timedelta(days=i)).isoformat(),
                        "count": per_day.get(start + dt.timedelta(days=i), 0)} for i in range(ACTIVITY_DAYS)],
        },
        "workload": sorted(owners.values(), key=lambda r: (-r["open"], r["owner"])),
        "due": {k: due.get(k, 0) for k in ("overdue", "this_week", "next_week", "later", "no_date")},
        "as_of_date": today.isoformat(),
        "totals": {
            "cases": len(cases),
            "cases_needing_attention": len({f.case_id for f in findings if f.severity in ("high", "medium")}),
            "open_tasks": len(open_tasks),
            "overdue_tasks": len(overdue),
            "reviews_recorded": len(latest),
        },
        "by_rule": [{"rule_id": r, "count": n} for r, n in by_rule.most_common()],
        "by_reason": [{"rule_id": r, "message": m, "count": n} for (r, m), n in by_reason.most_common()],
        "by_severity": {s: by_severity.get(s, 0) for s in ("high", "medium", "low")},
        "by_project": [{"project": p, "cases": n, "flagged": flagged_by_project.get(p, 0)}
                       for p, n in sorted(cases_by_project.items())],
        "stage_distribution": [{"stage": s, "count": stage.get(s, 0)} for s in ["none", *STAGES, "unspecified"]
                               if stage.get(s, 0) or s in ("none",)],
        "review_states": [{"state": s, "count": n} for s, n in review_states.most_common()],
        "readiness": {s: readiness.get(s, 0) for s in ("not_signed_off", "signed_off", "reopened")},
        "overdue": [ser.task_out(t, lk, cases.get(t.case_id), today) for t in overdue],
    }
