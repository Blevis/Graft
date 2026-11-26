"""The only module that talks to the model: a private Ollama server through its native /api/chat API.

Inference never leaves the private environment:
- the endpoint comes from server configuration only (OLLAMA_BASE_URL) and must be a loopback or explicitly allowed
  private host (OLLAMA_ALLOWED_HOSTS); there is no per-request override;
- only preinstalled, allowlisted model tags (LLM_ALLOWED_MODELS) are used; cloud tags are rejected;
- run Ollama with OLLAMA_NO_CLOUD=1 (docs/deployment.md).

Every structured call uses Ollama's JSON-schema `format` with stream=false, and the caller validates the full
response server-side. A bounded semaphore limits concurrent model calls; callers that cannot get a slot quickly
receive AIBusy instead of piling up. Application liveness (/api/health) never depends on the model."""
import json
import math
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..config import get_settings

HERE = Path(__file__).resolve().parent
PROVIDER = "ollama"
CLOUD_MARKERS = ("-cloud", ":cloud")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class AIUnavailable(Exception):
    """Model server down, timeout, misconfiguration, oversize input, refusal or malformed output."""


class AIBusy(AIUnavailable):
    """Every model slot is in use. Callers may retry later; background jobs wait."""


@lru_cache
def _read(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def extract_schema() -> dict:
    from .versions import SCHEMA_VERSION
    return json.loads(_read(f"schemas/{SCHEMA_VERSION}.json"))


# ---------- configuration and status ----------

def allowed_models() -> list[str]:
    return [m.strip() for m in get_settings().LLM_ALLOWED_MODELS.split(",") if m.strip()]


def configuration_error(model: str | None = None) -> str | None:
    s = get_settings()
    model = model or s.LLM_MODEL
    if not s.OLLAMA_BASE_URL:
        return "OLLAMA_BASE_URL is not set"
    url = urlparse(s.OLLAMA_BASE_URL)
    hosts = {h.strip().lower() for h in s.OLLAMA_ALLOWED_HOSTS.split(",") if h.strip()}
    if url.scheme not in ("http", "https") or (url.hostname or "").lower() not in hosts:
        return f"Model endpoint host '{url.hostname}' is not an allowed private host"
    if s.OLLAMA_API_KEY and url.scheme != "https" and (url.hostname or "").lower() not in LOOPBACK:
        return "OLLAMA_API_KEY is only sent over https (or http to this machine)"
    if any(m in model.lower() for m in CLOUD_MARKERS):
        return f"Cloud model '{model}' is not allowed"
    if model not in allowed_models():
        return f"Model '{model}' is not on the approved list"
    return None


def is_configured() -> bool:
    return configuration_error() is None


_status_cache: dict = {"at": 0.0, "value": None}
_slots: threading.BoundedSemaphore | None = None
_slots_lock = threading.Lock()


def _semaphore() -> threading.BoundedSemaphore:
    global _slots
    with _slots_lock:
        if _slots is None:
            _slots = threading.BoundedSemaphore(max(1, get_settings().LLM_MAX_CONCURRENCY))
        return _slots


def _http(timeout: float) -> httpx.Client:
    # trust_env=False: never route model traffic through an environment-configured proxy.
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.OLLAMA_API_KEY}"} if s.OLLAMA_API_KEY else None
    return httpx.Client(base_url=s.OLLAMA_BASE_URL, timeout=timeout, trust_env=False, headers=headers,
                        transport=_transport())


def _transport():
    """Test hook: tests install an httpx.MockTransport here. Production uses the default transport."""
    return _TRANSPORT


_TRANSPORT: httpx.BaseTransport | None = None


def set_transport(transport: httpx.BaseTransport | None) -> None:
    global _TRANSPORT, _slots
    _TRANSPORT = transport
    _status_cache.update(at=0.0, value=None)
    _slots = None


