"""Phase 5: task-scoped access, restricted evidence through related records, retention, backup/restore."""
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import ops
from app.ai import client
from app.config import get_settings
from app.db import SessionLocal
from app.models import AnalysisRun, Org, Source
from app.models._base import utcnow
from app.services.retention import apply_retention


def _ids(c):
    return {u["name"]: u["id"] for u in c.get("/api/users").json()}


def test_assignee_sees_only_their_task_context(login, monkeypatch):
    coord = login("Elira Dervishi")
    leo = coord.get("/api/cases/ONB-002").json()
    e2 = next(s["id"] for s in leo["sources"] if s["ref"] == "E2")
    e1 = next(s["id"] for s in leo["sources"] if s["ref"] == "E1")
    # Erion (project member on Orion only) is asked to chase Leo's portal access, citing E2 only.
    coord.post("/api/cases/ONB-002/tasks", json={"title": "Confirm the Orion Portal approver",
                                                 "owner_user_id": _ids(coord)["Erion Daci"], "cited_source_ids": [e2]})
    erion = login("Erion Daci")
    d = erion.get("/api/cases/ONB-002").json()
    assert d["view"]["level"] == "task_only"
    assert [s["id"] for s in d["sources"]] == [e2]
    assert d["findings"] == [] and d["reviews"] == [] and d["access_items"] == [] and d["training"] == []
    assert d["case"]["tracker_status"] is None and len(d["tasks"]) == 1
    # Direct links: the cited source yes, the uncited one no (404, like another org).
    assert erion.get(f"/api/sources/{e2}").status_code == 200
    assert erion.get(f"/api/sources/{e1}").status_code == 404
    # Not through Inbox, Knowledge, Insights, search, timeline, reviews, agent traces or AI either.
    assert all(i["source"]["case_id"] != leo["case"]["id"] for i in erion.get("/api/inbox").json())
    ins = erion.get("/api/insights").json()
    assert all("Leo" not in json.dumps(t) for t in ins["overdue"]) and ins["totals"]["cases"] == 1  # Eva only
    row = next(r for r in erion.get("/api/cases?view=all&q=Leo").json())
    assert row["reasons"] == [] and row["tracker_status"] is None
    assert all(e["type"] in ("task_created", "task_done", "responsibility_assigned", "responsibility_ended")
               for e in erion.get("/api/cases/ONB-002/timeline").json())
    assert erion.get("/api/cases/ONB-002/reviews").json() == []
    assert erion.get("/api/cases/ONB-002/agent-runs").json() == []
    assert erion.get("/api/cases/ONB-002/training").json() == []
    calls = []
    monkeypatch.setattr(client, "is_configured", lambda: True)
    monkeypatch.setattr(client, "answer_question", lambda p, s, v="ask_v3": calls.append(p) or
                        {"scope": "unanswerable", "statements": []})
    erion.post("/api/ask", json={"question": "What is blocking Leo's access?"})
    assert all(src["case_ref"] != "ONB-002" and "Leo" not in src["body"] for c in calls for src in c["sources"])


def test_cross_tenant_ids_through_related_records(login):
    sam, coord = login("Sam Rivera", "Sandbox Co"), login("Elira Dervishi")
    eva = coord.get("/api/cases/ONB-005").json()
    src, finding = eva["sources"][0]["id"], eva["findings"][0]["id"]
    sbx = sam.get("/api/cases/SBX-001").json()["case"]["id"]
    assert sam.get(f"/api/sources/{src}").status_code == 404
    assert sam.post(f"/api/cases/{sbx}/tasks", json={"title": "Borrow", "owner_role": "org_admin",
                                                     "cited_source_ids": [src]}).status_code == 422
    assert sam.post(f"/api/cases/{sbx}/tasks", json={"title": "Borrow", "owner_role": "org_admin",
                                                     "finding_id": finding}).status_code == 422
    t = coord.post("/api/cases/ONB-005/tasks", json={"title": "Internal", "owner_role": "technical_owner"}).json()
    for path in (f"/api/tasks/{t['id']}/history", f"/api/tasks/{t['id']}/claim"):
        r = sam.get(path) if path.endswith("history") else sam.post(path)
        assert r.status_code == 404, path
    assert sam.post(f"/api/inbox/{src}/link", json={"case_id": sbx}).status_code == 404
    assert sam.get("/api/queues/mine").json()["items"] == []


def test_retention_dry_run_then_apply(login):
    with SessionLocal() as db:
        org = db.execute(select(Org).where(Org.slug == "engineering-albania-demo")).scalar_one()
        src = db.execute(select(Source).where(Source.org_id == org.id, Source.ref == "E3")).scalar_one()
        db.add(AnalysisRun(org_id=org.id, source_id=src.id, body_sha256=src.body_sha256, prompt_version="p",
                           schema_version="s", model="m", provider="groq", mode="live", status="ok",
                           raw_response={"claims": []}))
        db.commit()
        dry = apply_retention(db, org.id)
        assert dry["applied"] is False and dry["raw_model_outputs"] >= 1
        assert db.execute(select(AnalysisRun).where(AnalysisRun.provider == "groq")).scalar_one().raw_response
        applied = apply_retention(db, org.id, apply=True)
        db.commit()
        assert applied["raw_model_outputs"] >= 1
        assert db.execute(select(AnalysisRun).where(AnalysisRun.provider == "groq")).scalar_one().raw_response is None
        # Recorded (fictional) examples keep their committed payloads.
        assert db.execute(select(AnalysisRun).where(AnalysisRun.provider == "recorded")).scalars().first().raw_response


def test_unmatched_source_retention_respects_citations(login):
    coord = login("Elira Dervishi")
    item = coord.post("/api/inbox", json={"title": "Unrelated note", "body": "Nobody we know.",
                                          "author_role": "Someone", "date": "2026-10-01"}).json()
    with SessionLocal() as db:
        s = db.get(Source, item["source"]["id"])
        s.created_at = utcnow() - timedelta(days=400)
        db.commit()
        org_id = s.org_id
        report = apply_retention(db, org_id, apply=True)
        db.commit()
        assert report["unmatched_sources"]["eligible"] >= 1
        assert db.get(Source, item["source"]["id"]) is None
        assert db.execute(select(Source).where(Source.ref == "E8")).scalars().first()  # project-linked: kept


def test_sqlite_backup_restore_round_trip(login, tmp_path):
    coord, tl = login("Elira Dervishi"), login("Ardit Kola")
    e3 = next(s["id"] for s in tl.get("/api/cases/ONB-005").json()["sources"] if s["ref"] == "E3")
    assert tl.post("/api/cases/ONB-005/reviews", json={"disposition": "keep_open", "scope": "Overall",
                                                       "rationale": "Two scenarios still open.",
                                                       "cited_source_ids": [e3]}).status_code == 201
    url = get_settings().sqlalchemy_url
    out = tmp_path / "graft.backup"
    ops.main(["backup", "--out", str(out), "--database-url", url])
    target = f"sqlite:///{tmp_path / 'restored.db'}"
    ops.main(["restore", "--from", str(out), "--to", target])
    ops.main(["verify", "--database-url", target])  # exits non-zero on any integrity failure
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models import Review
    with Session(create_engine(target)) as db:
        r = db.execute(select(Review)).scalars().one()
        assert r.cited_source_ids == [e3] and db.get(Source, e3).body.count("Two complex scenarios") == 1
    with pytest.raises(SystemExit):
        ops.main(["restore", "--from", str(out), "--to", target])  # never over a non-empty database
