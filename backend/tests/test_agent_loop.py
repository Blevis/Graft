"""Exercise the real scoped tool loop with scripted Groq messages and the fictional seed."""
import asyncio
import json

import pytest
from sqlalchemy import select

from app.ai import agent, client
from app.db import SessionLocal
from app.models import Membership, Org, User
from app.services.cases import case_detail, load_case
from app.services.tenancy import load_ctx


@pytest.fixture
def coordinator(app_client):
    with SessionLocal() as db:
        membership, user, org = db.execute(
            select(Membership, User, Org)
            .join(User, User.id == Membership.user_id)
            .join(Org, Org.id == Membership.org_id)
            .where(User.name == "Elira Dervishi")
        ).one()
        yield db, load_ctx(db, user.id, org.id)


def tool_message(name, args):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "stub_call", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}
    }]}


def run_script(monkeypatch, coordinator, ref, messages):
    db, ctx = coordinator
    remaining = iter(messages)
    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "agent_turn", lambda messages, tools, timeout: next(remaining))
    return agent.run_agent(db, ctx, load_case(db, ctx, ref))


@pytest.mark.parametrize(("ref", "source_refs", "required_text", "kind", "title", "role"), [
    ("ONB-005", ["E3", "E4"], ["Two complex scenarios", "considers onboarding closed"],
     "task", "Plan coverage of the two complex scenarios", "technical_owner"),
    ("ONB-002", ["E2"], ["Orion Portal is still awaiting application-owner approval"],
     "access_followup", "Chase Orion approval and Helix provisioning; ask Leo to test Nova VPN", "pmo_coordinator"),
    ("ONB-009", ["E5"], ["No response recorded"],
     "message", "Follow up with the Technical Manager about Lina's role, KT owner and date", "pmo_coordinator"),
])
def test_agent_reads_scoped_originals_before_submitting(monkeypatch, coordinator, ref, source_refs,
                                                       required_text, kind, title, role):
    db, ctx = coordinator
    case = load_case(db, ctx, ref)
    returned_sources = []

    def turn(messages, tools, timeout):
        assert 0 < timeout <= agent.MAX_SECONDS
        if messages[-1]["role"] == "user":
            return tool_message("get_case", {})
        result = json.loads(messages[-1]["content"])
        if messages[-1]["name"] == "get_case":
            metadata = {s["ref"]: s["id"] for s in result["sources"]}
            returned_sources.extend(metadata[s] for s in source_refs)
        else:
            index = returned_sources.index(result["id"])
            assert required_text[index] in result["body"]
        count = sum(m.get("name") == "read_source" for m in messages)
        if count < len(returned_sources):
            return tool_message("read_source", {"source_id": returned_sources[count]})
        draft = {"kind": kind, "title": title, "body": title, "owner_role": role,
                 "cited_source_ids": returned_sources}
        if role == "technical_owner":
            info = json.loads(next(m["content"] for m in messages if m.get("name") == "get_case"))
            assert info["tech_owner"]["name"] == "Ardit Kola"
            draft["owner_user_id"] = info["tech_owner"]["id"]
        return tool_message("submit_proposals", {"assessment": "The case still needs follow-up.", "proposals": [draft]})

    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "agent_turn", turn)
    out = agent.run_agent(db, ctx, case)
    assert out["status"] == "completed"
    assert out["steps"][-1]["tool"] == "submit_proposals"
    assert out["proposals"][0]["title"] == title
    assert out["proposals"][0]["cited_source_ids"] == returned_sources
    assert out["proposals"][0]["due_date"] == "2026-10-16"
    assert case_detail(db, ctx, case)["tasks"] == []


def test_agent_logs_and_drops_cross_case_and_uncited_proposals(monkeypatch, coordinator):
    db, ctx = coordinator
    eva = case_detail(db, ctx, load_case(db, ctx, "ONB-005"))
    foreign = case_detail(db, ctx, load_case(db, ctx, "ONB-002"))["sources"][0]["id"]
    real_claim = eva["claims"][0]
    proposal = {"kind": "task", "title": "Cover remaining topics", "body": "Schedule a training session",
                "owner_role": "technical_owner", "cited_claim_ids": [real_claim["id"]]}
    out = run_script(monkeypatch, coordinator, "ONB-005", [
        tool_message("read_source", {"source_id": foreign}),
        tool_message("list_claims", {}),
        tool_message("submit_proposals", {"assessment": "Coverage is outstanding.", "proposals": [
            {**proposal, "cited_source_ids": [foreign]}, {**proposal, "cited_claim_ids": []}, proposal,
        ]}),
    ])
    assert out["status"] == "completed"
    assert len(out["proposals"]) == 1
    assert out["proposals"][0]["cited_source_ids"] == [real_claim["source_id"]]
    assert "unavailable on this case" in out["steps"][0]["result_summary"]
    assert "uncited proposal" in out["steps"][-1]["result_summary"]
    assert "citation outside current case evidence" in out["steps"][-1]["result_summary"]


def test_agent_bounds_total_calls_in_one_provider_batch(monkeypatch, coordinator):
    msg = tool_message("get_case", {})
    msg["tool_calls"] *= 9
    out = run_script(monkeypatch, coordinator, "ONB-005", [msg])
    assert out["status"] == "failed" and len(out["steps"]) == agent.MAX_CALLS == 8
    assert not out["proposals"]


def test_agent_rejects_late_tool_response(monkeypatch, coordinator):
    clock = iter([0, 1, agent.MAX_SECONDS + 1])
    monkeypatch.setattr(agent, "monotonic", lambda: next(clock))
    out = run_script(monkeypatch, coordinator, "ONB-005", [tool_message("get_case", {})])
    assert out["status"] == "failed" and "time limit" in out["assessment"]
    assert not out["proposals"] and not out["steps"]


def test_groq_tool_turn_cancels_a_stalled_request(monkeypatch):
    cancelled = []

    class StalledProvider:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = self.completions = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            pass

        async def create(self, **kwargs):
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client.groq, "AsyncGroq", StalledProvider)
    with pytest.raises(client.AIUnavailable, match="timed out"):
        client.agent_turn([], [], timeout=0.02)
    assert cancelled
