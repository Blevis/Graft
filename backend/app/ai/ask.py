"""Ask Graft: short, cited answers about onboarding cases the requesting user may see.

Layers, in order (each can only narrow what the next sees or says):
1. Scope gate (deterministic, before any model call): attempts to change the assistant's instructions, questions
   about private matters (pay, health, family, beliefs...) and requests to rate people are refused with fixed text.
2. Authorization: sources and case-record facts are chosen from the user's visible cases only.
3. The model labels the question (answer / decision / off_topic / unanswerable) and writes 1-4 statements, each
   citing verbatim passages. Off-topic and unanswerable questions get fixed text; model wording is never shown.
4. Server verification: every quote must occur exactly once in its source or fact; a statement keeps its own
   wording only if that wording is grounded in what it cites and asserts no readiness decision, otherwise it is
   replaced by its quote. Statements without a verified citation are dropped."""
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..schemas.requests import Detail, Focus, Format, Include
from ..services.cases import case_detail, case_rows, load_case
from ..services.evidence import current_claims, latest_sources
from ..services.org_settings import get_org_settings
from ..services.permissions import Policy
from ..services.presentation import resolve as resolve_presentation
from ..services.tenancy import Ctx
from ..services.visibility import visible_cases
from . import client
from .agent_tools import _case_view, _projections
from .verifier import quote_error

PROMPT_VERSION = "ask_v3"
MAX_SOURCES = 24
MAX_PORTFOLIO_SOURCES = 8  # keeps portfolio questions well under the tunnel's 100 s request limit
MAX_CONTEXT_CHARS = 80_000
MAX_STATEMENTS = 4
MAX_PORTFOLIO_CASES = 40
RULE_TITLE = {  # same wording as the UI's flag labels
    "CLOSURE_CONFLICT": "closure conflict", "ACCESS_NOT_CONFIRMED": "access not confirmed",
    "UNANSWERED_REQUEST": "unanswered request", "STALE_TRACKER": "stale tracker",
    "MISSING_PROJECT": "missing project", "MISSING_MANAGER": "missing manager",
    "MISSING_TECH_OWNER": "missing technical owner", "MISSING_READINESS_DATE": "missing readiness date",
}

NO_EVIDENCE = "I couldn't find a verified source or case record that answers that question."
DECISION_HANDOFF = "The technical owner must review the evidence and record the readiness decision."
OUT_OF_SCOPE = ("Ask Graft only answers questions about the onboarding and knowledge-transfer cases you can see: "
                "evidence, training, access, tasks, flags, reviews and who acts next.")
PRIVATE = ("Ask Graft doesn't answer questions about pay, health, family, beliefs or other private matters. "
           "It only covers onboarding evidence and case records.")
INSTRUCTIONS = ("Ask Graft can't change its instructions, role or rules. "
                "Ask a question about an onboarding case instead.")
JUDGEMENT = ("Graft doesn't rate, rank or judge people. It shows the evidence; readiness decisions belong to the "
             "case's technical owner.")

