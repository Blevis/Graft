import os
import tempfile
from pathlib import Path

# Isolated SQLite DB per test session; set before the app (and its engine) is imported.
_tmp = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.as_posix()}"
os.environ["DEMO_MODE"] = "true"
os.environ["AUTH_MODE"] = "demo"
os.environ["GROQ_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed.seed import run as run_seed  # noqa: E402


@pytest.fixture()
def app_client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    run_seed()
    return TestClient(create_app(static_dir="does-not-exist"))


@pytest.fixture()
def accounts(app_client):
    rows = app_client.get("/api/auth/demo-accounts").json()
    return {(r["org_name"], r["name"]): r for r in rows}


@pytest.fixture()
def login(app_client, accounts):
    def _login(name: str, org: str = "Engineering Albania (demo)") -> TestClient:
        c = TestClient(app_client.app)
        r = c.post("/api/auth/demo-login", json={"user_id": accounts[(org, name)]["user_id"]})
        assert r.status_code == 200, r.text
        return c

    return _login
