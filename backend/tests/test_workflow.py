"""Phase 2: case creation from a template, routing and queues, reassignment, SLA clock, CSV import, reminders."""
from datetime import datetime, timezone

from app.db import SessionLocal
from app.services import sla
from app.services.workflow import run_reminders

COORD = "Elira Dervishi"


def _people(c):
    return {u["name"]: u["id"] for u in c.get("/api/users").json()}


def _project(c, name):
    return next(p["id"] for p in c.get("/api/projects").json() if p["name"] == name)


def test_project_transfer_end_to_end(login):
    coord, admin = login(COORD), login("Dren Basha")
    ids = _people(coord)
    form = coord.get("/api/cases-meta/form").json()
    assert {t["key"] for t in form["templates"]} >= {"new_hire", "project_transfer"}
    r = coord.post("/api/cases", json={
        "employee": "Dina Kraja", "movement": "reallocation", "start_date": "2026-10-12",
        "project_id": _project(coord, "Nimbus"), "line_manager_user_id": ids["Luca Gray"],
        "expected_readiness_date": "2026-11-13", "exact_role": "Support Engineer", "external_id": "HR-9001"})
    assert r.status_code == 201, r.text
    d = r.json()
    ref = d["case"]["ref"]
    assert ref == "ONB-011" and d["case"]["exact_role"] == "Support Engineer"
    assert d["case"]["expected_readiness_date"] == "2026-11-13"
    keys = [x["key"] for x in d["requirements"]]
    assert keys[0] == "handover" and "domain_kt" in keys  # project-transfer template snapshot
    tasks = {t["title"]: t for t in d["tasks"]}
    # Deterministic routing: technical owner and training default come from Nimbus; nobody holds access -> queue.
    assert tasks["Complex scenarios covered (observed)"]["owner_user"]["name"] == "Nadia Ferri"
    assert tasks["Project domain KT completed"]["owner_user"]["name"] == "Besa Leka"
    access_task = tasks["New project systems confirmed usable by the employee"]
    assert access_task["owner_user"] is None and access_task["queue"] == "unowned"
    # Duplicate external id is refused.
    assert coord.post("/api/cases", json={"employee": "Someone", "external_id": "HR-9001"}).status_code == 409

    # Template versions never change existing cases.
    tpl = next(t for t in coord.get("/api/templates").json()["templates"] if t["key"] == "project_transfer")
    defn = {"milestones": [{"key": "only_one", "title": "A single milestone", "kind": "milestone"}]}
    assert admin.post("/api/templates/project_transfer/versions", json={"name": "Transfer v2", "definition": defn}
                      ).status_code == 201
    assert [x["key"] for x in coord.get(f"/api/cases/{ref}").json()["requirements"]] == keys
    assert tpl["version"] == 1

    # The coordinator assigns the access blocker from the unowned queue to the access coordinator (audited).
    unowned = coord.get("/api/queues/unowned").json()["items"]
    assert access_task["id"] in {t["id"] for t in unowned}
    gent = ids["Gent Morina"]
    assert coord.post(f"/api/tasks/{access_task['id']}/reassign", json={"owner_user_id": gent, "reason": "Owns access"}
                      ).status_code == 200
    hist = coord.get(f"/api/tasks/{access_task['id']}/history").json()["assignments"]
    assert [h["action"] for h in hist] == ["queued", "reassigned"] and hist[-1]["by"]["name"] == COORD
    assert ("task", "reassigned") in {(e["entity"], e["action"]) for e in coord.get("/api/audit").json()}
    # The assignee acts from their queue.
    g = login("Gent Morina")
    assert access_task["id"] in {t["id"] for t in g.get("/api/queues/mine").json()["items"]}
    assert g.patch(f"/api/tasks/{access_task['id']}", json={"status": "done"}).status_code == 200
    # Gent cannot reassign someone else's work onward to a person.
    other = tasks["Project domain KT completed"]["id"]
    assert g.post(f"/api/tasks/{other}/reassign", json={"owner_user_id": gent, "reason": "x" * 5}).status_code in (403, 404)

    # The technical owner validates the required milestones and signs off with a citation.
    nadia = login("Nadia Ferri")
    src = nadia.post(f"/api/cases/{ref}/sources", json={
        "title": "Observation", "body": "Dina handled the handover and three standard requests with support."})
    assert src.status_code == 201
    sid = src.json()["source"]["id"]
    for key in [x["key"] for x in d["requirements"] if x["kind"] == "milestone" and x["applicability"] == "required"]:
        assert nadia.post(f"/api/cases/{ref}/reviews", json={
            "disposition": "validate_scope", "milestone_key": key, "scope": key, "rationale": "Observed on real work.",
            "cited_source_ids": [sid]}).status_code == 201
    assert coord.get("/api/queues/review_ready").json()["items"][0]["ref"] == ref
    assert nadia.post(f"/api/cases/{ref}/reviews", json={
        "disposition": "close", "scope": "Overall", "rationale": "All required milestones observed.",
        "cited_source_ids": [sid]}).status_code == 201
    assert coord.get(f"/api/cases/{ref}").json()["readiness"]["status"] == "signed_off"


