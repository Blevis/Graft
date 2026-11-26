"""Read-only, extractive Q&A over evidence visible to the requesting user."""
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..services.cases import load_case
from ..services.evidence import current_claims, latest_sources
from ..services.org_settings import get_org_settings
from ..services.tenancy import Ctx
from ..services.visibility import sees_all, visible_cases
from . import client
from .verifier import quote_error

PROMPT_VERSION = "ask_v1"
MAX_SOURCES = 24
MAX_CONTEXT_CHARS = 80_000
NO_EVIDENCE = "I couldn't find a verified source that answers that question."
DECISION_HANDOFF = "The technical owner must review the evidence and record the readiness decision."
DECISION_REQUEST = re.compile(
    r"\b(?:is|are|am|declare|deem|mark|confirm|certify|decide|assess|judge)\b[^?!.]{0,70}"
    r"\b(?:ready|cleared for (?:production|independent work)|fit for (?:production|independent work))\b"
    r"|\b(?:can|could|should|may)\b[^?!.]{0,70}\b(?:close|sign off|work independently|work (?:alone|unsupervised))\b",
    re.IGNORECASE,
)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str
    quote: str


class SelectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision_question: bool
    citations: list[Selection]


class AskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    case_id: str | None = Field(default=None, min_length=1, max_length=100)


def _result(answer, *, citations=(), refused=True, mode="unavailable", model=None):
    return {"answer": answer, "citations": list(citations), "refused": refused, "mode": mode,
            "model": model, "prompt_version": PROMPT_VERSION}


def _sources(db, ctx, case, question):
    if case:
        cases = {case.id: case}
        sources = latest_sources(db, ctx.org_id, case_id=case.id)
    else:
        cases = {c.id: c for c in db.scalars(visible_cases(ctx))}
        if sees_all(ctx):
            sources = latest_sources(db, ctx.org_id)
        else:
            sources = [s for c in cases.values() for s in latest_sources(db, ctx.org_id, case_id=c.id)]

    words = set(re.findall(r"\w+", question.casefold()))

    def relevance(source):
        emp = cases.get(source.case_id)
        label = f"{emp.employee} {emp.ref}" if emp else ""
        metadata = f"{label} {source.ref or ''} {source.title or ''}"
        return 3 * len(words.intersection(re.findall(r"\w+", metadata.casefold()))) + len(
            words.intersection(re.findall(r"\w+", source.body.casefold())))

    selected = {}
    payload = []
    characters = 0
    for source in sorted(sources, key=relevance, reverse=True):
        if characters + len(source.body) > MAX_CONTEXT_CHARS:
            continue
        employee_case = cases.get(source.case_id)
        payload.append({"source_id": source.id, "ref": source.ref, "title": source.title,
                        "employee": employee_case.employee if employee_case else None,
                        "case_ref": employee_case.ref if employee_case else None,
                        "author_role": source.author_role,
                        "date": source.date.isoformat() if source.date else None, "body": source.body})
        selected[source.id] = source
        characters += len(source.body)
        if len(selected) == MAX_SOURCES:
            break
    return selected, payload


def _in_context(body: str, quote: str) -> str:
    """Keep original negations and qualifications even if a model selects a fragment."""
    start = body.index(quote)
    end = start + len(quote)
    left, right = 0, len(body)
    for boundary in re.finditer(r"(?<=[.!?])\s+|\n+", body):
        if boundary.end() <= start:
            left = boundary.end()
        if boundary.start() >= end:
            right = boundary.start()
            break
    return body[left:right].strip()


def answer_question(db: Session, ctx: Ctx, question: str, case_id: str | None = None) -> dict:
    # Resolve scope before handling availability so hidden records still behave like missing ones.
    case = load_case(db, ctx, case_id) if case_id is not None else None
    decision = bool(DECISION_REQUEST.search(question))
    handoff = f" {DECISION_HANDOFF}" if decision else ""
    if not get_org_settings(db, ctx.org_id)["ai_enabled"]:
        return _result(f"Ask Graft is disabled for this organisation.{handoff}")
    if not client.is_configured():
        return _result(f"Ask Graft is unavailable because the AI provider is not configured.{handoff}")

    sources, payload = _sources(db, ctx, case, question)
    if not sources:
        return _result(DECISION_HANDOFF if decision else NO_EVIDENCE)
    model = get_settings().LLM_MODEL
    try:
        raw = client.answer_question({"question": question, "sources": payload}, SelectionResult.model_json_schema())
        result = SelectionResult.model_validate(raw)
    except client.AIUnavailable as exc:
        return _result(f"Ask Graft is unavailable ({exc}).{handoff}")
    except ValidationError:
        return _result(DECISION_HANDOFF if decision else NO_EVIDENCE, mode="live", model=model)

    decision = decision or result.decision_question
    refusal = _result(DECISION_HANDOFF if decision else NO_EVIDENCE, mode="live", model=model)
    if not 1 <= len(result.citations) <= 6:
        return refusal
    # Refuse the entire selection if any citation fails. Dropping a conflicting source could change the answer.
    selected = {}
    for item in result.citations:
        source = sources.get(item.source_id)
        if source is None or quote_error(source.body, item.quote, source.ref or source.id):
            return refusal
        passage = _in_context(source.body, item.quote)
        if quote_error(source.body, passage, source.ref or source.id):
            return refusal
        selected[(source.id, passage)] = source

    claims, _, _ = current_claims(db, {s.id: s for s in selected.values()}.values())
    claim_ids = {(claim.source_id, claim.quote): claim.id for claim in claims}
    citations = []
    statements = [DECISION_HANDOFF] if decision else []
    for (source_id, quote), source in selected.items():
        citations.append({"source_id": source_id, "claim_id": claim_ids.get((source_id, quote)), "quote": quote})
        label = source.ref or source.title or "Source"
        author = f" ({source.author_role})" if source.author_role else ""
        statements.append(f'{label}{author}: “{quote}”')
    return _result("\n".join(statements), citations=citations, refused=decision, mode="live", model=model)
