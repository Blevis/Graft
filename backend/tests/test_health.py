from fastapi.testclient import TestClient

from app.main import create_app


def test_health():
    client = TestClient(create_app(static_dir="does-not-exist"))
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_spa_fallback_and_api_404(tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    client = TestClient(create_app(static_dir=tmp_path))

    assert client.get("/").text == "<html>spa</html>"
    assert client.get("/app/cases/ONB-005").text == "<html>spa</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/../../etc/passwd").text == "<html>spa</html>"