def test_requirement_change_is_targeted_and_audited(login):
    coord = login(COORD)
    d = coord.get("/api/cases/ONB-005").json()
    req = next(r for r in d["requirements"] if r["key"] == "shadowing")
    r = coord.patch(f"/api/cases/ONB-005/requirements/{req['id']}",
                    json={"applicability": "not_applicable", "reason": "Eva joined mid-sprint; no shadowing slot"})
    assert r.status_code == 200
    assert next(x for x in r.json()["requirements"] if x["key"] == "shadowing")["status"] == "not_applicable"
    other = coord.get("/api/cases/ONB-001").json()
    assert next(x for x in other["requirements"] if x["key"] == "shadowing")["applicability"] == "optional"
    assert login("Ardit Kola").patch(f"/api/cases/ONB-005/requirements/{req['id']}",
                                     json={"applicability": "required", "reason": "nope!"}).status_code == 403


def test_csv_preview_dedupe_and_idempotent_resubmit(login):
    coord = login(COORD)
    csv = ("external_id,employee,movement,start_date,project,line_manager,template\n"
           "HR-1,Arta Lika,new_hire,2026-10-20,Orion,Luca Gray,new_hire\n"
           "HR-2,Besnik Hoti,transfer,2026-10-21,Nimbus,,\n"
           "HR-1,Arta Lika,new_hire,2026-10-20,Orion,,\n"
           "HR-3,Clara Ndoj,new_hire,20-10-2026,Mars,Nobody Here,\n"
           ",X,new_hire,,,,\n")
    p = coord.post("/api/cases/import/preview", json={"csv": csv}).json()
    actions = [(r["line"], r["action"]) for r in p["rows"]]
    assert actions == [(2, "create"), (3, "create"), (4, "error"), (5, "error"), (6, "error")]
    errs = {r["line"]: " ".join(r["errors"]) for r in p["rows"]}
    assert "duplicate of line 2" in errs[4]
    assert "start_date" in errs[5] and "unknown project" in errs[5] and "line_manager" in errs[5]
    assert "employee is required" in errs[6]
    out = coord.post("/api/cases/import", json={"csv": csv}).json()
    assert len(out["created"]) == 2
    again = coord.post("/api/cases/import", json={"csv": csv}).json()
    assert again["created"] == [] and [r["action"] for r in again["rows"]][:2] == ["skip_existing", "skip_existing"]
    assert sum(1 for r in coord.get("/api/cases?view=all").json() if r["employee"] in ("Arta Lika", "Besnik Hoti")) == 2
    assert login("Ardit Kola").post("/api/cases/import/preview", json={"csv": csv}).status_code == 403


