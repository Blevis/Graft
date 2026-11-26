"""Phase 6: outcome metrics against a controlled fixture, drill-down, and permission-scoped export."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import EmployeeCase, Finding, Review, Task, TaskAssignment


def _at(db, model, row_id, when):
    obj = db.get(model, row_id)
    obj.created_at = when
    return obj


def test_metrics_fixture_and_drilldown(login):
    coord, tl = login("Elira Dervishi"), login("Ardit Kola")
    eva = coord.get("/api/cases/ONB-005").json()
    conflict = next(f for f in eva["findings"] if f["rule_id"] == "CLOSURE_CONFLICT")
    t = coord.post("/api/cases/ONB-005/tasks", json={"title": "Cover the scenarios", "finding_id": conflict["id"]}
                   ).json()  # routed to Ardit
    e3 = next(s["id"] for s in eva["sources"] if s["ref"] == "E3")
    for key in ("kt_plan", "supported_execution", "complex_scenarios"):
        tl.post("/api/cases/ONB-005/reviews", json={"disposition": "validate_scope", "milestone_key": key,
                                                    "scope": key, "rationale": "Observed directly.",
                                                    "cited_source_ids": [e3]})
    close = tl.post("/api/cases/ONB-005/reviews", json={"disposition": "close", "scope": "Overall",
                                                        "rationale": "All required checks met.",
                                                        "cited_source_ids": [e3]}).json()
    t0 = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:  # pin timestamps so the expected numbers are exact
        _at(db, Finding, conflict["id"], t0)
        for a in db.execute(select(TaskAssignment).where(TaskAssignment.task_id == t["id"])).scalars():
            a.created_at = t0 + timedelta(hours=6)
        _at(db, Task, t["id"], t0 + timedelta(hours=6))
        _at(db, Review, close["id"], datetime(2026, 10, 20, 12, tzinfo=timezone.utc))
        case = db.execute(select(EmployeeCase).where(EmployeeCase.ref == "ONB-006")).scalar_one()
        ardit = db.get(Review, close["id"]).reviewer_user_id
        db.add(Review(org_id=case.org_id, case_id=case.id, disposition="close", scope="Overall", rationale="Old close.",
                      cited_source_ids=[], reviewer_user_id=ardit, policy_version="legacy",
                      created_at=datetime(2026, 10, 18, tzinfo=timezone.utc)))
        db.commit()
    m = coord.get("/api/metrics", params={"start": "2026-10-01", "end": "2026-10-31"}).json()
    b = m["blocker_to_owner_hours"]
    assert b["n"] == 1 and b["median"] == 6.0 and b["cases"] == [{"ref": "ONB-005", "values": [6.0]}]
    assert coord.get("/api/metrics").json()["blocker_to_owner_hours"]["open"] >= 1  # other blockers: no owner yet
    s = m["start_to_signoff_days"]
    eva_days = (date(2026, 10, 20) - date.fromisoformat(eva["case"]["start_date"])).days
    assert {"ref": "ONB-005", "values": [eva_days]} in s["cases"] and s["open"] == 8
    c = m["closes_with_unmet_checks"]
    assert c["closes"] == 2 and c["legacy_unverified"] == 1 and c["exceptions"] == 0 and c["share"] == 0.5
    assert c["cases"] == ["ONB-006"]
    # Filters narrow the scope and the drill-down follows.
    orion = next(p["id"] for p in coord.get("/api/projects").json() if p["name"] == "Orion")
    mo = coord.get("/api/metrics", params={"project_id": orion}).json()
    assert mo["filters"]["cases_in_scope"] == 1 and mo["closes_with_unmet_checks"]["closes"] == 1
    assert coord.get("/api/metrics", params={"start": "2026-11-01"}).json()["closes_with_unmet_checks"]["closes"] == 0


def test_export_is_scoped_and_audited(login):
    coord = login("Elira Dervishi")
    users = {u["name"]: u["id"] for u in coord.get("/api/users").json()}
    coord.post("/api/cases/ONB-002/tasks", json={"title": "Check portal", "owner_user_id": users["Erion Daci"]})
    full = coord.get("/api/export/cases.csv").text.splitlines()
    assert full[0].startswith("ref,employee") and len(full) == 11
    erion = login("Erion Daci").get("/api/export/cases.csv").text.splitlines()
    leo = next(line for line in erion if line.startswith("ONB-002"))
    assert "Access Pending" not in leo and "ACCESS_NOT_CONFIRMED" not in leo and leo.endswith("task_only")
    assert len(erion) == 3  # header + Eva (summary) + Leo (task only)
    assert ("export", "cases_csv") in {(e["entity"], e["action"]) for e in coord.get("/api/audit").json()}
