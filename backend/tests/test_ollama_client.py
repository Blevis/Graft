"""The private Ollama provider, exercised through httpx.MockTransport (no model server needed in CI).

Covers: native /api/chat request shape with JSON-schema `format` and stream=false, verification of the full
response, cache identity (provider + digest), cold start/timeout, busy, invalid JSON, rejected cloud/unlisted models
and hosts, oversized input, multi-turn native tool calls, and the outage fallback."""
import json
import threading

import httpx
import pytest

from app.ai import agent, client
from app.config import get_settings

DIGEST = "sha256:" + "a" * 64


@pytest.fixture
def ollama(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(s, "LLM_MODEL", "qwen3:8b")
    monkeypatch.setattr(s, "LLM_QUEUE_WAIT_SECONDS", 0.05)
    calls = []
    state = {"chat": None, "down": False}

    def handler(request: httpx.Request):
        if state["down"]:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "digest": DIGEST}]})
        body = json.loads(request.content)
        calls.append(body)
        out = state["chat"](body) if callable(state["chat"]) else state["chat"]
        if isinstance(out, Exception):
            raise out
        return out

    client.set_transport(httpx.MockTransport(handler))
    yield calls, state
    client.set_transport(None)


def _reply(content=None, tool_calls=None, done_reason="stop"):
    msg = {"role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return httpx.Response(200, json={"model": "qwen3:8b", "message": msg, "done": True, "done_reason": done_reason,
                                     "prompt_eval_count": 100, "eval_count": 20})


def _extraction(body):
    payload = json.loads(body["messages"][1]["content"])
    text = payload["original_body"]
    claims = [{"claim": "complex_scenarios/coverage_complete", "quote": "Eva independently resolves everything.",
               "reference": None}]
    if "Two complex scenarios still need to be covered." in text:
        claims.append({"claim": "complex_scenarios/coverage_pending",
                       "quote": "Two complex scenarios still need to be covered.", "reference": None})
    if "The Line Manager considers onboarding closed." in text:
        claims.append({"claim": "onboarding_closure/reported_closed",
                       "quote": "The Line Manager considers onboarding closed.", "reference": None})
    return _reply(json.dumps({"claims": claims}))


def test_status_states_and_rejections(ollama, monkeypatch):
    _, state = ollama
    st = client.status(refresh=True)
    assert st["state"] == "available" and st["digest"] == DIGEST and st["provider"] == "ollama"
    state["down"] = True
    assert client.status(refresh=True)["state"] == "unavailable"
    s = get_settings()
    monkeypatch.setattr(s, "LLM_MODEL", "gpt-oss:120b-cloud")
    assert client.status()["state"] == "misconfigured" and "Cloud" in client.status()["detail"]
    monkeypatch.setattr(s, "LLM_MODEL", "llama3:70b")
    assert "approved list" in client.configuration_error()
    monkeypatch.setattr(s, "LLM_MODEL", "qwen3:8b")
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "https://api.example.com")
    assert "not an allowed private host" in client.configuration_error()
    with pytest.raises(client.AIUnavailable):
        client.extract({"original_body": "x"})


def test_live_extraction_native_format_and_verifier(ollama, login):
    calls, state = ollama
    state["chat"] = _extraction
    coord = login("Elira Dervishi")
    r = coord.post("/api/cases/ONB-005/analyze").json()
    assert {o["mode"] for o in r["outcomes"]} == {"live"}
    body = calls[0]
    assert body["stream"] is False and body["model"] == "qwen3:8b" and body["think"] is False
    assert body["format"]["properties"]["claims"]["items"]["properties"]["claim"]["enum"]
    assert body["options"]["temperature"] == 0 and body["options"]["num_ctx"] == get_settings().LLM_CONTEXT_TOKENS
    d = r["detail"]
    assert {(c["scope"], c["value"]) for c in d["claims"]} == {
        ("complex_scenarios", "coverage_pending"), ("onboarding_closure", "reported_closed")}
    assert all(x["reason"].startswith("no exact match") for x in d["rejected"])  # invented quote rejected
    assert any(f["rule_id"] == "CLOSURE_CONFLICT" for f in d["findings"])
    run = d["analysis"]["runs"][0]
    assert run["provider"] == "ollama" and run["model_digest"] == DIGEST
    assert all(r_["mode"] == "live" for r_ in d["analysis"]["runs"])
    # Same input and same pinned digest: verified cache, no new model call.
    n = len(calls)
    again = coord.post("/api/cases/ONB-005/analyze").json()
    assert {o["mode"] for o in again["outcomes"]} == {"cached"} and len(calls) == n


def test_invalid_json_and_truncation(ollama):
    calls, state = ollama
    state["chat"] = _reply("{not json")
    with pytest.raises(client.AIUnavailable, match="malformed JSON"):
        client.extract({"original_body": "x"})
    assert len(calls) == get_settings().LLM_MAX_ATTEMPTS
    state["chat"] = _reply('{"claims": [', done_reason="length")
    with pytest.raises(client.AIUnavailable, match="truncated"):
        client.extract({"original_body": "x"})