DECISION_REQUEST = re.compile(
    r"\b(?:is|are|am|declare|deem|mark|confirm|certify|decide|assess|judge|say|state|tell)\b[^?!.]{0,70}"
    r"\b(?:ready|cleared for (?:production|independent work)|fit for (?:production|independent work))\b"
    r"|\b(?:can|could|should|may)\b[^?!.]{0,70}\b(?:close|sign off|work independently|work (?:alone|unsupervised))\b",
    re.IGNORECASE,
)
INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass)\b[^?!.]{0,40}\b(?:instruction|rule|prompt|guideline|polic|above|previous|prior)"
    r"|\bsystem prompt\b|\byour (?:instructions|prompt|rules)\b|\b(?:jailbreak|developer mode|dan mode)\b"
    r"|\byou are now\b|\b(?:pretend|roleplay|role-play)\b|\bact as (?:if|though|an? (?:ai|assistant|chatbot|bot|different|new))\b|\bfrom now on\b"
    r"|\b(?:reveal|print|repeat|show)\b[^?!.]{0,30}\b(?:prompt|instructions|hidden|the text above)\b"
    r"|\bi (?:hereby )?authori[sz]e you\b|\byou (?:now )?have (?:my )?permission\b",
    re.IGNORECASE,
)
PRIVATE_TOPIC = re.compile(
    r"\b(?:salary|salaries|wage|wages|pay ?rate|bonus|compensation|earn(?:s|ing)?|"
    r"pregnan\w*|maternity|(?:her|his|their|mental|physical) health|health (?:condition|issue|problem|record)s?|medical|illness|sick(?:ness)?|diagnos\w*|disabilit\w*|therapy|"
    r"religio\w*|political|politics|sexual\w*|gay|lesbian|ethnic\w*|racial|nationality|"
    r"married|marital|divorce\w*|boyfriend|girlfriend|dating|children|kids|family|home address|"
    r"phone number|password|credit card|social security|private life|personal life|age of)\b",
    re.IGNORECASE,
)
PEOPLE_JUDGEMENT = re.compile(
    r"\b(?:fire|fired|sack|dismiss|terminate|demote|promote|lay off)\b|\b(?:lazy|stupid|incompetent|smart|"
    r"clever|weak|worst|best) (?:employee|person|hire|worker)\b|\brank\b[^?!.]{0,30}\b(?:employees|people|hires)\b"
    r"|\bwho is (?:the )?(?:best|worst)\b|\bperformance review\b",
    re.IGNORECASE,
)
# Readiness vocabulary: a statement may use these words only if its own citations contain them, so it can report
# who said so but never upgrade "working independently" into "ready", or "closed" into "approved".
READINESS_WORDS = re.compile(
    r"\b(?:ready|readiness|independent\w*|approved|approve|cleared|closed|closure|completed?|done|finished|"
    r"signed off|sign-off|validated|usable|stale)\b", re.IGNORECASE)
INTERNAL_ID = re.compile(r"\s*\((?:source:?\s*)?(?:record:)?R\d+\)|\brecord:R\d+\b", re.IGNORECASE)
STOP = set("""a an the and or but of to in on at for by with from as is are was were be been being it its this that
these those there here has have had do does did not no yes can could should would may might will shall than then
so such also any all some each both either which who whom whose what when where why how her his their them they
she he we you your our i me my about into over under after before still yet only just very more most less few
case cases record records source sources says said reports reported according per""".split())


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str
    quote: str


class Statement(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(max_length=600)
    citations: list[Citation] = Field(max_length=3)


class AskResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    scope: str
    statements: list[Statement] = Field(max_length=6)


ASK_SCHEMA = {
    "type": "object",
    "properties": {
        "scope": {"type": "string", "enum": ["answer", "decision", "off_topic", "unanswerable"]},
        "statements": {"type": "array", "maxItems": MAX_STATEMENTS, "items": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "maxLength": 400},
                "citations": {"type": "array", "minItems": 1, "maxItems": 3, "items": {
                    "type": "object",
                    "properties": {"source_id": {"type": "string"}, "quote": {"type": "string"}},
                    "required": ["source_id", "quote"], "additionalProperties": False}},
            },
            "required": ["text", "citations"], "additionalProperties": False}},
    },
    "required": ["scope", "statements"],
    "additionalProperties": False,
}


