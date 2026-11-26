"""Phase 3: authenticated relay intake, idempotency, review queue, durable jobs across an outage."""
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select

from app.ai import client
from app.config import get_settings
from app.db import SessionLocal
from app.models import AnalysisJob, Org, ServiceCredential, Source
from app.services import jobs

TOKEN = "grs_test_relay_token_value_0123456789"


@pytest.fixture
def relay(app_client):
    with SessionLocal() as db:
        org = db.execute(select(Org).where(Org.slug == "engineering-albania-demo")).scalar_one()
        db.add(ServiceCredential(org_id=org.id, name="mail-relay", scopes=["inbound:write"],
                                 token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest()))
        db.commit()
    return app_client


def _post(c, payload, token=TOKEN):
    return c.post("/api/integrations/inbound", json=payload, headers={"Authorization": f"Bearer {token}"})


MSG = {"external_id": "<msg-001@relay.example>", "received_at": "2026-10-14T08:15:00Z",
       "sender": "tech.lead@example.invalid", "subject": "ONB-005 Eva Stone: complex scenario 1 covered",
       "body": "Eva executed complex scenario 1 on her own today.", "author_role": "Technical Lead"}


def test_relay_auth_and_idempotent_delivery(relay, login):
    assert relay.post("/api/integrations/inbound", json=MSG).status_code == 401
    assert _post(relay, MSG, token="wrong").status_code == 401
    first = _post(relay, MSG)
    assert first.status_code == 200 and first.json()["status"] == "created"
    assert first.json()["case_ref"] == "ONB-005" and first.json()["match_status"] == "matched"
    again = _post(relay, MSG)
    assert again.json() == {"status": "duplicate", "source_id": first.json()["source_id"], "match_status": "matched"}
    assert _post(relay, {**MSG, "body": "Different text"}).status_code == 409
    with SessionLocal() as db:
        assert len(db.execute(select(Source).where(Source.external_id == MSG["external_id"])).scalars().all()) == 1
        assert len(db.execute(select(AnalysisJob).where(AnalysisJob.source_id == first.json()["source_id"]))
                   .scalars().all()) == 1
    coord = login("Elira Dervishi")
    src = next(s for s in coord.get("/api/cases/ONB-005").json()["sources"] if s["id"] == first.json()["source_id"])
    assert src["channel"] == "relay:mail-relay" and src["sender"] == MSG["sender"] and src["body"] == MSG["body"]
    # The audit trail records provenance, not a copy of the body.
    ev = next(e for e in coord.get("/api/audit?entity=source").json() if e["action"] == "relayed")
    assert ev["after"]["service_identity"] == "mail-relay" and "body" not in ev["after"]


def test_payload_validation_and_size(relay):
    assert _post(relay, {**MSG, "external_id": "x"}).status_code == 422
    assert _post(relay, {**MSG, "extra": "nope"}).status_code == 422
    big = {**MSG, "external_id": "<big@relay>", "body": "x" * 19000, "subject": "y" * 300}
    get_settings().INBOUND_MAX_BYTES, old = 1000, get_settings().INBOUND_MAX_BYTES
    try:
        assert _post(relay, big).status_code == 413
    finally:
        get_settings().INBOUND_MAX_BYTES = old


def test_ambiguous_message_waits_in_review_queue(relay, login):
    r = _post(relay, {**MSG, "external_id": "<msg-002@relay>", "subject": "Update on Eva Stone and Leo Marin",
                      "body": "Both had their onboarding sessions today."}).json()
    assert r["match_status"] == "needs_review" and r["case_ref"] is None and r["job_id"] is None
    coord = login("Elira Dervishi")
    queue = coord.get("/api/inbox?status=needs_review").json()
    item = next(i for i in queue if i["source"]["id"] == r["source_id"])
    assert {c["ref"] for c in item["candidates"]} == {"ONB-002", "ONB-005"}
    linked = coord.post(f"/api/inbox/{r['source_id']}/link", json={"case_id": "ONB-005"})
    assert linked.status_code == 200 and linked.json()["source"]["version"] == 2
    assert login("Eva Stone").get("/api/inbox?status=needs_review").json() == []


def test_outage_keeps_intake_and_manual_work_then_resumes(relay, login, monkeypatch):
    """The model is down: delivery succeeds, the job waits (no attempts spent), manual work continues. When the
    model returns the worker completes the job and only the current version feeds findings."""
    s = get_settings()
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(s, "ANALYSIS_WORKER", "external")  # nothing runs inline
    up = {"on": False}

    def handler(request):
        if not up["on"]:
            raise httpx.ConnectError("refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": s.LLM_MODEL, "digest": "sha256:" + "b" * 64}]})
        body = json.loads(json.loads(request.content)["messages"][1]["content"])["original_body"]
        quote = "Eva executed complex scenario 1 on her own today."
        claims = [{"claim": "complex_scenarios/coverage_complete", "quote": quote, "reference": None}] \
            if quote in body else []
        return httpx.Response(200, json={"message": {"role": "assistant", "content": json.dumps({"claims": claims})},
                                         "done": True, "done_reason": "stop"})

    client.set_transport(httpx.MockTransport(handler))
    try:
        r = _post(relay, {**MSG, "external_id": "<msg-003@relay>"}).json()
        coord = login("Elira Dervishi")
        assert coord.post("/api/cases/ONB-005/tasks", json={"title": "Manual work still fine",
                                                            "owner_role": "technical_owner"}).status_code == 201
        with SessionLocal() as db:
            job = db.get(AnalysisJob, r["job_id"])
            assert job.status == "queued"
            jobs.run_jobs(db, [job])
            job = db.get(AnalysisJob, r["job_id"])
            assert job.status == "waiting" and job.attempts == 0 and "unreachable" in (job.last_error or "")
            # A second delivery while waiting does not create a second job.
            assert jobs.enqueue_analysis(db, db.get(Source, r["source_id"]), reason="inbound").id == job.id
        up["on"] = True
        client.set_transport(httpx.MockTransport(handler))  # reset the cached status
        with SessionLocal() as db:
            job = db.get(AnalysisJob, r["job_id"])
            job.run_after = job.created_at  # due now
            db.commit()
            assert jobs.run_once(db) >= 1
            job = db.get(AnalysisJob, r["job_id"])
            assert job.status == "done" and job.outcome_mode == "live"
        d = coord.get("/api/cases/ONB-005").json()
        assert any(c["value"] == "coverage_complete" and c["source_id"] == r["source_id"] for c in d["claims"])
    finally:
        client.set_transport(None)


def test_relink_supersedes_queued_job(relay, login, monkeypatch):
    monkeypatch.setattr(get_settings(), "ANALYSIS_WORKER", "external")
    r = _post(relay, {**MSG, "external_id": "<msg-004@relay>"}).json()
    coord = login("Elira Dervishi")
    assert coord.post(f"/api/inbox/{r['source_id']}/link", json={"case_id": "ONB-006"}).status_code == 200
    with SessionLocal() as db:
        old = db.get(AnalysisJob, r["job_id"])
        jobs.run_jobs(db, [old])
        assert db.get(AnalysisJob, r["job_id"]).status == "superseded"
        # The worker restarts: a job whose lease expired is claimed again.
        newer = db.execute(select(AnalysisJob).where(AnalysisJob.status == "queued")).scalars().first()
        newer.status, newer.lease_until = "running", newer.created_at
        db.commit()
        assert jobs._claim(db, newer.id) is not None
