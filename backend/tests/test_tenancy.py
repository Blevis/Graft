"""Cross-org access returns 404, never 403 and never data."""


def test_cross_org_is_404(login):
    ea = login("Elira Dervishi")
    eva = ea.get("/api/cases/ONB-005").json()
    sandbox = login("Sam Rivera", org="Sandbox Co")

    assert [r["ref"] for r in sandbox.get("/api/cases?view=all").json()] == ["SBX-001"]
    assert sandbox.get(f"/api/cases/{eva['case']['id']}").status_code == 404
    assert sandbox.get("/api/cases/ONB-005").status_code == 404
    assert sandbox.get(f"/api/cases/{eva['case']['id']}/timeline").status_code == 404
    assert sandbox.post(f"/api/cases/{eva['case']['id']}/tasks",
                        json={"title": "Cross-org write", "owner_role": "admin"}).status_code == 404
    assert sandbox.post(f"/api/cases/{eva['case']['id']}/reviews",
                        json={"disposition": "close", "scope": "x" * 5, "rationale": "y" * 20}).status_code == 404
    assert sandbox.get("/api/inbox").json() == []
    assert sandbox.get("/api/knowledge").json() == []

    task = ea.post("/api/cases/ONB-005/tasks", json={"title": "Follow up", "owner_role": "technical_owner"}).json()
    assert sandbox.patch(f"/api/tasks/{task['id']}", json={"status": "done"}).status_code == 404


def test_unauthenticated_is_401(app_client):
    assert app_client.get("/api/cases").status_code == 401


def test_role_from_session_not_body(login):
    viewer = login("Mira Shehu")
    r = viewer.post("/api/cases/ONB-005/tasks", json={"title": "Sneaky", "owner_role": "admin", "role": "admin"})
    assert r.status_code == 403
