"""The tunnel gateway in front of Ollama, and the client's bearer token."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import client
from app.config import get_settings
from app.gateway import create_gateway

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def upstream():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "digest": "sha256:abc"}]})
        return httpx.Response(200, json={"message": {"content": "{}"}, "done_reason": "stop"})

    gw = TestClient(create_gateway(TOKEN, transport=httpx.MockTransport(handler)))
    return gw, seen


def test_gateway_requires_the_token(upstream):
    gw, seen = upstream
    assert gw.get("/api/tags").status_code == 401
    assert gw.get("/api/tags", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert gw.get("/api/tags", headers=AUTH).json()["models"][0]["name"] == "qwen3:8b"
    assert seen == [("GET", "/api/tags")]


def test_gateway_forwards_only_allowed_non_streaming_chat(upstream):
    gw, seen = upstream
    ok = {"model": "qwen3:8b", "stream": False, "messages": []}
    assert gw.post("/api/chat", headers=AUTH, json=ok).status_code == 200
    assert gw.post("/api/chat", headers=AUTH, json={**ok, "model": "llama3:70b"}).status_code == 403
    assert gw.post("/api/chat", headers=AUTH, json={**ok, "model": "gpt-oss:120b-cloud"}).status_code == 403
    assert gw.post("/api/chat", headers=AUTH, json={**ok, "stream": True}).status_code == 400
    for path in ("/api/pull", "/api/delete", "/api/generate", "/api/create"):
        assert gw.post(path, headers=AUTH, json={"model": "qwen3:8b"}).status_code == 404
    assert seen == [("POST", "/api/chat")]


def test_gateway_rejects_short_tokens():
    with pytest.raises(ValueError):
        create_gateway("short")


def test_client_sends_the_key_and_only_over_https(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "http://graft-ai.example.com")
    monkeypatch.setattr(s, "OLLAMA_ALLOWED_HOSTS", "graft-ai.example.com")
    monkeypatch.setattr(s, "OLLAMA_API_KEY", TOKEN)
    assert "https" in client.configuration_error()
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "https://graft-ai.example.com")
    assert client.configuration_error() is None

    headers = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers.get("authorization"))
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b", "digest": "sha256:abc"}]})

    client.set_transport(httpx.MockTransport(handler))
    try:
        assert client.status(refresh=True)["state"] == "available" and headers == [f"Bearer {TOKEN}"]
        monkeypatch.setattr(s, "OLLAMA_API_KEY", "x" * 32)
        st = client.status(refresh=True)
        assert st["state"] == "misconfigured" and "OLLAMA_API_KEY" in st["detail"]
    finally:
        client.set_transport(None)


def test_no_key_means_no_authorization_header(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setattr(s, "OLLAMA_API_KEY", "")
    seen = []
    client.set_transport(httpx.MockTransport(lambda r: seen.append(r.headers.get("authorization"))
                                             or httpx.Response(200, json={"models": []})))
    try:
        client.status(refresh=True)
        assert seen == [None]
    finally:
        client.set_transport(None)