class AskRequest(BaseModel):
    """focus/detail/format/include steer presentation only. Which records the model sees is decided before."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)
    case_id: str | None = Field(default=None, min_length=1, max_length=100)
    focus: Focus | None = None
    detail: Detail | None = None
    format: Format | None = None
    include: list[Include] | None = None


def gate(question: str) -> tuple[str, str] | None:
    """Deterministic refusals that never reach the model: (reason, fixed answer) or None."""
    if INJECTION.search(question):
        return "instructions", INSTRUCTIONS
    if PRIVATE_TOPIC.search(question):
        return "private", PRIVATE
    if PEOPLE_JUDGEMENT.search(question):
        return "judgement", JUDGEMENT
    return None


def _result(answer, *, citations=(), refused=True, reason=None, mode="unavailable", model=None, presentation=None):
    return {"answer": answer, "citations": list(citations), "refused": refused, "refusal_reason": reason,
            "mode": mode, "model": model, "prompt_version": PROMPT_VERSION, "presentation": presentation}


# ---------- what the model may see ----------

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

    selected, payload, characters = {}, [], 0
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
        if len(selected) == (MAX_SOURCES if case else MAX_PORTFOLIO_SOURCES):
            break
    return selected, payload, cases


def _name(value):
    return value.get("name") if isinstance(value, dict) else value


def _case_facts(detail) -> list[str]:
    """One sentence per fact from the case record exactly as this user's view level shapes it."""
    view, rows = _case_view(detail), _projections(detail)
    who = f"{view.get('ref')} {view.get('employee')}"
    facts = []
    head = [f"project {view['project']}" if view.get("project") else None,
            f"movement {view['movement']}" if view.get("movement") else None,
            f"start date {view['start_date']}" if view.get("start_date") else None]
    facts.append(f"{who}: " + ", ".join(h for h in head if h) + "." if any(head) else f"{who}.")
    if _name(view.get("tech_owner")):
        facts.append(f"{who}: technical owner is {_name(view['tech_owner'])}.")
    if _name(view.get("manager")):
        facts.append(f"{who}: line manager is {_name(view['manager'])}.")
    if view.get("tracker_status"):
        age = f", {view['tracker_age_days']} days old" if view.get("tracker_age_days") is not None else ""
        facts.append(f"{who}: tracker status is '{view['tracker_status']}' (updated {view.get('tracker_updated_at') or 'date unknown'}{age}).")
    facts.append(f"{who}: stage is {view['stage']}." if view.get("stage") else f"{who}: no technical review recorded yet, so no stage.")
    if view.get("expected_readiness_date"):
        facts.append(f"{who}: expected readiness date is {view['expected_readiness_date']}.")
    if view.get("exact_role"):
        facts.append(f"{who}: role is {view['exact_role']}.")
    review = view.get("latest_review")
    if review:
        facts.append(f"{who}: latest technical review is '{review.get('disposition')}'"
                     + (f" for scope {review['scope']}" if review.get("scope") else "")
                     + (f" on {str(review['created_at'])[:10]}" if review.get("created_at") else "") + ".")
    for f in rows["findings"]:
        facts.append(f"{who}: open flag ({f.get('severity')}): {f.get('message')}")
    for t in rows["tasks"]:
        owner = t.get("owner") or t.get("owner_role") or "unassigned"
        facts.append(f"{who}: task '{t.get('title')}' is {t.get('status')}, owner {owner}"
                     + (f", due {t['due_date']}" if t.get("due_date") else "") + ".")
    for a in rows["access_items"]:
        facts.append(f"{who}: {a.get('system')} access is {str(a.get('state')).replace('_', ' ')}"
                     + (f" (requested {a['requested_at']})" if a.get("requested_at") else "") + ".")
    for k in rows["knowledge"]:
        facts.append(f"{who}: '{k.get('title')}' is documented at {k.get('location')}.")
    return facts


def _portfolio_facts(db, ctx, allowed: set[str]) -> list[str]:
    """Precomputed list facts first ("Cases flagged X: ..."), so portfolio questions are answered by one fact rather
    than by the model filtering every case itself; then one line per visible case."""
    rows = [r for r in case_rows(db, ctx) if r["id"] in allowed][:MAX_PORTFOLIO_CASES]
    by_flag: dict[str, list[str]] = {}
    for row in rows:
        for r in row.get("reasons") or []:
            label = RULE_TITLE.get(r["rule_id"], r["rule_id"].replace("_", " ").lower())
            by_flag.setdefault(label, []).append(f"{row['ref']} {row['employee']}")
    facts = [f"Cases flagged '{label}': {', '.join(names)}." for label, names in sorted(by_flag.items())]
    flagged = {n for names in by_flag.values() for n in names}
    clear = [f"{row['ref']} {row['employee']}" for row in rows if f"{row['ref']} {row['employee']}" not in flagged]
    if clear:
        facts.append(f"Cases with no open flags: {', '.join(clear)}.")
    overdue = [f"{row['ref']} {row['employee']}" for row in rows if (row.get("next_task") or {}).get("overdue")]
    if overdue:
        facts.append(f"Cases with an overdue task: {', '.join(overdue)}.")
    for row in rows:
        project = (row.get("project") or {}).get("name") if isinstance(row.get("project"), dict) else row.get("project")
        reasons = "; ".join(r["message"] for r in row.get("reasons") or []) or "no open flags"
        nxt = row.get("next_task")
        nxt = nxt.get("title") if isinstance(nxt, dict) else nxt
        facts.append(f"{row['ref']} {row['employee']}" + (f" ({project})" if project else "")
                     + f": tracker '{row.get('tracker_status') or 'not set'}'; flags: {reasons}"
                     + (f"; next task: {nxt}" if nxt else "") + ".")
    return facts


