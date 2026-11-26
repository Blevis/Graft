"""Per-role case visibility. A case you may not see behaves like another org's case: 404, no data anywhere."""

ALL = {f"ONB-{i:03d}" for i in range(1, 11)}


def refs(client):
    return {r["ref"] for r in client.get("/api/cases?view=all").json()}


def test_full_view_roles_see_every_case(login):
    for name in ("Dren Basha", "Elira Dervishi", "Mira Shehu"):  # admin, coordinator, management
        assert refs(login(name)) == ALL, name


def test_employee_sees_only_own_case(login):
    eva = login("Eva Stone")
    assert refs(eva) == {"ONB-005"}
    assert eva.get("/api/cases/ONB-005").status_code == 200
    for hidden in ("ONB-002", "ONB-009"):
        assert eva.get(f"/api/cases/{hidden}").status_code == 404
        assert eva.get(f"/api/cases/{hidden}/timeline").status_code == 404
        assert eva.get(f"/api/cases/{hidden}/access-items").status_code == 404
    # Evidence: only her own sources, never unmatched or other people's mail.
    assert {i["source"]["ref"] for i in eva.get("/api/inbox").json()} == {"E3", "E4"}
    # Portfolio figures cover only what she may see.
    assert eva.get("/api/insights").json()["totals"]["cases"] == 1


def test_employee_can_confirm_own_access_but_not_see_others(login):
    leo = login("Leo Marin")
    assert refs(leo) == {"ONB-002"}
    item = leo.get("/api/cases/ONB-002/access-items").json()[0]
    r = leo.patch(f"/api/access-items/{item['id']}", json={"state": "confirmed_usable"})
    assert r.status_code == 200 and r.json()["state"] == "confirmed_usable"
    assert leo.get("/api/cases/ONB-005").status_code == 404


def test_line_manager_sees_only_their_reports(login):
    assert refs(login("Luca Gray")) == {"ONB-005"}


def test_technical_owner_sees_owned_projects(login):
    assert refs(login("Ardit Kola")) == {"ONB-001", "ONB-005", "ONB-006"}  # Aurora, Orion, Atlas
    nadia = login("Nadia Ferri")
    assert refs(nadia) == {"ONB-002", "ONB-004", "ONB-007", "ONB-008", "ONB-010"}
    assert nadia.get("/api/cases/ONB-005").status_code == 404
    assert nadia.post("/api/cases/ONB-005/reviews", json={
        "disposition": "close", "scope": "Overall", "rationale": "Not my case at all."}).status_code == 404


def test_assigned_task_opens_its_case(login):
    coord = login("Elira Dervishi")
    users = {u["name"]: u["id"] for u in coord.get("/api/users").json()}
    # Nadia does not own Lina's case (no project), but once a task is assigned to her she can open it.
    nadia = login("Nadia Ferri")
    assert nadia.get("/api/cases/ONB-009").status_code == 404
    assert coord.post("/api/cases/ONB-009/tasks", json={
        "title": "Confirm Lina's role, KT owner and readiness date", "owner_user_id": users["Nadia Ferri"]}
    ).status_code == 201
    assert nadia.get("/api/cases/ONB-009").status_code == 200
    assert len(nadia.get("/api/tasks?mine=1").json()) == 1


def test_hidden_task_lists_and_search(login):
    eva = login("Eva Stone")
    coord = login("Elira Dervishi")
    coord.post("/api/cases/ONB-002/tasks", json={"title": "Chase Orion Portal approval", "owner_role": "pmo_coordinator"})
    assert all(t["case"]["ref"] == "ONB-005" for t in eva.get("/api/tasks?status=all").json())
    assert eva.get("/api/cases?view=all&q=Leo").json() == []
