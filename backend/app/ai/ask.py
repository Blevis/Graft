"""Read-only, extractive Q&A over evidence visible to the requesting user."""
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..services.cases import load_case
from ..services.evidence import current_claims, latest_sources
from ..schemas.requests import Detail, Focus, Format, Include
from ..services.org_settings import get_org_settings
from ..services.presentation import resolve as resolve_presentation
from ..services.tenancy import Ctx
from ..services.permissions import Policy
from ..services.visibility import visible_cases
from . import client
from .verifier import quote_error

PROMPT_VERSION = "ask_v2"
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
    """focus/detail/format/include steer presentation only. Which records the model sees is decided before."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    case_id: str | None = Field(default=None, min_length=1, max_length=100)
    focus: Focus | None = None
    detail: Detail | None = None
    format: Format | None = None
    include: list[Include] | None = None


def _result(answer, *, citations=(), refused=True, mode="unavailable", model=None, presentation=None):
    return {"answer": answer, "citations": list(citations), "refused": refused, "mode": mode,
            "model": model, "prompt_version": PROMPT_VERSION, "presentation": presentation}


def _sources(db, ctx, case, question, boost=()):
    """Authorization happens here, before the model sees anything: only cases the user may see, and only
    cases where their view level includes original evidence. Presentation settings never widen this set."""
    policy = Policy(db, ctx)
    if case:
        cases = {case.id: case} if policy.sees_evidence(case) else {}
        sources = latest_sources(db, ctx.org_id, case_id=case.id) if cases else []
    else:
        cases = {c.id: c for c in db.scalars(visible_cases(ctx)) if policy.sees_evidence(c)}
        if policy.is_coordinator():
            sources = latest_sources(db, ctx.org_id)
        else:
            sources = [s for c in cases.values() for s in latest_sources(db, ctx.org_id, case_id=c.id)]

    words = set(re.findall(r"\w+", question.casefold()))

    def relevance(source):
        emp = cases.get(source.case_id)
        label = f"{emp.employee} {emp.ref}" if emp else ""
        metadata = f"{label} {source.ref or ''} {source.title or ''}"
        body_words = set(re.findall(r"\w+", source.body.casefold()))
        return 3 * len(words.intersection(re.findall(r"\w+", metadata.casefold()))) + len(
            words.intersection(body_words)) + len(body_words.intersection(boost))

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


def _present(statements: list[tuple[str, object, str]], fmt: str, decision: bool) -> str:
    """Arrange verified, quoted statements. Every statement keeps its quote and source label: formatting can
    reorder or group them but never drop a citation. statements: (text, date, group)."""
    lead = [DECISION_HANDOFF] if decision else []
    if fmt == "chronological":
        ordered = sorted(statements, key=lambda s: (s[1] is None, s[1] or ""))
        return "\n".join(lead + [f"{s[1] or 'undated'} · {s[0]}" for s in ordered])
    if fmt == "action_list":
        return "\n".join(lead + [f"• {s[0]}" for s in statements])
    if fmt == "stakeholder_report":
        groups: dict[str, list[str]] = {}
        for text, _, group in statements:
            groups.setdefault(group, []).append(text)
        lines = list(lead)
        for group, items in groups.items():
            lines.append(f"{group}:")
            lines += [f"  – {t}" for t in items]
        return "\n".join(lines)
    return "\n".join(lead + [s[0] for s in statements])


def answer_question(db: Session, ctx: Ctx, question: str, case_id: str | None = None,
                    presentation: dict | None = None) -> dict:
    # Resolve scope before handling availability so hidden records still behave like missing ones.
    case = load_case(db, ctx, case_id) if case_id is not None else None
    pres = resolve_presentation(db, ctx, presentation)
    public = {k: pres[k] for k in ("profile", "profile_label", "focus", "detail", "format", "guidance_version")}
    decision = bool(DECISION_REQUEST.search(question))
    handoff = f" {DECISION_HANDOFF}" if decision else ""

    def respond(answer, **kw):  # every response carries the presentation that shaped it
        return _result(answer, presentation=public, **kw)

    if not get_org_settings(db, ctx.org_id)["ai_enabled"]:
        return respond(f"Ask Graft is disabled for this organisation.{handoff}")
    if not client.is_configured():
        return respond(f"Ask Graft is unavailable because the AI provider is not configured.{handoff}")

    sources, payload = _sources(db, ctx, case, question, boost=set(pres["keywords"]))
    if not sources:
        return respond(DECISION_HANDOFF if decision else NO_EVIDENCE)
    model = get_settings().LLM_MODEL
    try:
        raw = client.answer_question({
            "question": question, "sources": payload,
            # Presentation hints only (role profile, personal preferences, versioned PMO guidance). They can
            # change emphasis and how many passages to select; they cannot add sources or change the rules above.
            "presentation": {"reader_role": pres["profile_label"], "emphasis": pres["emphasis"],
                             "focus": pres["focus"], "max_passages": pres["max_citations"],
                             "organisation_guidance": pres["guidance"]},
        }, SelectionResult.model_json_schema())
        result = SelectionResult.model_validate(raw)
    except client.AIUnavailable as exc:
        return respond(f"Ask Graft is unavailable ({exc}).{handoff}")
    except ValidationError:
        return respond(DECISION_HANDOFF if decision else NO_EVIDENCE, mode="live", model=model)

    decision = decision or result.decision_question
    refusal = respond(DECISION_HANDOFF if decision else NO_EVIDENCE, mode="live", model=model)
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
    statements = []
    case_by_id = {c.id: c for c in db.scalars(visible_cases(ctx))}
    for (source_id, quote), source in selected.items():
        citations.append({"source_id": source_id, "claim_id": claim_ids.get((source_id, quote)), "quote": quote})
        label = source.ref or source.title or "Source"
        author = f" ({source.author_role})" if source.author_role else ""
        owner = case_by_id.get(source.case_id)
        group = f"{owner.employee} ({owner.ref})" if owner else "Unlinked evidence"
        statements.append((f'{label}{author}: “{quote}”', source.date.isoformat() if source.date else None, group))
    answer = _present(statements, pres["format"], decision)
    return respond(answer, citations=citations, refused=decision, mode="live", model=model)