# ---------- verification ----------

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


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9/]+", text.casefold()) if len(w) > 2 and w not in STOP]


def grounded(text: str, support: str, cited: str) -> bool:
    """A statement keeps its own wording only if (1) at least 80% of its content words come from what it cites,
    the question or case names (prefix match tolerates inflection: covered/coverage), (2) every number or date in
    it appears in what it cites, and (3) every readiness word in it appears in what it cites."""
    words = _content_words(text)
    if not words:
        return False
    stems = {w[:5] for w in _content_words(support)}
    if sum(1 for w in words if w[:5] in stems) / len(words) < 0.8:
        return False
    if any(n not in cited for n in re.findall(r"\d[\d-]*", text)):
        return False
    cited_low = cited.casefold()
    return all(m.group(0).casefold() in cited_low for m in READINESS_WORDS.finditer(text))


def _present(statements: list[tuple[str, object, str]], fmt: str, decision: bool) -> str:
    """Arrange verified statements. Formatting can reorder or group them but never drop one or its references.
    statements: (text, date, group)."""
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
    # Resolve scope before anything else so hidden records still behave like missing ones.
    case = load_case(db, ctx, case_id) if case_id is not None else None
    pres = resolve_presentation(db, ctx, presentation)
    public = {k: pres[k] for k in ("profile", "profile_label", "focus", "detail", "format", "guidance_version")}

    def respond(answer, **kw):  # every response carries the presentation that shaped it
        return _result(answer, presentation=public, **kw)

    refusal = gate(question)
    if refusal:
        return respond(refusal[1], reason=refusal[0], mode="live" if client.is_configured() else "unavailable")
    decision = bool(DECISION_REQUEST.search(question))
    handoff = f" {DECISION_HANDOFF}" if decision else ""

    if not get_org_settings(db, ctx.org_id)["ai_enabled"]:
        return respond(f"Ask Graft is disabled for this organisation.{handoff}", reason="unavailable")
    if not client.is_configured():
        return respond(f"Ask Graft is unavailable because the AI provider is not configured.{handoff}",
                       reason="unavailable")

    sources, payload, evidence_cases = _sources(db, ctx, case, question, boost=set(pres["keywords"]))
    # Case-record facts follow the same rule as sources: only cases whose original evidence this user may read.
    # Summary-level and task-only viewers therefore send nothing to the model.
    if case:
        facts = _case_facts(case_detail(db, ctx, case)) if case.id in evidence_cases else []
    else:
        facts = _portfolio_facts(db, ctx, set(evidence_cases))
    records = {f"record:R{i}": text for i, text in enumerate(facts, 1)}
    payload += [{"source_id": rid, "ref": "Case record", "case_ref": case.ref if case else None, "body": text}
                for rid, text in records.items()]
    if not sources and not records:
        return respond(DECISION_HANDOFF if decision else NO_EVIDENCE, reason="decision" if decision else "no_evidence")

    model = get_settings().LLM_MODEL
    try:
        raw = client.answer_question({
            "question": question, "sources": payload,
            "presentation": {"reader_role": pres["profile_label"], "emphasis": pres["emphasis"],
                             "focus": pres["focus"], "max_passages": pres["max_citations"],
                             "organisation_guidance": pres["guidance"]},
        }, ASK_SCHEMA, PROMPT_VERSION)
        result = AskResult.model_validate(raw)
    except client.AIUnavailable as exc:
        return respond(f"Ask Graft is unavailable ({exc}).{handoff}", reason="unavailable")
    except ValidationError:
        return respond(DECISION_HANDOFF if decision else NO_EVIDENCE, mode="live", model=model,
                       reason="decision" if decision else "no_evidence")

    if result.scope == "off_topic" and not decision:
        return respond(OUT_OF_SCOPE, mode="live", model=model, reason="off_topic")
    decision = decision or result.scope == "decision"

    # Verify statement by statement. A statement needs at least one verified citation, and its wording must be
    # grounded in what it cites (question words do not count, so the model cannot echo the question back as a
    # finding). Ungrounded statements are dropped; only if none is grounded does the first cited passage stand in.
    by_id_case = {c.id: c for c in db.scalars(visible_cases(ctx))}
    names = " ".join(f"{c.employee} {c.ref}" for c in by_id_case.values())
    candidates = []
    for st in result.statements[:MAX_STATEMENTS]:
        quotes = []
        for item in st.citations:
            if item.source_id in records:
                body = records[item.source_id]
                if quote_error(body, item.quote, "case record"):
                    continue
                quotes.append(("record", item.source_id, body, None))
                continue
            source = sources.get(item.source_id)
            if source is None or quote_error(source.body, item.quote, source.ref or source.id):
                continue
            passage = _in_context(source.body, item.quote)
            if quote_error(source.body, passage, source.ref or source.id):
                continue
            quotes.append(("source", source.id, passage, source))
        if not quotes:
            continue
        cited = " ".join(q[2] for q in quotes)
        attribution = " ".join(f"{q[3].author_role or ''} {q[3].title or ''}" for q in quotes if q[3] is not None)
        text = INTERNAL_ID.sub("", " ".join(st.text.split())).strip()
        candidates.append((text if text and grounded(text, f"{cited} {attribution} {names}", cited) else None, quotes))

    kept = [(t, q) for t, q in candidates if t]
    if not kept and candidates:
        kept = [(candidates[0][1][0][2], candidates[0][1][:1])]
    citations, statements, seen, seen_text = [], [], set(), set()
    for text, quotes in kept:
        if text.casefold() in seen_text:
            continue
        seen_text.add(text.casefold())
        refs, date, group = [], None, "Case record"
        for kind, sid, quote, source in quotes:
            if kind == "record":
                refs.append("case record")
                cite = {"source_id": None, "claim_id": None, "quote": quote, "kind": "record"}
            else:
                refs.append(source.ref or source.title or "source")
                date = date or (source.date.isoformat() if source.date else None)
                owner = by_id_case.get(source.case_id)
                group = f"{owner.employee} ({owner.ref})" if owner else "Unlinked evidence"
                cite = {"source_id": sid, "claim_id": None, "quote": quote, "kind": "source"}
            if (cite["source_id"], quote) not in seen:
                seen.add((cite["source_id"], quote))
                citations.append(cite)
        statements.append((f"{text} [{', '.join(dict.fromkeys(refs))}]", date, group))

    if not statements:
        if decision:
            return respond(DECISION_HANDOFF, mode="live", model=model, reason="decision")
        return respond(NO_EVIDENCE, mode="live", model=model, reason="no_evidence")

    # Link source citations to verified claims where the passage matches a stored claim exactly.
    cited_sources = [sources[c["source_id"]] for c in citations if c["source_id"] in sources]
    claims, _, _ = current_claims(db, {s.id: s for s in cited_sources}.values())
    claim_ids = {(claim.source_id, claim.quote): claim.id for claim in claims}
    for c in citations:
        c["claim_id"] = claim_ids.get((c["source_id"], c["quote"]))
    answer = _present(statements, pres["format"], decision)
    return respond(answer, citations=citations, refused=decision, reason="decision" if decision else None,
                   mode="live", model=model)
