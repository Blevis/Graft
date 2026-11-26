"""Investigate one visible onboarding case. Tool execution can never write a task or review."""
import json
from time import monotonic

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import EmployeeCase
from ..services.cases import case_detail, load_case
from ..services.org_settings import get_org_settings
from ..services.tenancy import Ctx
from . import client
from .agent_tools import EVIDENCE_READS, TOOLS, case_brief, evidence_hash, read_tool, validate_submission

PROMPT_VERSION = "agent_v2"
MAX_CALLS = 8
MAX_SECONDS = 60


def _case_owners(ctx, case, detail):
    owners = {ctx.user_id: ctx.role}
    for row in detail.get("stakeholders", []):
        for a in row["assignments"]:
            if a["user"] and a["access_item_id"] is None:
                owners.setdefault(a["user"]["id"], row["responsibility_type"])
    if case.employee_user_id:
        owners[case.employee_user_id] = "employee"
    if tech_owner := detail["case"]["tech_owner"]:
        owners[tech_owner["id"]] = tech_owner["role"]
    for task in detail["tasks"]:
        if owner := task["owner_user"]:
            owners[owner["id"]] = owner["role"]
    return owners


def run_agent(db: Session, ctx: Ctx, case: EmployeeCase) -> dict:
    """Return an investigated snapshot, its trace, and drafts for the API to store together."""
    deadline = monotonic() + MAX_SECONDS
    case = load_case(db, ctx, case.id)
    if not ctx.org_roles & {"pmo_coordinator", "org_admin"}:
        raise HTTPException(403, "Only a coordinator or admin may run the case agent")
    detail = case_detail(db, ctx, case)
    settings = get_org_settings(db, ctx.org_id)
    steps = []
    result = {
        "model": get_settings().LLM_MODEL, "prompt_version": PROMPT_VERSION,
        "evidence_hash": evidence_hash(detail), "steps": steps, "proposals": [],
    }

    def finish(status, assessment, proposals=None):
        return {**result, "status": status, "assessment": assessment, "proposals": proposals or []}

    if not settings["ai_enabled"]:
        return finish("unavailable", "Agent unavailable: AI is disabled for this organisation.")
    if not client.is_configured():
        return finish("unavailable", "Agent unavailable: GROQ_API_KEY is not configured.")

    owners = _case_owners(ctx, case, detail)
    messages = [
        {"role": "system", "content": client._read(f"prompts/{PROMPT_VERSION}.txt")},
        {"role": "user", "content": json.dumps({
            "request": "Investigate this case and propose follow-ups.",
            "brief": case_brief(detail, settings)}, ensure_ascii=False, separators=(",", ":"))},
    ]
    # The brief already carries every original, so the model may submit without a separate read.
    read_evidence = bool(detail["sources"])
    while len(steps) < MAX_CALLS:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return finish("failed", "Investigation exceeded the time limit.")
        try:
            message = client.agent_turn(messages, TOOLS, remaining)
        except client.AIUnavailable as exc:
            return finish("unavailable", f"Agent unavailable: {exc}.")
        if monotonic() >= deadline:
            return finish("failed", "Investigation exceeded the time limit.")
        calls = message.get("tool_calls") or []
        if not calls:
            return finish("failed", "The model did not request a tool or submit proposals.")
        messages.append(message)
        for call in calls:
            if len(steps) >= MAX_CALLS:
                return finish("failed", "Investigation reached the tool-call limit.")
            if monotonic() >= deadline:
                return finish("failed", "Investigation exceeded the time limit.")
            start = monotonic()
            function = call["function"]
            name = function["name"]
            args, candidates, assessment = {}, [], None
            try:
                parsed = json.loads(function["arguments"])
                if not isinstance(parsed, dict):
                    raise ValueError("Tool arguments must be an object")
                args = parsed
                if name == "submit_proposals":
                    if not read_evidence:
                        raise ValueError("Read the case evidence before submitting")
                    assessment, candidates, rejected = validate_submission(args, detail, settings, owners)
                    summary = f"{len(candidates)} proposal(s) accepted by validation"
                    if rejected:
                        summary += "; rejected " + "; ".join(rejected)
                    output = {"validation": summary}
                else:
                    output = read_tool(name, args, detail, settings)
                    if name in EVIDENCE_READS and output:
                        read_evidence = True
                    if isinstance(output, list):
                        summary = f"Returned {len(output)} record(s)"
                    elif name == "read_source":
                        summary = f"Read source {output['ref'] or output['id']}"
                    else:
                        summary = "Returned case details" if name == "get_case" else "Returned organisation settings"
            except (TypeError, ValueError) as exc:
                summary = f"Rejected: {exc}"
                output = {"error": summary}
            steps.append({"index": len(steps) + 1, "tool": name, "arguments": args, "result_summary": summary,
                          "duration_ms": round((monotonic() - start) * 1000)})
            if monotonic() >= deadline:
                return finish("failed", "Investigation exceeded the time limit.")
            if candidates:
                return finish("completed", assessment, candidates)
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                             "content": json.dumps(output, ensure_ascii=False, separators=(",", ":"))})
    return finish("failed", "Investigation reached the tool-call limit without a valid proposal.")
