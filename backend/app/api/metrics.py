"""Portfolio outcome metrics and permission-scoped export.

Definitions (also in docs/business-rules.md, "Outcome metrics"). All figures cover only cases the caller may read
at least as a summary, optionally filtered by project; every metric lists the cases behind it (drill-down).

1. Blocker to owner (hours): for each high/medium finding first detected in the range (finding.created_at), the time
   until a named person owned work on it: the earliest of a task created for that finding with a named owner, or a
   claim/reassignment of such a task to a person. Blockers without an owner yet are counted as `open` and excluded
   from the median/p90. Wall-clock hours.
2. Start to sign-off (days): for each case whose current final sign-off falls in the range, days from the case start
   date to the sign-off review. Cases without a start date are listed as `missing_start`. Cases not signed off are
   reported as `open` (count) and excluded from the durations.
3. Closes with unmet checks: of all final sign-off reviews recorded in the range (including later-reopened ones),
   the share recorded under a documented exception (bypassed criteria) or before the closure gate existed (legacy,
   checks unverified). Denominator: all close reviews in the range."""
import csv
import io
import statistics
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Finding, Review, Task, TaskAssignment
from ..services import audit
from ..services.cases import case_rows
from ..services.permissions import EMPLOYEE, FULL, SUMMARY, Policy
from ..services.readiness import derive
from ..services.tenancy import Ctx, get_ctx, scoped
from ..services.visibility import visible_cases

router = APIRouter(tags=["metrics"])


def _utc(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _in(v: datetime, start: date | None, end: date | None) -> bool:
    d = _utc(v).date()
    return (start is None or d >= start) and (end is None or d <= end)


def _summary(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": None, "p90": None}
    s = sorted(values)
    p90 = s[min(len(s) - 1, max(0, round(0.9 * len(s)) - 1))]
    return {"n": len(s), "median": round(statistics.median(s), 1), "p90": round(p90, 1)}


def compute(db: Session, ctx: Ctx, start: date | None, end: date | None, project_id: str | None) -> dict:
    policy = Policy(db, ctx)
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()
             if policy.level(c) in (FULL, EMPLOYEE, SUMMARY) and (project_id is None or c.project_id == project_id)}
    ids = list(cases)

    # 1. blocker -> owner
    findings = db.execute(scoped(Finding, ctx).where(Finding.case_id.in_(ids), Finding.severity.in_(("high", "medium")))
                          ).scalars().all()
    tasks = db.execute(scoped(Task, ctx).where(Task.case_id.in_(ids), Task.finding_id.is_not(None))).scalars().all()
    owned_at: dict[str, datetime] = {}

    def owned(fid: str, at: datetime) -> None:
        owned_at[fid] = min(owned_at.get(fid, _utc(at)), _utc(at))

    for t in tasks:
        history = db.execute(select(TaskAssignment).where(TaskAssignment.task_id == t.id)).scalars().all()
        if not history and t.owner_user_id:  # tasks created before assignment history existed
            owned(t.finding_id, t.created_at)
        for a in history:
            if a.to_user_id:
                owned(t.finding_id, a.created_at)
    b_vals, b_cases, b_open = [], {}, []
    for f in findings:
        if not _in(f.created_at, start, end):
            continue
        if f.id in owned_at:
            hours = round(max(0.0, (owned_at[f.id] - _utc(f.created_at)).total_seconds() / 3600), 1)
            b_vals.append(hours)
            b_cases.setdefault(f.case_id, []).append(hours)
        else:
            b_open.append(f.case_id)

    # 2 + 3. sign-off
    reviews: dict[str, list[Review]] = {}
    for r in db.execute(scoped(Review, ctx).where(Review.case_id.in_(ids))).scalars():
        reviews.setdefault(r.case_id, []).append(r)
    s_vals, s_cases, s_open, missing_start = [], [], [], []
    closes, flagged, exceptions, legacy = 0, [], 0, 0
    for cid, c in cases.items():
        st = derive(reviews.get(cid, []))
        if st.status == "signed_off" and _in(st.final_review.created_at, start, end):
            if c.start_date:
                days = max(0, (_utc(st.final_review.created_at).date() - c.start_date).days)
                s_vals.append(days)
                s_cases.append((cid, days))
            else:
                missing_start.append(cid)
        elif st.status != "signed_off":
            s_open.append(cid)
        for r in reviews.get(cid, []):
            if r.disposition != "close" or not _in(r.created_at, start, end):
                continue
            closes += 1
            if r.bypassed_criteria:
                exceptions += 1
                flagged.append(cid)
            elif r.policy_version == "legacy":
                legacy += 1
                flagged.append(cid)

    def refs(xs):
        return sorted({cases[x].ref for x in xs})

    return {
        "filters": {"from": start.isoformat() if start else None, "to": end.isoformat() if end else None,
                    "project_id": project_id, "cases_in_scope": len(cases)},
        "blocker_to_owner_hours": {**_summary(b_vals), "open": len(b_open),
                                   "cases": sorted(({"ref": cases[c].ref, "values": v} for c, v in b_cases.items()),
                                                   key=lambda x: x["ref"]),
                                   "open_cases": refs(b_open)},
        "start_to_signoff_days": {**_summary(s_vals), "open": len(s_open),
                                  "cases": sorted(({"ref": cases[c].ref, "values": [d]} for c, d in s_cases),
                                                  key=lambda x: x["ref"]),
                                  "missing_start": refs(missing_start)},
        "closes_with_unmet_checks": {"closes": closes, "flagged": exceptions + legacy, "exceptions": exceptions,
                                     "legacy_unverified": legacy,
                                     "share": round((exceptions + legacy) / closes, 3) if closes else None,
                                     "cases": refs(flagged)},
    }


@router.get("/metrics")
def metrics(start: date | None = None, end: date | None = None, project_id: str | None = None,
            ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return compute(db, ctx, start, end, project_id)


EXPORT_FIELDS = ["ref", "employee", "project", "tracker_status", "tracker_age_days", "readiness", "review_state",
                 "stage", "open_task_count", "flags", "ownership_gaps", "view_level"]
MINIMAL_FIELDS = {"ref", "employee", "project", "open_task_count", "view_level"}


@router.get("/export/cases.csv")
def export_cases(view: str = "all", ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """CSV of the case list the caller can see, with exactly the fields their view level allows. Audited."""
    rows = case_rows(db, ctx, view if view in ("all", "needs_attention", "mine", "stale", "access_blocked",
                                               "missing_owner") else "all")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
    w.writeheader()
    for r in rows:
        minimal = r["view_level"] in ("access_only", "task_only")
        full = {"ref": r["ref"], "employee": r["employee"], "project": r["project"] or "",
                "tracker_status": r["tracker_status"] or "", "tracker_age_days": r["tracker_age_days"],
                "readiness": r["readiness"] or "", "review_state": r["review_state"], "stage": r["stage"] or "",
                "open_task_count": r["open_task_count"], "flags": " ".join(x["rule_id"] for x in r["reasons"]),
                "ownership_gaps": " ".join(r["ownership_gaps"]), "view_level": r["view_level"]}
        w.writerow({k: (v if not minimal or k in MINIMAL_FIELDS else "") for k, v in full.items()})
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="export", entity_id=ctx.user_id[:32],
                 action="cases_csv", after={"view": view, "rows": len(rows), "fields": EXPORT_FIELDS})
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="graft-cases.csv"'})

