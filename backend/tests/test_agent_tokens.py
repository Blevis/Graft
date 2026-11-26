"""Token budget of the case agent: compact brief up front, low reasoning, one bounded wait after a rate limit."""
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.ai import agent, client
from app.ai.agent_tools import case_brief
from app.db import SessionLocal
from app.services.cases import case_detail, load_case
from app.services.org_settings import get_org_settings
from app.services.tenancy import load_ctx
from app.models import Membership, Org, User
from sqlalchemy import select


@pytest.fixture()
def coordinator(app_client):
    db = SessionLocal()
    m, u, o = db.execute(select(Membership, User, Org).join(User, User.id == Membership.user_id)
                         .join(Org, Org.id == Membership.org_id).where(User.name == "Elira Dervishi")).first()
    yield db, load_ctx(db, u.id, o.id)
    db.close()


def test_brief_carries_the_whole_case_compactly(coordinator):
    db, ctx = coordinator
    detail = case_detail(db, ctx, load_case(db, ctx, "ONB-005"))
    brief = case_brief(detail, get_org_settings(db, ctx.org_id))
    bodies = {s["ref"]: s["body"] for s in brief["sources"]}
    assert set(bodies) == {"E3", "E4"} and "Two complex scenarios" in bodies["E3"]
    assert {c["id"] for c in brief["claims"]} == {c["id"] for c in detail["claims"]}
    assert brief["findings"][0]["rule_id"] == "CLOSURE_CONFLICT"
    assert brief["case"]["tech_owner"]["name"] == "Ardit Kola"
    # No offsets, run ids or hashes: they cost tokens and help nothing.
    flat = json.dumps(brief)
    for noise in ("analysis_run_id", "body_sha256", '"start"', '"end"'):
        assert noise not in flat
    full = json.dumps(detail)
    assert len(flat) < len(full) / 2
    assert len(json.dumps(brief, separators=(",", ":"))) < 4000  # roughly 1k tokens for Eva's whole case


def test_agent_can_submit_on_its_first_call(monkeypatch, coordinator):
    db, ctx = coordinator
    case = load_case(db, ctx, "ONB-005")
    calls = []

    def turn(messages, tools, timeout):
        calls.append(messages)
        brief = json.loads(messages[1]["content"])["brief"]
        e3 = next(s["id"] for s in brief["sources"] if s["ref"] == "E3")
        draft = {"kind": "task", "title": "Plan coverage of the two complex scenarios", "body": "Cover them.",
                 "owner_role": "technical_owner", "owner_user_id": brief["case"]["tech_owner"]["id"],
                 "cited_source_ids": [e3]}
        return {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "submit_proposals",
            "arguments": json.dumps({"assessment": "E3 and E4 disagree.", "proposals": [draft]})}}]}

    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "agent_turn", turn)
    out = agent.run_agent(db, ctx, case)
    assert out["status"] == "completed" and len(calls) == 1 and len(out["steps"]) == 1
    assert out["prompt_version"] == "agent_v2"
