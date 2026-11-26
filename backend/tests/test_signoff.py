"""Phase 1: milestones, gated final sign-off, reopen, reassessment, legacy decisions."""
from app.db import SessionLocal
from app.models import EmployeeCase, Review, User
from sqlalchemy import select

TL = "Ardit Kola"


def _ids(c, case="ONB-005"):
    d = c.get(f"/api/cases/{case}").json()
    return d, {s["ref"]: s["id"] for s in d["sources"]}


def _review(c, case="ONB-005", **kw):
    body = {"disposition": "validate_scope", "scope": "Scope", "rationale": "Observed directly on real work.", **kw}
    return c.post(f"/api/cases/{case}/reviews", json=body)


def test_scoped_validation_then_gated_final_sign_off(login):
    tl, coord = login(TL), login("Elira Dervishi")
    d, src = _ids(tl)
    assert any(f["rule_id"] == "CLOSURE_CONFLICT" for f in d["findings"])  # E3 vs E4 still conflict
    reqs = {r["key"]: r for r in d["requirements"]}
    assert reqs["complex_scenarios"]["applicability"] == "required" and reqs["shadowing"]["applicability"] == "optional"
    assert reqs["access_ready"]["status"] == "satisfied"  # no tracked systems block Eva

    # A named scope is validated; overall readiness is not.
    r = _review(tl, milestone_key="complex_scenarios", scope="Complex scenarios", cited_source_ids=[src["E3"]])
    assert r.status_code == 201, r.text
    d = tl.get("/api/cases/ONB-005").json()
    assert d["readiness"]["status"] == "not_signed_off"
    assert next(x for x in d["requirements"] if x["key"] == "complex_scenarios")["status"] == "satisfied"
    assert _review(tl, milestone_key="complex_scenarios", cited_source_ids=[src["E3"]]).status_code == 409

    # Final sign-off: empty, foreign and premature closes all fail.
    close = {"disposition": "close", "scope": "Overall onboarding"}
    assert _review(tl, **close, cited_source_ids=[]).status_code == 422
    leo_e1 = {s["ref"]: s["id"] for s in coord.get("/api/cases/ONB-002").json()["sources"]}["E1"]
    assert _review(tl, **close, cited_source_ids=[leo_e1]).status_code == 422
    r = _review(tl, **close, cited_source_ids=[src["E3"], src["E4"]])
    assert r.status_code == 422
    assert {"milestone:kt_plan", "milestone:supported_execution"} <= set(r.json()["detail"]["unmet"])

    for key in ("kt_plan", "supported_execution"):
        assert _review(tl, milestone_key=key, scope=key, cited_source_ids=[src["E3"]]).status_code == 201
    r = _review(tl, **close, cited_source_ids=[src["E3"], src["E4"]], observed_stage="validated")
    assert r.status_code == 201, r.text
    d = coord.get("/api/cases/ONB-005").json()
    assert d["readiness"]["status"] == "signed_off" and d["readiness"]["signed_off_by"]["name"] == TL
    assert d["case"]["tracker_status"] == "Ready with Support"  # the tracker stays a separate report
    assert _review(tl, **close, cited_source_ids=[src["E3"]]).status_code == 409

    # The coordinator still cannot sign off; re-analysis keeps every decision.
    assert _review(coord, **close, cited_source_ids=[src["E3"]]).status_code == 403
    before = [(x["id"], x["disposition"]) for x in d["reviews"]]
    coord.post("/api/cases/ONB-005/analyze")
    assert [(x["id"], x["disposition"]) for x in coord.get("/api/cases/ONB-005").json()["reviews"]] == before

    # Reopen is explicit, audited and keeps the earlier record.
    r = tl.post("/api/cases/ONB-005/reviews", json={
        "disposition": "reopen", "scope": "Overall onboarding", "rationale": "A new production incident shows gaps."})
    assert r.status_code == 201 and r.json()["supersedes_review_id"]
    d = coord.get("/api/cases/ONB-005").json()
    assert d["readiness"]["status"] == "reopened" and len(d["reviews"]) == len(before) + 1
    assert ("review", "reopened") in {(e["entity"], e["action"]) for e in coord.get("/api/audit").json()}
    row = next(x for x in coord.get("/api/cases?view=all").json() if x["ref"] == "ONB-005")
    assert row["readiness"] == "reopened"


