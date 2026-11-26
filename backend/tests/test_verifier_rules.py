from datetime import date

from app.ai.verifier import verify
from app.services.rules import working_days_between

E3 = ("Eva completed the first training topics and can handle standard requests with occasional support. "
      "Two complex scenarios still need to be covered. The Technical Lead classifies her as Ready with Support.")


def test_offsets_computed_server_side():
    v = verify(E3, {"claims": [{"scope": "complex_scenarios", "value": "coverage_pending",
                                "quote": "Two complex scenarios still need to be covered.", "reference": None}]})
    assert v.status == "ok"
    assert (v.accepted[0]["start"], v.accepted[0]["end"]) == (98, 145)


def test_invented_quote_rejected_siblings_kept():
    v = verify(E3, {"claims": [
        {"scope": "initial_training", "value": "completed", "quote": "Eva completed the first training topics",
         "reference": None},
        {"scope": "complex_scenarios", "value": "coverage_complete",
         "quote": "Eva independently resolves complex scenarios.", "reference": None},
    ]}, "E3")
    assert v.status == "partial" and len(v.accepted) == 1
    assert v.rejected[0]["reason"] == "no exact match in E3"


def test_envelope_and_pair_validation():
    assert verify(E3, {"claims": [], "extra": 1}).status == "failed"
    assert verify(E3, [1]).status == "failed"
    v = verify(E3, {"claims": [{"scope": "standard_requests", "value": "completed",
                                "quote": "occasional support", "reference": None}]})
    assert v.rejected and "unsupported" in v.rejected[0]["reason"]


def test_access_claim_needs_reference_in_span():
    body = "Nova VPN is active. Orion Portal is still awaiting application-owner approval."
    ok = verify(body, {"claims": [{"scope": "access", "value": "active", "quote": "Nova VPN is active.",
                                   "reference": "Nova VPN"}]})
    bad = verify(body, {"claims": [{"scope": "access", "value": "active", "quote": "Nova VPN is active.",
                                    "reference": "Orion Portal"}]})
    assert ok.status == "ok" and bad.status == "partial"


def test_working_days():
    assert working_days_between(date(2026, 10, 8), date(2026, 10, 14)) == 4
