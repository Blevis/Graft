"""Acceptance: the Eva Stone (ONB-005) hero workflow, end to end through the API."""

COORD, TL, LM = "Elira Dervishi", "Ardit Kola", "Luca Gray"


def _snapshot(detail):
    return (
        [(t["id"], t["title"], t["status"], (t["owner_user"] or {}).get("id"), t["due_date"]) for t in detail["tasks"]],
        [(r["id"], r["disposition"], r["rationale"], r["reviewer"]["id"], r["created_at"]) for r in detail["reviews"]],
    )


def test_eva_end_to_end(login):
    coord = login(COORD)
    d = coord.get("/api/cases/ONB-005").json()

    # Tracker is one report; evidence is cited; the conflict is flagged; no decision yet.
    assert d["case"]["tracker_status"] == "Ready with Support"
    assert d["latest_review"] is None and d["tasks"] == []
    bodies = {s["id"]: s["body"] for s in d["sources"]}
    pairs = {(c["scope"], c["value"]) for c in d["claims"]}
    assert ("complex_scenarios", "coverage_pending") in pairs
    assert ("complex_scenarios", "coverage_complete") not in pairs
    for c in d["claims"]:
        assert bodies[c["source_id"]][c["start"]:c["end"]] == c["quote"]
    assert [r["reason"] for r in d["rejected"]] == ["no exact match in E3"]
    conflict = [f for f in d["findings"] if f["rule_id"] == "CLOSURE_CONFLICT"]
    assert len(conflict) == 1 and conflict[0]["message"] == "Closure needs technical review"
    assert {e["source_id"] for e in conflict[0]["evidence"]} == set(bodies)
    assert d["analysis"]["mode"] == "replay"

    # The coordinator cannot record a readiness review.
    assert coord.post("/api/cases/ONB-005/reviews", json={
        "disposition": "close", "scope": "Overall onboarding", "rationale": "Line manager says closed."}
    ).status_code == 403

    # Coordinator assigns a follow-up to the technical owner, citing both sources.
    tl_id = d["case"]["tech_owner"]["id"]
    r = coord.post("/api/cases/ONB-005/tasks", json={
        "title": "Plan coverage of the two outstanding complex scenarios", "owner_user_id": tl_id,
        "finding_id": conflict[0]["id"], "cited_source_ids": list(bodies), "due_date": "2026-10-21"})
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]

    # The assigned technical owner records a scoped Keep-open review linked to that task.
    tl = login(TL)
    assert len(tl.get("/api/tasks?mine=1").json()) == 1
    r = tl.post("/api/cases/ONB-005/reviews", json={
        "disposition": "keep_open", "scope": "Overall onboarding",
        "rationale": "Standard requests with occasional support only; two complex scenarios still uncovered.",
        "observed_stage": "supported_execution", "cited_source_ids": list(bodies), "task_id": task_id})
    assert r.status_code == 201, r.text

    # Line manager cannot review either.
    assert login(LM).post("/api/cases/ONB-005/reviews", json={
        "disposition": "close", "scope": "Overall", "rationale": "Everything looks complete."}).status_code == 403

    before = coord.get("/api/cases/ONB-005").json()
    assert before["latest_review"]["disposition"] == "keep_open"
    assert before["case"]["stage"] == "supported_execution"

    # Re-analysis twice: human records are unchanged, nothing duplicated.
    for _ in range(2):
        assert coord.post("/api/cases/ONB-005/analyze").status_code == 200
    after = coord.get("/api/cases/ONB-005").json()
    assert _snapshot(after) == _snapshot(before)
    assert len(after["claims"]) == len(before["claims"])
    assert [f["id"] for f in after["findings"]] == [f["id"] for f in before["findings"]]

    # Queue still shows Eva open.
    row = next(r for r in coord.get("/api/cases?view=all").json() if r["ref"] == "ONB-005")
    assert row["review_state"] == "keep_open"

    # Every write was audited.
    actions = {(e["entity"], e["action"]) for e in coord.get("/api/audit").json()}
    assert {("task", "created"), ("review", "created"), ("case", "analyzed")} <= actions


def test_ai_disabled_still_works(login):
    admin = login("Dren Basha")
    assert admin.patch("/api/settings", json={"ai_enabled": False}).json()["ai_enabled"] is False
    coord = login(COORD)
    assert coord.post("/api/cases/ONB-005/analyze").status_code == 200
    assert coord.post("/api/cases/ONB-005/suggest-task").status_code == 503
    assert coord.post("/api/cases/ONB-005/tasks", json={"title": "Manual follow-up", "owner_role": "technical_owner"}
                      ).status_code == 201