def test_timeout_cold_start_and_busy(ollama, monkeypatch):
    calls, state = ollama
    state["chat"] = lambda b: httpx.ReadTimeout("slow cold start")
    with pytest.raises(client.AIUnavailable, match="timeout"):
        client.extract({"original_body": "x"})
    # Busy: every slot taken -> AIBusy quickly instead of queueing without bound.
    sem = client._semaphore()
    assert sem.acquire(blocking=False)
    try:
        with pytest.raises(client.AIBusy):
            client.extract({"original_body": "x"})
        assert client.status(refresh=True)["state"] == "busy"
    finally:
        sem.release()


def test_oversized_input_is_refused_before_calling(ollama, monkeypatch):
    calls, state = ollama
    state["chat"] = _extraction
    monkeypatch.setattr(get_settings(), "LLM_CONTEXT_TOKENS", 1024)
    with pytest.raises(client.AIUnavailable, match="context budget"):
        client.extract({"original_body": "word " * 5000})
    assert calls == []


def test_outage_falls_back_to_recorded_examples_and_manual_work_continues(ollama, login):
    _, state = ollama
    state["down"] = True
    coord = login("Elira Dervishi")
    r = coord.post("/api/cases/ONB-005/analyze").json()
    assert {o["mode"] for o in r["outcomes"]} == {"replay"}  # E3/E4 recorded examples, labelled as such
    assert coord.post("/api/cases/ONB-005/suggest-task").status_code == 503
    assert coord.post("/api/cases/ONB-005/tasks", json={"title": "Manual follow-up", "owner_role": "technical_owner"}
                      ).status_code == 201


def test_suggest_task_validates_shape_and_citations(ollama, login):
    _, state = ollama
    state["chat"] = _reply(json.dumps({"title": "Cover the two outstanding complex scenarios",
                                       "owner_role": "technical_owner", "rationale": "Pending coverage.",
                                       "cited_claim_ids": ["not-a-real-id"]}))
    coord = login("Elira Dervishi")
    s = coord.post("/api/cases/ONB-005/suggest-task").json()
    assert s["owner_role"] == "technical_owner" and s["cited_claim_ids"] == []
    assert s["provider"] == "ollama" and s["model_digest"] == DIGEST
    assert coord.get("/api/cases/ONB-005").json()["tasks"] == []
    state["chat"] = _reply(json.dumps({"title": "x", "owner_role": "ceo", "rationale": "r", "cited_claim_ids": []}))
    assert coord.post("/api/cases/ONB-005/suggest-task").status_code == 503


def test_multi_turn_native_tool_calls(ollama, login):
    """The real agent loop against the stubbed server: native tool_calls (object arguments), tool results with
    tool_name, one nudge after a prose reply, and a validated submission."""
    calls, state = ollama
    seen = []

    def chat(body):
        msgs = body["messages"]
        seen.append([m["role"] for m in msgs])
        assert body["tools"] and all(t["type"] == "function" for t in body["tools"])
        if len(seen) == 1:
            return _reply("I think the case needs work.")  # prose, no tool call
        if msgs[-1]["role"] == "user":
            return _reply(tool_calls=[{"function": {"name": "list_claims", "arguments": {}}}])
        assert msgs[-1]["role"] == "tool" and msgs[-1]["tool_name"] == "list_claims"
        claims = json.loads(msgs[-1]["content"])
        pending = next(c for c in claims if c["value"] == "coverage_pending")
        draft = {"kind": "task", "title": "Plan coverage of the two complex scenarios", "body": "Follow up.",
                 "owner_role": "technical_owner", "cited_claim_ids": [pending["id"]]}
        return _reply(tool_calls=[{"function": {"name": "submit_proposals", "arguments": {
            "assessment": "Coverage is pending.", "proposals": [draft]}}}])

    state["chat"] = chat
    coord = login("Elira Dervishi")
    run = coord.post("/api/cases/ONB-005/agent-runs").json()
    assert run["status"] == "completed", run
    assert run["provider"] == "ollama" and run["model_digest"] == DIGEST
    assert [s["tool"] for s in run["steps"]] == ["list_claims", "submit_proposals"]
    assert seen[1][-1] == "user"  # the nudge


def test_malformed_tool_arguments_are_rejected_predictably(ollama, login):
    _, state = ollama
    state["chat"] = _reply(tool_calls=[{"function": {"name": "read_source", "arguments": "{broken"}}])
    run = login("Elira Dervishi").post("/api/cases/ONB-005/agent-runs").json()
    assert run["status"] == "failed" and run["proposals"] == []
    assert all(s["result_summary"].startswith("Rejected") for s in run["steps"])


def test_ai_layer_has_no_hosted_provider():
    import app.ai.client as c
    src = open(c.__file__).read().lower()
    assert "groq" not in src and "openai.com" not in src
    assert agent.MAX_SECONDS == get_settings().AGENT_MAX_SECONDS
