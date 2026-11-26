"""Read-only tools scoped to one case snapshot and server validation of draft proposals."""
import hashlib
import json
import re
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..schemas.requests import Role


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)
    kind: Literal["task", "message", "access_followup"]
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=1, max_length=3000)
    owner_role: Role | None = None
    owner_user_id: str | None = Field(default=None, max_length=64)
    due_date: str | None = Field(default=None, max_length=10)
    cited_source_ids: list[str] = Field(default_factory=list, max_length=32)
    cited_claim_ids: list[str] = Field(default_factory=list, max_length=32)


READ_TOOLS = {
    "get_case": ("Read case identity, owner, tracker, latest human review and original source IDs.", "case"),
    "list_findings": ("Read flags, their explanations and supporting evidence IDs.", "findings"),
    "list_claims": ("Read verified claim IDs, source IDs, scopes and exact quotes.", "claims"),
    "list_tasks": ("Read existing human tasks to avoid proposing duplicates.", "tasks"),
    "list_access_items": ("Read per-system approval, provisioning and employee-test evidence.", "access_items"),
    "list_knowledge": ("Read project knowledge references visible on this case.", "knowledge"),
    "get_settings": ("Read the organisation's as-of date, due-date defaults and thresholds.", "settings"),
}
EVIDENCE_READS = {"read_source", "list_findings", "list_claims", "list_access_items"}


def _tool(name, description, properties=None, required=()):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties or {}, "required": list(required),
        "additionalProperties": False,
    }}}


TOOLS = [_tool(name, description) for name, (description, _) in READ_TOOLS.items()] + [
    _tool("read_source", "Read one immutable original from this case, using its internal source ID.",
          {"source_id": {"type": "string"}}, ["source_id"]),
    _tool("submit_proposals", "Finish with a short assessment and cited human-editable follow-ups.", {
        "assessment": {"type": "string", "minLength": 1, "maxLength": 3000},
        "proposals": {"type": "array", "minItems": 1, "maxItems": 3, "items": Proposal.model_json_schema()},
    }, ["assessment", "proposals"]),
]


def evidence_hash(detail: dict) -> str:
    # Include claim IDs so refreshing the extraction cannot leave dangling citations.
    sources = sorted((source["id"], source["body_sha256"]) for source in detail["sources"])
    claims = sorted((claim["id"], claim["source_id"]) for claim in detail["claims"])
    access = sorted((item["id"], item["state"]) for item in detail["access_items"])
    evidence = json.dumps([sources, claims, access], separators=(",", ":"))
    return hashlib.sha256(evidence.encode()).hexdigest()


def read_tool(name, args, detail, settings):
    if name == "read_source":
        if set(args) != {"source_id"} or not isinstance(args["source_id"], str):
            raise ValueError("read_source needs a source_id")
        for source in detail["sources"]:
            if source["id"] == args["source_id"]:
                return {key: source[key] for key in ("id", "ref", "title", "date", "author_role", "body")}
        raise ValueError("Source is unavailable on this case")
    if name not in READ_TOOLS or args:
        raise ValueError("Unknown tool or unexpected arguments")
    if name == "get_case":
        sources = [{key: s[key] for key in ("id", "ref", "title", "author_role", "date")} for s in detail["sources"]]
        return {**detail["case"], "latest_review": detail["latest_review"], "sources": sources}
    if name == "get_settings":
        return {key: settings[key] for key in ("as_of_date", "default_sla_hours", "stale_days", "unanswered_working_days")}
    return detail[READ_TOOLS[name][1]]


def _validate_proposal(raw, detail, settings, owners):
    draft = Proposal.model_validate(raw)
    sources = {s["id"] for s in detail["sources"]}
    claims = {c["id"]: c["source_id"] for c in detail["claims"]}
    if not draft.cited_claim_ids and not draft.cited_source_ids:
        raise ValueError("uncited proposal")
    if set(draft.cited_claim_ids) - claims.keys() or set(draft.cited_source_ids) - sources:
        raise ValueError("citation outside current case evidence")
    mentioned_cases = re.findall(r"\bONB-\d+\b", f"{draft.title} {draft.body}".upper())
    if set(mentioned_cases) - {detail["case"]["ref"].upper()}:
        raise ValueError("references a different case")
    if not draft.owner_role and not draft.owner_user_id:
        raise ValueError("no proposed owner")
    if draft.owner_user_id:
        if draft.owner_user_id not in owners:
            raise ValueError("unknown owner on this case")
        role = owners[draft.owner_user_id]
        if draft.owner_role and role != draft.owner_role:
            raise ValueError("owner and role disagree")
        draft.owner_role = role
    if draft.due_date:
        parsed = date.fromisoformat(draft.due_date)
        if parsed.isoformat() != draft.due_date:
            raise ValueError("due date must use YYYY-MM-DD")
    else:
        days = max(1, round(settings["default_sla_hours"] / 24))
        draft.due_date = (date.fromisoformat(settings["as_of_date"]) + timedelta(days=days)).isoformat()
    draft.cited_source_ids = list(dict.fromkeys([*draft.cited_source_ids, *(claims[c] for c in draft.cited_claim_ids)]))
    draft.cited_claim_ids = list(dict.fromkeys(draft.cited_claim_ids))
    return draft.model_dump()


def validate_submission(args, detail, settings, owners):
    if set(args) != {"assessment", "proposals"}:
        raise ValueError("Expected assessment and proposals")
    assessment = args["assessment"]
    if not isinstance(assessment, str) or not 1 <= len(assessment.strip()) <= 3000:
        raise ValueError("A short assessment is required")
    if not isinstance(args["proposals"], list) or not 1 <= len(args["proposals"]) <= 3:
        raise ValueError("Return one to three proposals")
    accepted, rejected = [], []
    for index, raw in enumerate(args["proposals"], start=1):
        try:
            accepted.append(_validate_proposal(raw, detail, settings, owners))
        except ValidationError as exc:
            problem = exc.errors(include_input=False, include_url=False)[0]
            rejected.append(f"proposal {index}: {problem['loc']} {problem['type']}")
        except ValueError as exc:
            rejected.append(f"proposal {index}: {exc}")
    return assessment.strip(), accepted, rejected
