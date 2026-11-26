from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import EmployeeCase, Finding, Review, Task
from ..services import serialize as ser
from ..services.org_settings import as_of, get_org_settings
from ..services.visibility import visible_case_ids, visible_cases
from ..services.tenancy import Ctx, get_ctx, scoped

router = APIRouter(tags=["insights"])
STAGES = ["pre_onboarding", "access", "shadowing", "supported_execution", "independent_execution", "validated"]


@router.get("/insights")
def insights(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    today = as_of(get_org_settings(db, ctx.org_id))
    lk = ser.Lookup(db, ctx.org_id)
    cases = {c.id: c for c in db.execute(visible_cases(ctx)).scalars()}
    ids = visible_case_ids(ctx)  # every figure covers only the cases this member may see
    findings = db.execute(scoped(Finding, ctx).where(Finding.case_id.in_(ids))).scalars().all()
    open_tasks = db.execute(scoped(Task, ctx).where(Task.status == "open", Task.case_id.in_(ids))).scalars().all()
    latest: dict[str, Review] = {}
    for r in db.execute(scoped(Review, ctx).where(Review.case_id.in_(ids)).order_by(Review.created_at)).scalars():
        latest[r.case_id] = r

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
    return {
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
        "overdue": [ser.task_out(t, lk, cases.get(t.case_id), today) for t in overdue],
    }