def test_blocking_access_and_documented_exceptions(login):
    nadia, admin, coord = login("Nadia Ferri"), login("Dren Basha"), login("Elira Dervishi")
    d, src = _ids(nadia, "ONB-002")
    milestones = [r["key"] for r in d["requirements"] if r["kind"] == "milestone" and r["applicability"] == "required"]
    assert milestones
    for key in milestones:
        assert _review(nadia, "ONB-002", milestone_key=key, cited_source_ids=[src["E2"]]).status_code == 201
    close = {"disposition": "close", "scope": "Overall onboarding", "cited_source_ids": [src["E2"]]}
    r = _review(nadia, "ONB-002", **close)
    assert r.status_code == 422 and "access:blocking" in r.json()["detail"]["unmet"]
    # An exception reason alone is not enough while the org has no documented exception policy.
    assert _review(nadia, "ONB-002", **close, exception_reason="Access tracked elsewhere").status_code == 422
    admin.patch("/api/settings", json={"allow_closure_exceptions": True})
    r = _review(nadia, "ONB-002", **close, exception_reason="Helix is retired for this project (approved by PMO).")
    assert r.status_code == 201 and r.json()["bypassed_criteria"] == ["access:blocking"]
    ev = [e for e in coord.get("/api/audit?entity=review").json() if e["action"] == "exception_sign_off"]
    assert ev and ev[0]["after"]["bypassed_criteria"] == ["access:blocking"]


def test_reassessment_and_legacy_disclosure(login):
    tl, coord = login(TL), login("Elira Dervishi")
    _, src = _ids(tl)
    assert _review(tl, disposition="keep_open", scope="Overall", cited_source_ids=[src["E3"]]).status_code == 201
    assert coord.get("/api/cases/ONB-005").json()["reassessment"]["needed"] is False
    coord.post("/api/inbox", json={"title": "ONB-005 Eva Stone: new incident", "body": "Eva handled an incident.",
                                   "author_role": "Technical Lead", "date": "2026-10-14"})
    re = coord.get("/api/cases/ONB-005").json()["reassessment"]
    assert re["needed"] and "after the keep open decision" in re["reasons"][0]

    with SessionLocal() as db:  # a close recorded before the gate existed
        case = db.execute(select(EmployeeCase).where(EmployeeCase.ref == "ONB-006")).scalar_one()
        ardit = db.execute(select(User).where(User.name == TL)).scalar_one()
        db.add(Review(org_id=case.org_id, case_id=case.id, disposition="close", scope="Overall",
                      rationale="Closed in the old tracker.", cited_source_ids=[], reviewer_user_id=ardit.id,
                      policy_version="legacy"))
        db.commit()
    d = coord.get("/api/cases/ONB-006").json()
    assert d["readiness"]["status"] == "signed_off"
    assert any("no evidence citation" in g for g in d["latest_review"]["gaps"])


def test_superseded_citation_is_rejected(login):
    coord, tl = login("Elira Dervishi"), login(TL)
    item = next(i for i in coord.get("/api/inbox").json() if i["source"]["ref"] == "E8")  # Atlas doc, no case
    old = item["source"]["id"]
    assert coord.post(f"/api/inbox/{old}/link", json={"case_id": "ONB-006"}).status_code == 200
    d = tl.get("/api/cases/ONB-006").json()
    new = next(s["id"] for s in d["sources"] if s["ref"] == "E8")
    assert _review(tl, "ONB-006", disposition="keep_open", cited_source_ids=[new]).status_code == 201
    assert new != old
