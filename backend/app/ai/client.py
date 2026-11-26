"""The only module that talks to the LLM provider. One source per extraction call."""
import json
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
    return json.loads(_read("schemas/extract_v1.json"))


def is_configured() -> bool:
    return bool(get_settings().GROQ_API_KEY)


def _client() -> groq.Groq:
    s = get_settings()
    # max_retries=1 -> at most 2 attempts per source, each capped by the timeout.
    return groq.Groq(api_key=s.GROQ_API_KEY, timeout=s.LLM_TIMEOUT_SECONDS,
                     max_retries=max(0, s.LLM_MAX_ATTEMPTS - 1))


def _json_call(system: str, user_payload: dict, schema: dict, max_tokens: int, name: str) -> dict:
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


def extract(payload: dict) -> dict:
    """payload: {source_id, case_id, source_type, author_role, source_date, original_body}"""
    return _json_call(_read("prompts/extract_v1.txt"), payload, extract_schema(), max_tokens=8000, name="extract_v1")


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
    return _json_call(_read("prompts/suggest_v1.txt"), payload, SUGGEST_SCHEMA, max_tokens=4000, name="suggest_v1")


def agent_turn(messages: list[dict], tools: list[dict], timeout: float) -> dict:
    """One tool-calling turn. Bound the entire provider request, including retries/reads."""
    import asyncio

    if not is_configured():
        raise AIUnavailable("GROQ_API_KEY is not set")
    settings = get_settings()
    seconds = min(timeout, settings.LLM_TIMEOUT_SECONDS)

    async def request():
        async with groq.AsyncGroq(api_key=settings.GROQ_API_KEY, max_retries=0, timeout=seconds) as sdk:
            return await sdk.chat.completions.create(
                model=settings.LLM_MODEL, messages=messages, tools=tools, tool_choice="required",
                max_completion_tokens=3500,
            )

    try:
        response = asyncio.run(asyncio.wait_for(request(), timeout=seconds))
    except (TimeoutError, groq.APITimeoutError) as exc:
        raise AIUnavailable("Tool request timed out") from exc
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
    return _json_call(_read("prompts/ask_v1.txt"), payload, schema, max_tokens=3000, name="ask_v1")
