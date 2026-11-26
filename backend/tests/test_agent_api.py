"""Exercise persistence, access control and human handoff through the public endpoints."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.ai import client
from app.db import SessionLocal
from app.models import AgentRun

EVA = "/api/cases/ONB-005"
RUNS = EVA + "/agent-runs"


@pytest.fixture
def stub_groq(monkeypatch):
    def turn(messages, tools, timeout):
        if messages[-1]["role"] == "user":
            tool, args = "list_claims", {}
        else:
            claims = json.loads(messages[-1]["content"])
            claim = next(c for c in claims if c["value"] == "coverage_pending")
            good = {"kind": "task", "title": "Plan coverage of the two complex scenarios",
                    "body": "Arrange a technical follow-up.", "owner_role": "technical_owner",
                    "cited_claim_ids": [claim["id"]]}
            tool = "submit_proposals"
            args = {"assessment": "The technical lead reports outstanding coverage.",
                    "proposals": [good, {**good, "cited_claim_ids": ["invented-id"]}]}
        return {"role": "assistant", "content": None, "tool_calls": [
            {"id": str(len(messages)), "type": "function",
             "function": {"name": tool, "arguments": json.dumps(args)}}]}
    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "agent_turn", turn)
    return turn


def test_run_persists_only_ai_data_and_audit(login, stub_groq):
    coord = login("Elira Dervishi")
    owner = login("Ardit Kola")
    saved_task = coord.post(EVA + "/tasks", json={"title": "Original task", "owner_role": "technical_owner"}).json()
    saved_review = owner.post(EVA + "/reviews", json={
        "disposition": "keep_open", "scope": "Overall training", "rationale": "Two scenarios still outstanding.",
        "task_id": saved_task["id"]})
    assert saved_review.status_code == 201
    before = coord.get(EVA).json()
    result = coord.post(RUNS)
    assert result.status_code == 200, result.text
    run = result.json()
    assert set(run) == {"id", "case_id", "status", "assessment", "proposals", "steps", "model",
                        "prompt_version", "created_at"}
    assert run["status"] == "completed"
    (proposal,) = run["proposals"]
    assert proposal["status"] == "open" and proposal["cited_source_ids"]
    assert proposal["cited_claim_ids"][0] in {c["id"] for c in before["claims"]}
    assert "rejected" in run["steps"][-1]["result_summary"].lower()
    assert owner.get(RUNS).json() == [run]
    latest = coord.post(RUNS).json()
    assert [row["id"] for row in coord.get(RUNS).json()] == [latest["id"], run["id"]]
    after = coord.get(EVA).json()
    assert (before["tasks"], before["reviews"]) == (after["tasks"], after["reviews"])
    records = coord.get("/api/audit").json()
    assert {("agent_run", "completed"), ("agent_proposal", "proposed"), ("agent_step", "recorded")} <= {
        (r["entity"], r["action"]) for r in records}
    with SessionLocal() as db:
        assert len(db.get(AgentRun, run["id"]).evidence_hash) == 64


def test_permissions_and_unavailability(login, app_client):
    assert app_client.post(RUNS).status_code == 401
    employee = login("Eva Stone")
    assert employee.post(RUNS).status_code == 403
    assert login("Leo Marin").post(RUNS).status_code == 404
    assert login("Leo Marin").get(RUNS).status_code == 404
    sandbox = login("Sam Rivera", "Sandbox Co")
    assert sandbox.get(RUNS).status_code == sandbox.post(RUNS).status_code == 404
    coord = login("Elira Dervishi")
    missing_key = coord.post(RUNS).json()
    assert missing_key["status"] == "unavailable" and not missing_key["proposals"]
    admin = login("Dren Basha")
    admin.patch("/api/settings", json={"ai_enabled": False}).raise_for_status()
    disabled = admin.post(RUNS).json()
    assert disabled["status"] == "unavailable" and "disabled" in disabled["assessment"].lower()
    assert employee.get(RUNS).json() == [disabled, missing_key]


def test_accept_and_dismiss_are_scoped_and_atomic(login, stub_groq):
    coord = login("Elira Dervishi")
    p = coord.post(RUNS).json()["proposals"][0]
    path = f"/api/agent-proposals/{p['id']}/dismiss"
    task = {"title": "Edited by the coordinator", "owner_role": "technical_owner",
            "cited_source_ids": p["cited_source_ids"], "proposal_id": p["id"]}
    assert login("Leo Marin").post(path, json={"reason": "Wrong case"}).status_code == 404
    assert login("Sam Rivera", "Sandbox Co").post(path, json={"reason": "Wrong org"}).status_code == 404
    assert login("Eva Stone").post(path, json={"reason": "Own case"}).status_code == 403
    assert coord.post("/api/cases/ONB-002/tasks", json={**task, "cited_source_ids": []}).status_code == 404
    assert coord.post(EVA + "/tasks", json={**task, "owner_user_id": "unknown"}).status_code == 422
    assert coord.get(RUNS).json()[0]["proposals"][0]["status"] == "open"
    made = coord.post(EVA + "/tasks", json=task)
    assert made.status_code == 201 and made.json()["origin"] == "ai_suggested_edited"
    assert coord.get(RUNS).json()[0]["proposals"][0]["status"] == "accepted"
    assert coord.post(EVA + "/tasks", json=task).status_code == 409
    assert coord.post(path, json={"reason": "Too late"}).status_code == 409
    assert len(coord.get(EVA).json()["tasks"]) == 1

    next_p = coord.post(RUNS).json()["proposals"][0]
    path = f"/api/agent-proposals/{next_p['id']}/dismiss"
    assert coord.post(path, json={"reason": "   "}).status_code == 422
    dismissed = coord.post(path, json={"reason": "Already assigned"}).json()
    assert (dismissed["status"], dismissed["dismiss_reason"]) == ("dismissed", "Already assigned")
    assert coord.post(EVA + "/tasks", json={**task, "proposal_id": next_p["id"]}).status_code == 409
    events = coord.get("/api/audit").json()
    assert {("agent_proposal", "accepted"), ("agent_proposal", "dismissed")} <= {
        (e["entity"], e["action"]) for e in events}


def test_new_evidence_invalidates_unaccepted_proposal(login, stub_groq, monkeypatch):
    coord = login("Elira Dervishi")
    proposal = coord.post(RUNS).json()["proposals"][0]
    monkeypatch.setattr(client, "is_configured", lambda: False)
    new = coord.post("/api/inbox", json={"title": "Eva Stone follow-up", "author_role": "Technical Lead",
                                        "date": "2026-10-14", "body": "Eva Stone has a new follow-up."})
    assert new.status_code == 201, new.text
    r = coord.post(EVA + "/tasks", json={"title": "Use old proposal", "proposal_id": proposal["id"],
                                         "owner_role": "technical_owner"})
    assert r.status_code == 409, r.text
    assert coord.get(EVA).json()["tasks"] == []


def test_only_one_run_can_hold_case_lease(monkeypatch, login, stub_groq):
    first, second = login("Elira Dervishi"), login("Elira Dervishi")
    entered, release = Event(), Event()
    def pause(messages, tools, timeout):
        entered.set()
        assert release.wait(10)
        return stub_groq(messages, tools, timeout)
    monkeypatch.setattr(client, "agent_turn", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(first.post, RUNS)
        try:
            assert entered.wait(10)
            duplicate = second.post(RUNS)
            assert duplicate.status_code == 409, duplicate.text
        finally:
            release.set()
        assert active.result().json()["status"] == "completed"
    assert len(second.get(RUNS).json()) == 1
