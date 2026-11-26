"""The showcase dataset (data/showcase.json) loads through the real API, shows every scenario it promises, is
idempotent, and leaves the starter-pack hero case (Eva, ONB-005) untouched."""
import pytest

from app.config import get_settings
from app.seed.seed import run as run_seed


@pytest.fixture()
def showcase(app_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "SEED_SHOWCASE", True)
    message = run_seed()
    assert "Showcase loaded: 14 cases, 11 sources." in message, message
    return app_client


def _rules(client, ref):
    return {f["rule_id"] for f in client.get(f"/api/cases/{ref}").json()["findings"]}


def test_showcase_covers_every_angle(showcase, login):
    elira = login("Elira Dervishi")
    rows = {r["ref"]: r for r in elira.get("/api/cases?view=all").json()}
    assert {f"ONB-{n:03d}" for n in range(1, 25)} <= set(rows)

    # Final sign-off after every milestone and the employee's own access tests.
    assert rows["ONB-011"]["readiness"] == "signed_off"
    # Each rule fires somewhere, on the case built for it.
    assert "CLOSURE_CONFLICT" in _rules(elira, "ONB-015")
    assert {"UNANSWERED_REQUEST", "MISSING_MANAGER"} <= _rules(elira, "ONB-016")
    assert "STALE_TRACKER" in _rules(elira, "ONB-014")
    assert "MISSING_PROJECT" in _rules(elira, "ONB-017")
    assert "ACCESS_NOT_CONFIRMED" in _rules(elira, "ONB-013")

    # Recorded extractions are replayed through the verifier: highlighted claims without a model.
    sara = elira.get("/api/cases/ONB-012").json()
    assert {(c["scope"], c["value"]) for c in sara["claims"]} >= {("complex_scenarios", "coverage_pending")}
    assert [r["disposition"] for r in sara["reviews"]].count("keep_open") == 1

    # HR uploaded a document: extracted text, provenance, no file stored.
    elsa = elira.get("/api/cases/ONB-019").json()
    doc = next(s for s in elsa["sources"] if s["kind"] == "document")
    assert doc["document"]["filename"] == "HR_checkin_Elsa_Marku.txt" and doc["ingested_via"] == "upload"
    assert any(c["source_id"] == doc["id"] for c in elsa["claims"])

    # Inbox: matched, needs review and unmatched mail.
    statuses = {i["source"]["title"]: i["status"] for i in elira.get("/api/inbox").json()}
    assert statuses["Weekly KT update: Jon Pace"] == "matched"
    assert statuses["Helios access question for Dea Shala and Tom Reed"] == "needs_review"
    assert statuses["Laptop delivery schedule"] == "unmatched"

    # Work queues: paused, reassigned, claimed and overdue tasks exist.
    tasks = elira.get("/api/tasks?status=open").json()
    tasks = tasks["tasks"] if isinstance(tasks, dict) else tasks
    assert len(tasks) >= 8
    assert login("Ilda Berisha").get("/api/cases/ONB-013").status_code == 200   # employees see their own case
    assert login("Ilda Berisha").get("/api/cases/ONB-011").status_code == 404   # and nothing else


def test_hero_case_is_untouched_and_showcase_is_idempotent(showcase, login):
    eva = login("Elira Dervishi").get("/api/cases/ONB-005").json()
    assert eva["tasks"] == [] and eva["reviews"] == []
    assert any(f["rule_id"] == "CLOSURE_CONFLICT" for f in eva["findings"])
    before = len(login("Elira Dervishi").get("/api/cases?view=all").json())
    assert "Showcase" not in run_seed()
    assert len(login("Elira Dervishi").get("/api/cases?view=all").json()) == before
