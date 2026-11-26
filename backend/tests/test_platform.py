"""Case fields maintained by the coordinator, the MISSING_READINESS_DATE rule, and production hardening."""
import pytest
from fastapi.testclient import TestClient

from app.config import DEV_SESSION_SECRET, InsecureConfig, Settings, check_production_settings


def test_readiness_date_and_role_null_until_recorded(login):
    coord = login("Elira Dervishi")
    case = coord.get("/api/cases/ONB-009").json()["case"]
    assert case["expected_readiness_date"] is None and case["exact_role"] is None

    r = coord.patch("/api/cases/ONB-009", json={"expected_readiness_date": "2026-11-02", "exact_role": "QA Analyst"})
    assert r.status_code == 200, r.text
    assert r.json()["case"]["expected_readiness_date"] == "2026-11-02"
    assert r.json()["case"]["exact_role"] == "QA Analyst"

    # Omitted keys are untouched; explicit null clears.
    r = coord.patch("/api/cases/ONB-009", json={"exact_role": None})
    assert r.json()["case"]["exact_role"] is None
    assert r.json()["case"]["expected_readiness_date"] == "2026-11-02"

    events = coord.get("/api/audit?entity=case").json()
    assert [e["action"] for e in events].count("updated") == 2
    assert events[0]["before"] == {"exact_role": "QA Analyst"} and events[0]["after"] == {"exact_role": None}


def test_only_coordinator_or_admin_can_patch(login):
    for name in ("Ardit Kola", "Luca Gray", "Eva Stone", "Mira Shehu"):
        assert login(name).patch("/api/cases/ONB-005", json={"exact_role": "x"}).status_code == 403, name
    assert login("Sam Rivera", org="Sandbox Co").patch("/api/cases/ONB-005", json={"exact_role": "x"}).status_code == 404


def test_missing_readiness_date_rule_is_a_setting(login):
    coord, admin = login("Elira Dervishi"), login("Dren Basha")
    rules = lambda: {f["rule_id"] for f in coord.get("/api/cases/ONB-010").json()["findings"]}  # noqa: E731
    assert "MISSING_READINESS_DATE" not in rules()  # off by default
    admin.patch("/api/settings", json={"flag_missing_readiness_date": True})
    assert "MISSING_READINESS_DATE" in rules()
    coord.patch("/api/cases/ONB-010", json={"expected_readiness_date": "2026-10-30"})
    assert "MISSING_READINESS_DATE" not in rules()


def test_insecure_secret_refused_outside_demo():
    check_production_settings(Settings(DEMO_MODE=True, SESSION_SECRET=DEV_SESSION_SECRET))  # demo: allowed
    with pytest.raises(InsecureConfig):
        check_production_settings(Settings(DEMO_MODE=False, SESSION_SECRET=DEV_SESSION_SECRET))
    with pytest.raises(InsecureConfig):
        check_production_settings(Settings(DEMO_MODE=False, SESSION_SECRET="short"))
    oidc = dict(AUTH_MODE="oidc", OIDC_ISSUER="https://idp.example", OIDC_CLIENT_ID="graft",
                OIDC_REDIRECT_URI="https://graft.example/api/auth/oidc/callback", OIDC_ORG_SLUG="acme")
    check_production_settings(Settings(DEMO_MODE=False, SESSION_SECRET="x" * 48, **oidc))
    # Fail closed: production without OIDC, or OIDC with missing/insecure settings, refuses to start.
    with pytest.raises(InsecureConfig, match="AUTH_MODE=oidc"):
        check_production_settings(Settings(DEMO_MODE=False, SESSION_SECRET="x" * 48, AUTH_MODE="demo"))
    with pytest.raises(InsecureConfig, match="OIDC_CLIENT_ID"):
        check_production_settings(Settings(DEMO_MODE=False, SESSION_SECRET="x" * 48, **{**oidc, "OIDC_CLIENT_ID": ""}))
    with pytest.raises(InsecureConfig, match="https"):
        check_production_settings(Settings(DEMO_MODE=False, SESSION_SECRET="x" * 48,
                                           **{**oidc, "OIDC_ISSUER": "http://idp.example"}))


def test_secure_cookie_only_over_https(app_client, accounts):
    uid = accounts[("Engineering Albania (demo)", "Elira Dervishi")]["user_id"]
    https = TestClient(app_client.app, base_url="https://testserver")
    assert "secure" in https.post("/api/auth/demo-login", json={"user_id": uid}).headers["set-cookie"].lower()
    http = TestClient(app_client.app)
    assert "secure" not in http.post("/api/auth/demo-login", json={"user_id": uid}).headers["set-cookie"].lower()
