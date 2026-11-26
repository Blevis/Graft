"""The only module that talks to the LLM provider. One source per extraction call."""
import json
import re
import time
from functools import lru_cache
from pathlib import Path

import groq

from ..config import get_settings

HERE = Path(__file__).resolve().parent


class AIUnavailable(Exception):
    """Timeout, provider error, refusal, missing key or malformed output."""


@lru_cache
def _read(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def extract_schema() -> dict:
    from .versions import SCHEMA_VERSION
    return json.loads(_read(f"schemas/{SCHEMA_VERSION}.json"))


def is_configured() -> bool:
    return bool(get_settings().GROQ_API_KEY)


def _client() -> groq.Groq:
    s = get_settings()
    # max_retries=1 -> at most 2 attempts per source, each capped by the timeout.
    return groq.Groq(api_key=s.GROQ_API_KEY, timeout=s.LLM_TIMEOUT_SECONDS,
                     max_retries=max(0, s.LLM_MAX_ATTEMPTS - 1))


def _json_call(system: str, user_payload: dict, schema: dict, max_tokens: int, name: str,
               reasoning_effort: str | None = None) -> dict:
    if not is_configured():
        raise AIUnavailable("GROQ_API_KEY is not set")
    s = get_settings()
    try:
        response = _client().chat.completions.create(
            model=s.LLM_MODEL,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            # Strict mode = constrained decoding: output always matches the schema (gpt-oss models).
            response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
            **({"reasoning_effort": reasoning_effort} if reasoning_effort else {}),
        )
    except groq.APITimeoutError as e:
        raise AIUnavailable(f"timeout after {s.LLM_TIMEOUT_SECONDS:.0f}s") from e
    except groq.RateLimitError as e:
        raise AIUnavailable("rate limited") from e
    except groq.APIStatusError as e:
        raise AIUnavailable(f"provider error {e.status_code}") from e
    except groq.APIConnectionError as e:
        raise AIUnavailable("provider unreachable") from e

    choice = response.choices[0] if response.choices else None
    if choice is None:
        raise AIUnavailable("no output")
    if choice.finish_reason == "length":
        raise AIUnavailable("output truncated")
    text = choice.message.content
    if not text:
        raise AIUnavailable("no text output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIUnavailable("malformed JSON output") from e


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
    from .versions import SCHEMA_VERSION
    raw = _json_call(_read("prompts/extract_v1.txt"), payload, extract_schema(), max_tokens=4000, name=SCHEMA_VERSION)
    return _split_claims(raw)


SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "owner_role": {
            "type": "string",
            "enum": ["pmo_coordinator", "technical_owner", "line_manager", "employee"],
        },
        "rationale": {"type": "string"},
        "cited_claim_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "owner_role", "rationale", "cited_claim_ids"],
    "additionalProperties": False,
}


def suggest_task(payload: dict) -> dict:
    return _json_call(_read("prompts/suggest_v1.txt"), payload, SUGGEST_SCHEMA, max_tokens=2000, name="suggest_v1",
                      reasoning_effort="low")


def _rate_limit_wait(exc: Exception) -> float | None:
    """Seconds Groq asks us to wait (retry-after, else the token-bucket reset), or None if unknown."""
    headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
    value = headers.get("retry-after")
    if value:
        try:
            return float(value)
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset-tokens") or ""
    match = re.fullmatch(r"(?:(\d+)m)?(?:([\d.]+)s)?|([\d.]+)ms", reset)
    if not reset or not match:
        return None
    if match.group(3):
        return float(match.group(3)) / 1000
    return int(match.group(1) or 0) * 60 + float(match.group(2) or 0)


AGENT_MAX_COMPLETION_TOKENS = 2500
RATE_LIMIT_MARGIN_SECONDS = 3.0


def agent_turn(messages: list[dict], tools: list[dict], timeout: float) -> dict:
    """One tool-calling turn, bounded by `timeout` in total, including at most one wait after a rate limit."""
    import asyncio

    if not is_configured():
        raise AIUnavailable("GROQ_API_KEY is not set")
    settings = get_settings()
    started = time.monotonic()

    async def request(seconds):
        async with groq.AsyncGroq(api_key=settings.GROQ_API_KEY, max_retries=0, timeout=seconds) as sdk:
            return await sdk.chat.completions.create(
                model=settings.LLM_MODEL, messages=messages, tools=tools, tool_choice="required",
                max_completion_tokens=AGENT_MAX_COMPLETION_TOKENS, reasoning_effort="low",
            )

    waited = False
    while True:
        seconds = min(timeout - (time.monotonic() - started), settings.LLM_TIMEOUT_SECONDS)
        if seconds <= 0:
            raise AIUnavailable("Tool request timed out")
        try:
            response = asyncio.run(asyncio.wait_for(request(seconds), timeout=seconds))
            break
        except (TimeoutError, groq.APITimeoutError) as exc:
            raise AIUnavailable("Tool request timed out") from exc
        except groq.RateLimitError as exc:
            wait = _rate_limit_wait(exc)
            left = timeout - (time.monotonic() - started)
            if waited or wait is None or wait + RATE_LIMIT_MARGIN_SECONDS >= left:
                raise AIUnavailable("Provider error 429 (rate limited)") from exc
            waited = True
            time.sleep(wait + 0.5)
        except groq.APIStatusError as exc:
            raise AIUnavailable(f"Provider error {exc.status_code}") from exc
        except groq.APIConnectionError as exc:
            raise AIUnavailable("Provider unreachable") from exc

    if not response.choices or response.choices[0].finish_reason == "length":
        raise AIUnavailable("Missing or truncated tool response")
    calls = response.choices[0].message.tool_calls or []
    # Retain the protocol fields needed by later turns, excluding private reasoning.
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": call.id, "type": "function", "function": {
            "name": call.function.name, "arguments": call.function.arguments,
        }} for call in calls
    ]}


def answer_question(payload: dict, schema: dict) -> dict:
    return _json_call(_read("prompts/ask_v2.txt"), payload, schema, max_tokens=2000, name="ask_v2",
                      reasoning_effort="low")
