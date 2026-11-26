"""The showcase dataset (data/showcase.json) loads through the real API, shows every scenario it promises, is
idempotent, and leaves the starter-pack hero case (Eva, ONB-005) untouched."""
import pytest

from app.config import get_settings
from app.seed.seed import run as run_seed


@pytest.fixture()
def showcase(app_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "SEED_SHOWCASE", True)
    message = run_seed()
    assert "Showcase loaded: 14 cases, 11 sources; 2 cases, 4 sources (chapter 2)." in message, message
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


def test_every_figure_has_at_least_one_example(showcase, login):
    """Every value the Insights, Metrics, Inbox and case pages can show has at least one showcase example."""
    elira = login("Elira Dervishi")
    ins = elira.get("/api/insights").json()
    assert ins["checks"]["required"] > 0 and ins["checks"]["met"] > 0
    stages = {s["stage"] for s in ins["stage_distribution"] if s["count"]}
    assert {"none", "pre_onboarding", "access", "shadowing", "supported_execution", "independent_execution",
            "validated", "unspecified"} <= stages
    assert {s["state"] for s in ins["review_states"]} >= {"none", "keep_open", "validate_scope", "close", "reopen"}
    assert all(ins["readiness"][k] for k in ("not_signed_off", "signed_off", "reopened"))
    assert all(a["count"] for a in ins["access"]["by_state"]), ins["access"]["by_state"]
    assert all(ins["tracker"]["age"].values()), ins["tracker"]["age"]
    # "no_date" stays empty by design: the task route fills a missing due date from the SLA.
    assert all(ins["due"][k] for k in ("overdue", "this_week", "next_week", "later")), ins["due"]
    assert {r["rule_id"] for r in ins["by_rule"]} >= {
        "CLOSURE_CONFLICT", "ACCESS_NOT_CONFIRMED", "UNANSWERED_REQUEST", "STALE_TRACKER", "MISSING_PROJECT",
        "MISSING_MANAGER", "MISSING_TECH_OWNER"}
    assert {k["kind"] for k in ins["evidence"]["by_kind"]} >= {"email", "update", "tracker_note", "tracker_row",
                                                               "document"}
    assert ins["evidence"]["rejected"] >= 2

    metrics = elira.get("/api/metrics").json()
    assert metrics["closes_with_unmet_checks"]["exceptions"] >= 1

    channels = {i["source"]["ingested_via"] for i in elira.get("/api/inbox").json()}
    assert {"paste", "webhook"} <= channels or {"paste", "relay"} <= channels, channels

    runs = elira.get("/api/cases/ONB-021/agent-runs").json()
    statuses = {p["status"] for r in runs for p in r["proposals"]}
    assert statuses == {"accepted", "dismissed"}
    origins = {t["origin"] for t in elira.get("/api/cases/ONB-021").json()["tasks"]}
    assert "ai_suggested_edited" in origins


def test_old_databases_get_their_checklists_back(app_client, login):
    """A database seeded before checklists existed showed 0 of 0 checks; start-up back-fills them."""
    from sqlalchemy import delete
    from app.db import SessionLocal
    from app.models import CaseRequirement
    with SessionLocal() as db:
        db.execute(delete(CaseRequirement))
        db.commit()
    assert login("Elira Dervishi").get("/api/insights").json()["checks"]["required"] == 0
    assert "11 checklist(s) back-filled" in run_seed()  # 10 starter cases + Sandbox Co
    assert login("Elira Dervishi").get("/api/insights").json()["checks"]["required"] > 0