def status(refresh: bool = False) -> dict:
    """configured / available / busy / unavailable / misconfigured, plus the pinned model digest."""
    s = get_settings()
    err = configuration_error()
    if err:
        return {"state": "misconfigured", "provider": PROVIDER, "model": s.LLM_MODEL, "digest": None, "detail": err}
    if not refresh and _status_cache["value"] and time.monotonic() - _status_cache["at"] < 30:
        value = dict(_status_cache["value"])
    else:
        try:
            with _http(6.0) as h:
                r = h.get("/api/tags")
            if r.status_code in (401, 403):
                raise _GatewayRejected()
            r.raise_for_status()
            models = {m.get("name") or m.get("model"): m for m in r.json().get("models", [])}
            m = models.get(s.LLM_MODEL)
            value = ({"state": "available", "digest": m.get("digest"), "detail": None} if m else
                     {"state": "unavailable", "digest": None,
                      "detail": f"Model '{s.LLM_MODEL}' is not installed on the model server"})
            if m and s.LLM_MODEL_DIGEST and m.get("digest") != s.LLM_MODEL_DIGEST:
                value = {"state": "misconfigured", "digest": m.get("digest"),
                         "detail": "Installed model digest does not match LLM_MODEL_DIGEST (weights changed)"}
        except _GatewayRejected:
            value = {"state": "misconfigured", "digest": None,
                     "detail": "The model gateway rejected OLLAMA_API_KEY (check the token on both sides)"}
        except (httpx.HTTPError, ValueError) as e:
            value = {"state": "unavailable", "digest": None, "detail": f"Model server unreachable ({type(e).__name__})"}
        _status_cache.update(at=time.monotonic(), value=dict(value))
    if value["state"] == "available" and not _probe_free():
        value["state"] = "busy"
    return {"provider": PROVIDER, "model": s.LLM_MODEL, **value}


class _GatewayRejected(Exception):
    pass


def _probe_free() -> bool:
    sem = _semaphore()
    if sem.acquire(blocking=False):
        sem.release()
        return True
    return False


def model_digest() -> str | None:
    return status().get("digest")


# ---------- budget ----------

def estimate_tokens(text: str) -> int:
    """Conservative token estimate (no tokenizer dependency): ~3.5 characters per token."""
    return math.ceil(len(text) / 3.5)


def input_budget(output_tokens: int) -> int:
    return max(512, get_settings().LLM_CONTEXT_TOKENS - output_tokens - 256)


# ---------- calls ----------

last_call: dict = {}


def _chat(body: dict, timeout: float) -> dict:
    s = get_settings()
    err = configuration_error()
    if err:
        raise AIUnavailable(err)
    sem = _semaphore()
    if not sem.acquire(timeout=s.LLM_QUEUE_WAIT_SECONDS):
        raise AIBusy("model busy")
    started = time.monotonic()
    try:
        with _http(timeout) as h:
            r = h.post("/api/chat", json={"model": s.LLM_MODEL, "stream": False, **body})
    except httpx.TimeoutException as e:
        raise AIUnavailable(f"timeout after {timeout:.0f}s") from e
    except httpx.HTTPError as e:
        raise AIUnavailable("model server unreachable") from e
    finally:
        sem.release()
    if r.status_code == 404:
        raise AIUnavailable(f"model '{s.LLM_MODEL}' is not installed")
    if r.status_code in (401, 403):
        raise AIUnavailable("the model gateway rejected OLLAMA_API_KEY")
    if r.status_code >= 400:
        raise AIUnavailable(f"model server error {r.status_code}")
    try:
        data = r.json()
    except ValueError as e:
        raise AIUnavailable("model server returned non-JSON") from e
    last_call.clear()
    last_call.update(model=data.get("model"), prompt_tokens=data.get("prompt_eval_count"),
                     output_tokens=data.get("eval_count"), total_ms=round((time.monotonic() - started) * 1000),
                     load_ms=round((data.get("load_duration") or 0) / 1e6))
    if data.get("done_reason") == "length":
        raise AIUnavailable("output truncated at the context limit")
    return data


def _options(output_tokens: int) -> dict:
    s = get_settings()
    return {"temperature": 0, "num_ctx": s.LLM_CONTEXT_TOKENS, "num_predict": output_tokens}


def _think() -> dict:
    v = get_settings().LLM_THINK.strip().lower()
    if v in ("", "default"):
        return {}
    return {"think": False if v == "false" else True if v == "true" else v}


