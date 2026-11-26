"""Password sign-in for the fictional demo accounts: hashed at rest, generic failures, throttled, demo orgs only."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.seed.seed import run as run_seed
from app.services.passwords import hash_password, throttle, verify_password

ELIRA = "elira.dervishi@demo.graft.example"


@pytest.fixture(autouse=True)
def _fresh_throttle():
    throttle._failures.clear()
    yield
    throttle._failures.clear()


def _login(app_client, email, password):
    return TestClient(app_client.app).post("/api/auth/login", json={"email": email, "password": password})


def test_hash_is_salted_and_verifies():
    a, b = hash_password("graft-demo"), hash_password("graft-demo")
    assert a != b and a.startswith("scrypt$") and "graft-demo" not in a
    assert verify_password("graft-demo", a) and not verify_password("graft-demo!", a)
    assert not verify_password("graft-demo", None) and not verify_password("x", "not-a-hash")


def test_demo_accounts_list_emails_and_the_shared_password(app_client):
    accounts = app_client.get("/api/auth/demo-accounts").json()
    assert all(a["email"].endswith(".graft.example") for a in accounts)
    assert app_client.get("/api/auth/demo-password").json() == {"password": "graft-demo"}
    assert app_client.get("/api/auth/config").json()["password_login"] is True
    with SessionLocal() as db:
        stored = db.execute(select(User.password_hash).where(User.email == ELIRA)).scalar_one()
    assert stored.startswith("scrypt$")


def test_right_password_signs_in_case_insensitive_email(app_client):
    c = TestClient(app_client.app)
    r = c.post("/api/auth/login", json={"email": " Elira.Dervishi@DEMO.graft.example ", "password": "graft-demo"})
    assert r.status_code == 200
    assert c.get("/api/auth/me").json()["user"]["name"] == "Elira Dervishi"
    audit = c.get("/api/audit?entity=session").json()
    assert any(e["action"] == "password_login" for e in (audit["events"] if isinstance(audit, dict) else audit))


def test_wrong_password_and_unknown_email_fail_the_same_way(app_client):
    wrong = _login(app_client, ELIRA, "nope-nope")
    unknown = _login(app_client, "nobody@demo.graft.example", "graft-demo")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Wrong email or password"}
    assert "graft_session" not in wrong.cookies


def test_repeated_failures_are_throttled(app_client):
    for _ in range(5):
        assert _login(app_client, ELIRA, "guess").status_code == 401
    # Locked for this email, even with the right password, until the window passes.
    assert _login(app_client, ELIRA, "graft-demo").status_code == 429
    assert _login(app_client, "eva.stone@demo.graft.example", "graft-demo").status_code == 200


def test_databases_seeded_before_passwords_get_credentials_on_start(app_client):
    with SessionLocal() as db:
        for u in db.execute(select(User)).scalars():
            u.password_hash, u.email = None, None
        db.commit()
    assert _login(app_client, ELIRA, "graft-demo").status_code == 401
    assert "credential" in run_seed()  # what the container runs on every start
    assert _login(app_client, ELIRA, "graft-demo").status_code == 200


def test_member_added_to_a_demo_org_can_sign_in(login, app_client):
    admin = login("Dren Basha")
    r = admin.post("/api/org/members", json={"name": "Arta Nova", "title": "New coordinator"})
    assert r.status_code == 201, r.text
    assert _login(app_client, "arta.nova@demo.graft.example", "graft-demo").status_code == 200


def test_password_login_is_off_outside_demo_mode(app_client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "AUTH_MODE", "oidc")
    assert _login(app_client, ELIRA, "graft-demo").status_code == 404
    assert TestClient(app_client.app).get("/api/auth/demo-password").status_code == 404
