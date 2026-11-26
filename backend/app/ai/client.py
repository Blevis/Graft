"""The only module that talks to the LLM provider. One source per extraction call."""
import json
from functools import lru_cache
from pathlib import Path

import anthropic

from ..config import get_settings

HERE = Path(__file__).resolve().parent


class AIUnavailable(Exception):
    """Timeout, provider error, refusal, missing key or malformed output."""


@lru_cache
def _read(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def extract_schema() -> dict:
    return json.loads(_read("schemas/extract_v1.json"))


def is_configured() -> bool:
    return bool(get_settings().ANTHROPIC_API_KEY)


def _client() -> anthropic.Anthropic:
    s = get_settings()
    # max_retries=1 -> at most 2 attempts per source, each capped by the timeout.
    return anthropic.Anthropic(api_key=s.ANTHROPIC_API_KEY, timeout=s.LLM_TIMEOUT_SECONDS,
                               max_retries=max(0, s.LLM_MAX_ATTEMPTS - 1))


def _json_call(system: str, user_payload: dict, schema: dict, max_tokens: int) -> dict:
    if not is_configured():
        raise AIUnavailable("ANTHROPIC_API_KEY is not set")
    s = get_settings()
    try:
        response = _client().beta.messages.create(
            model=s.LLM_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            # Server-side refusal fallback: on a policy decline the API re-runs on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.APITimeoutError as e:
        raise AIUnavailable(f"timeout after {s.LLM_TIMEOUT_SECONDS:.0f}s") from e
    except anthropic.RateLimitError as e:
        raise AIUnavailable("rate limited") from e
    except anthropic.APIStatusError as e:
        raise AIUnavailable(f"provider error {e.status_code}") from e
    except anthropic.APIConnectionError as e:
        raise AIUnavailable("provider unreachable") from e

    if response.stop_reason == "refusal":
        raise AIUnavailable("model declined the request")
    if response.stop_reason == "max_tokens":
        raise AIUnavailable("output truncated")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AIUnavailable("no text output")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIUnavailable("malformed JSON output") from e


def extract(payload: dict) -> dict:
    """payload: {source_id, case_id, source_type, author_role, source_date, original_body}"""
    return _json_call(_read("prompts/extract_v1.txt"), payload, extract_schema(), max_tokens=8000)


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
    return _json_call(_read("prompts/suggest_v1.txt"), payload, SUGGEST_SCHEMA, max_tokens=4000)