def _json_call(system: str, user_payload: dict, schema: dict, max_tokens: int) -> dict:
    s = get_settings()
    user = json.dumps(user_payload, ensure_ascii=False)
    if estimate_tokens(system + user) > input_budget(max_tokens):
        raise AIUnavailable("input exceeds the model context budget")
    body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema, "options": _options(max_tokens), **_think()}
    last: Exception | None = None
    for _ in range(max(1, s.LLM_MAX_ATTEMPTS)):
        try:
            data = _chat(body, s.LLM_TIMEOUT_SECONDS)
        except AIBusy:
            raise
        except AIUnavailable as e:
            if "unreachable" in str(e) or "not installed" in str(e) or "not allowed" in str(e) \
                    or "approved list" in str(e):
                raise
            last = e
            continue
        text = ((data.get("message") or {}).get("content") or "").strip()
        if not text:
            last = AIUnavailable("no text output")
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            last = AIUnavailable("malformed JSON output")
    raise last or AIUnavailable("no output")


def _split_claims(response: dict) -> dict:
    """extract_v2 asks for one `claim` field from an enum of valid "scope/value" pairs, so the model cannot pair a
    scope with another scope's value. Split it back into the v1 contract {scope, value, quote, reference}; anything
    malformed is passed through unchanged for the verifier to reject."""
    if not isinstance(response, dict) or not isinstance(response.get("claims"), list):
        return response
    claims = []
    for item in response["claims"]:
        if isinstance(item, dict) and isinstance(item.get("claim"), str) and "/" in item["claim"]:
            scope, value = item["claim"].split("/", 1)
            rest = {k: v for k, v in item.items() if k != "claim"}
            claims.append({"scope": scope, "value": value, **rest})
        else:
            claims.append(item)
    return {**response, "claims": claims}


def extract(payload: dict) -> dict:
    """payload: {source_id, case_id, source_type, author_role, source_date, original_body}"""
    from .versions import PROMPT_VERSION
    raw = _json_call(_read(f"prompts/{PROMPT_VERSION}.txt"), payload, extract_schema(), max_tokens=4000)
    return _split_claims(raw)


SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "owner_role": {
            "type": "string",
            "enum": ["pmo_coordinator", "project_manager", "technical_owner", "training_responsible", "line_manager",
                     "access_responsible", "employee"],
        },
        "rationale": {"type": "string"},
        "cited_claim_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "owner_role", "rationale", "cited_claim_ids"],
    "additionalProperties": False,
}


def suggest_task(payload: dict) -> dict:
    out = _json_call(_read("prompts/suggest_v1.txt"), payload, SUGGEST_SCHEMA, max_tokens=1500)
    if not isinstance(out, dict) or set(out) != set(SUGGEST_SCHEMA["required"]) or \
            out.get("owner_role") not in SUGGEST_SCHEMA["properties"]["owner_role"]["enum"] or \
            not isinstance(out.get("cited_claim_ids"), list):
        raise AIUnavailable("suggestion did not match the schema")
    return out


def answer_question(payload: dict, schema: dict, prompt_version: str = "ask_v3") -> dict:
    return _json_call(_read(f"prompts/{prompt_version}.txt"), payload, schema, max_tokens=2000)


AGENT_MAX_OUTPUT_TOKENS = 2500


def agent_turn(messages: list[dict], tools: list[dict], timeout: float) -> dict:
    """One tool-calling turn in Ollama's native format. Returns the assistant message to append to the history:
    {"role": "assistant", "content": str, "tool_calls": [{"function": {"name": str, "arguments": dict|str}}]}."""
    if timeout <= 0:
        raise AIUnavailable("Tool request timed out")
    prompt = json.dumps(messages, ensure_ascii=False)
    if estimate_tokens(prompt) > input_budget(AGENT_MAX_OUTPUT_TOKENS):
        raise AIUnavailable("conversation exceeds the model context budget")
    data = _chat({"messages": messages, "tools": tools, "options": _options(AGENT_MAX_OUTPUT_TOKENS), **_think()},
                 min(timeout, get_settings().LLM_TIMEOUT_SECONDS))
    msg = data.get("message") or {}
    calls = []
    for call in msg.get("tool_calls") or []:
        fn = (call or {}).get("function") or {}
        if isinstance(fn.get("name"), str):
            calls.append({"function": {"name": fn["name"], "arguments": fn.get("arguments", {})}})
    # Keep only protocol fields; private reasoning ("thinking") is not carried into later turns or stored.
    return {"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls}
