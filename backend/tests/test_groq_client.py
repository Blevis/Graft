"""The live path, with the Groq SDK stubbed: request shape, verification, and graceful failure."""
import json
from types import SimpleNamespace

import groq
import httpx

from app.ai import client


class FakeCompletions:
    def __init__(self, content=None, error=None, finish_reason="stop"):
        self.content, self.error, self.finish_reason, self.calls = content, error, finish_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        body = self.content(kwargs) if callable(self.content) else self.content
        msg = SimpleNamespace(content=body)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=self.finish_reason)])


def _install(monkeypatch, completions):
    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)))


def _echo_claims(kwargs):
    """Return one real claim for E3/E4 bodies and one invented quote."""
    body = json.loads(kwargs["messages"][1]["content"])["original_body"]
    claims = [{"scope": "complex_scenarios", "value": "coverage_complete",
               "quote": "Eva independently resolves complex scenarios.", "reference": None}]
    if "Two complex scenarios still need to be covered." in body:
        claims.append({"scope": "complex_scenarios", "value": "coverage_pending",
                       "quote": "Two complex scenarios still need to be covered.", "reference": None})
    if "The Line Manager considers onboarding closed." in body:
        claims.append({"scope": "onboarding_closure", "value": "reported_closed",
                       "quote": "The Line Manager considers onboarding closed.", "reference": None})
    return json.dumps({"claims": claims})


def test_live_extraction_uses_strict_schema_and_verifier(monkeypatch, login):
    fake = FakeCompletions(content=_echo_claims)
    _install(monkeypatch, fake)
    coord = login("Elira Dervishi")
    r = coord.post("/api/cases/ONB-005/analyze").json()
    assert {o["mode"] for o in r["outcomes"]} == {"live"}

    call = fake.calls[0]
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True
    assert call["response_format"]["json_schema"]["name"] == "extract_v1"
    assert call["messages"][0]["role"] == "system"

    d = r["detail"]
    assert {(c["scope"], c["value"]) for c in d["claims"]} == {
        ("complex_scenarios", "coverage_pending"), ("onboarding_closure", "reported_closed")}
    assert all(x["reason"].startswith("no exact match") for x in d["rejected"])
    assert any(f["rule_id"] == "CLOSURE_CONFLICT" for f in d["findings"])

    # Same input again: reused from the verified cache, no new provider call.
    n = len(fake.calls)
    again = coord.post("/api/cases/ONB-005/analyze").json()
    assert {o["mode"] for o in again["outcomes"]} == {"cached"} and len(fake.calls) == n


def test_provider_failure_falls_back(monkeypatch, login):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    _install(monkeypatch, FakeCompletions(error=groq.APITimeoutError(request=req)))
    coord = login("Elira Dervishi")
    r = coord.post("/api/cases/ONB-005/analyze").json()
    # Seeded recorded examples remain the evidence; the reason is surfaced.
    assert {o["mode"] for o in r["outcomes"]} == {"replay"}
    assert all("timeout" in (o["note"] or "") for o in r["outcomes"])
    assert coord.post("/api/cases/ONB-005/suggest-task").status_code == 503


def test_truncated_output_is_unavailable(monkeypatch):
    _install(monkeypatch, FakeCompletions(content='{"claims": [', finish_reason="length"))
    try:
        client.extract({"original_body": "x"})
    except client.AIUnavailable as e:
        assert "truncated" in str(e)
    else:
        raise AssertionError("expected AIUnavailable")


def test_suggest_task_validates_citations(monkeypatch, login):
    _install(monkeypatch, FakeCompletions(content=json.dumps({
        "title": "Cover the two outstanding complex scenarios", "owner_role": "technical_owner",
        "rationale": "Closure conflicts with pending coverage.", "cited_claim_ids": ["not-a-real-id"]})))
    coord = login("Elira Dervishi")
    s = coord.post("/api/cases/ONB-005/suggest-task").json()
    assert s["owner_role"] == "technical_owner" and s["cited_claim_ids"] == []
    assert s["model"] == "openai/gpt-oss-120b"
    assert coord.get("/api/cases/ONB-005").json()["tasks"] == []  # draft is never persisted