def test_working_time_with_pause_and_resume():
    settings = {"clock_mode": "real", "timezone": "Europe/Tirane",
                "working_hours": {"start": "09:00", "end": "17:00", "days": [0, 1, 2, 3, 4]}, "holidays": ["2026-10-16"]}
    tz = sla.tz(settings)
    mon9 = datetime(2026, 10, 12, 9, 0, tzinfo=tz)
    fri17 = datetime(2026, 10, 16, 17, 0, tzinfo=tz)
    assert sla.working_seconds(mon9, fri17, settings) == 4 * 8 * 3600  # Friday is a holiday
    assert sla.working_seconds(datetime(2026, 10, 10, 10, tzinfo=tz), datetime(2026, 10, 11, 18, tzinfo=tz),
                               settings) == 0  # weekend

    class T:
        created_at = mon9.astimezone(timezone.utc)
        completed_at = datetime(2026, 10, 14, 13, 0, tzinfo=tz).astimezone(timezone.utc)

    class P:
        def __init__(self, a, b, reason="Waiting for the client"):
            self.paused_at, self.resumed_at, self.reason = a, b, reason

    pauses = [P(datetime(2026, 10, 12, 15, 0, tzinfo=tz), datetime(2026, 10, 13, 11, 0, tzinfo=tz))]
    clock = sla.task_clock(T, pauses, settings)
    # Mon 9-17 (8h) + Tue 9-17 (8h) + Wed 9-13 (4h) = 20h; paused Mon 15-17 + Tue 9-11 = 4h
    assert clock["working_hours"] == 16.0 and clock["waiting_hours"] == 4.0 and not clock["waiting"]


def test_pause_resume_and_reminders(login):
    coord = login(COORD)
    t = coord.post("/api/cases/ONB-005/tasks", json={"title": "Chase Eva's KT plan", "owner_user_id":
                                                       _people(coord)["Ardit Kola"], "due_date": "2026-10-08"}).json()
    assert t["overdue"] is True
    ardit = login("Ardit Kola")
    p = ardit.post(f"/api/tasks/{t['id']}/pause", json={"reason": "Waiting for the client's test data"}).json()
    assert p["waiting"] is True and p["overdue"] is False
    assert t["id"] in {x["id"] for x in coord.get("/api/queues/waiting").json()["items"]}
    with SessionLocal() as db:
        assert run_reminders(db)["reminded"] == 0  # waiting work is not chased
    assert ardit.post(f"/api/tasks/{t['id']}/resume").json()["waiting"] is False
    with SessionLocal() as db:
        first = run_reminders(db)
        second = run_reminders(db)
    assert first["reminded"] >= 1 and second == {"reminded": 0, "escalated": 0}  # idempotent
    assert first["escalated"] >= 1  # 2026-10-08 is more than 2 working days before the as-of date
    assert any("Overdue" in n["text"] for n in ardit.get("/api/notifications").json())
    assert any("Escalated" in n["text"] for n in coord.get("/api/notifications").json())


def test_routing_from_a_finding(login):
    coord = login(COORD)
    f = next(x for x in coord.get("/api/cases/ONB-002").json()["findings"] if x["rule_id"] == "ACCESS_NOT_CONFIRMED")
    t = coord.post("/api/cases/ONB-002/tasks", json={"title": "Unblock Leo's access", "finding_id": f["id"]}).json()
    assert t["owner_user"]["name"] == "Gent Morina"  # ONB-002's access responsible
    lina = coord.get("/api/cases/ONB-009").json()
    f = next(x for x in lina["findings"] if x["rule_id"] == "MISSING_PROJECT")
    t = coord.post("/api/cases/ONB-009/tasks", json={"title": "Record Lina's project", "finding_id": f["id"]}).json()
    assert t["owner_user"] is None and t["queue"] == "unowned"
    # Claim from the coordinator queue.
    c = coord.post(f"/api/tasks/{t['id']}/claim").json()
    assert c["owner_user"]["name"] == COORD and c["queue"] is None


def test_employee_submits_evidence_to_own_case_only(login):
    eva = login("Eva Stone")
    r = eva.post("/api/cases/ONB-005/sources", json={"title": "My update", "body": "I covered one complex scenario."})
    assert r.status_code == 201 and r.json()["source"]["author_role"].startswith("Employee")
    assert eva.post("/api/cases/ONB-002/sources", json={"title": "x" * 3, "body": "y" * 3}).status_code == 404
    assert login("Mira Shehu").post("/api/cases/ONB-005/sources", json={"title": "x" * 3, "body": "y" * 3}
                                    ).status_code == 403
