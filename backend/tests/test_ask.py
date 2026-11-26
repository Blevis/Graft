import pytest

from app.ai import client


def _stub(monkeypatch, select):
    calls = []
    monkeypatch.setattr(client, "is_configured", lambda: True)

    def respond(payload, schema):
        calls.append(payload)
        assert schema["additionalProperties"] is False
        return select(payload)

    monkeypatch.setattr(client, "answer_question", respond)
    return calls


def _eva_evidence(payload):
    sources = {s["ref"]: s for s in payload["sources"]}
    return {"decision_question": False, "citations": [
        {"source_id": sources["E3"]["source_id"], "quote": "Two complex scenarios still need to be covered."},
        {"source_id": sources["E4"]["source_id"], "quote": "The Line Manager considers onboarding closed."},
    ]}


def test_cited_case_answer_and_readiness_deferral(monkeypatch, login):
    _stub(monkeypatch, _eva_evidence)
    user = login("Eva Stone")
    path = "/api/cases/ONB-005"
    before = user.get(path).json()
    result = user.post("/api/ask", json={"case_id": "ONB-005", "question": "Why was my case flagged?"})
    assert result.status_code == 200
    answer = result.json()
    assert answer["mode"] == "live" and answer["refused"] is False and answer["prompt_version"] == "ask_v2"
    for citation in answer["citations"]:
        source = next(s for s in before["sources"] if s["id"] == citation["source_id"])
        assert source["body"].count(citation["quote"]) == 1
        assert citation["quote"] in answer["answer"]
        assert any(c["id"] == citation["claim_id"] for c in before["claims"])
    assert len(answer["citations"]) == 2
    for decision in ("Is Eva ready?", "Can Eva work independently?", "Which employees are cleared for production?"):
        readiness = user.post("/api/ask", json={"case_id": "ONB-005", "question": decision}).json()
        assert readiness["refused"] and "technical owner" in readiness["answer"].lower()
        assert readiness["citations"] == answer["citations"]
    assert user.get(path).json() == before


@pytest.mark.parametrize("citation,expected", [
    (lambda source: {"source_id": "other-case", "quote": source["body"]}, False),
    (lambda source: {"source_id": source["source_id"], "quote": "An unsupported claim."}, False),
    (lambda source: {"source_id": source["source_id"], "quote": " "}, False),
    (lambda source: {"source_id": source["source_id"], "quote": source["body"]}, True),
])
def test_portfolio_limits_sources_before_model_and_validates_returned_quotes(monkeypatch, login, citation, expected):
    calls = _stub(monkeypatch, lambda p: {"decision_question": False, "citations": [citation(p["sources"][0])]})
    leo = login("Leo Marin")
    result = leo.post("/api/ask", json={"question": "Which access is blocking Leo?"}).json()
    assert {s["ref"] for s in calls[0]["sources"]} == {"E1", "E2"}
    assert bool(result["citations"]) == expected
    assert result["refused"] == (not expected)
    assert leo.post("/api/ask", json={"case_id": "ONB-005", "question": "Why?"}).status_code == 404
    assert login("Sam Rivera", "Sandbox Co").post("/api/ask", json={
        "case_id": "ONB-005", "question": "Show the evidence"}).status_code == 404
    assert len(calls) == 1


def test_disabled_unavailable_and_unsupported(monkeypatch, login):
    coordinator = login("Elira Dervishi")
    prompt = {"case_id": "ONB-005", "question": "Is Eva ready?"}
    response = coordinator.post("/api/ask", json=prompt).json()
    assert response["mode"] == "unavailable" and response["refused"] and response["model"] is None
    assert "technical owner" in response["answer"].lower()
    calls = _stub(monkeypatch, lambda p: {"decision_question": False, "citations": []})
    response = coordinator.post("/api/ask", json={"question": "What is the price of a guitar?"}).json()
    assert response["refused"] and not response["citations"] and "verified source" in response["answer"]
    assert login("Dren Basha").patch("/api/settings", json={"ai_enabled": False}).status_code == 200
    response = coordinator.post("/api/ask", json=prompt).json()
    assert response["mode"] == "unavailable" and response["refused"] and len(calls) == 1


def test_ask_requires_user_and_question(app_client, login):
    assert app_client.post("/api/ask", json={"question": "Who owns this?"}).status_code == 401
    assert login("Elira Dervishi").post("/api/ask", json={"question": "  "}).status_code == 422


def test_selected_fragment_preserves_original_negation(monkeypatch, login):
    def selection(payload):
        source = next(s for s in payload["sources"] if s["ref"] == "E2")
        return {"decision_question": False, "citations": [{"source_id": source["source_id"], "quote": "provisioned."}]}

    _stub(monkeypatch, selection)
    answer = login("Leo Marin").post("/api/ask", json={"case_id": "ONB-002", "question": "Is Helix provisioned?"}).json()
    assert answer["citations"][0]["quote"] == "Helix Service Desk has not yet been provisioned."
    assert answer["citations"][0]["quote"] in answer["answer"]
