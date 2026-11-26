"""Layer B (presentation): role response profiles, personal preferences and PMO guidance.

Nothing in this module is consulted by an authorization check. Layer A (services/permissions.py,
services/visibility.py) decides which records reach the assistant *before* any of this applies; a profile, a
preference or a guidance text can change wording, ordering and level of detail only."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AIGuidanceVersion, UserPreference
from .tenancy import Ctx

PROFILES: dict[str, dict] = {
    "pmo_coordinator": {"label": "PMO", "focus": "cross_project", "format": "action_list",
                        "emphasis": "Organization-wide exceptions, missing information, ownership gaps, overdue "
                                    "actions, stale status and cross-project patterns.",
                        "keywords": ["owner", "overdue", "stale", "missing", "blocked", "pending", "closed"]},
    "org_admin": {"label": "PMO", "focus": "cross_project", "format": "action_list",
                  "emphasis": "Organization-wide exceptions, ownership gaps and configuration issues.",
                  "keywords": ["owner", "missing", "pending"]},
    "project_manager": {"label": "Project Manager", "focus": "one_project", "format": "status_brief",
                        "emphasis": "Project delivery impact, onboarding blockers, unresolved dependencies, "
                                    "client-relevant status and next coordination steps.",
                        "keywords": ["blocked", "pending", "client", "delivery", "access", "scenarios"]},
    "line_manager": {"label": "Line Manager", "focus": "one_employee", "format": "status_brief",
                     "emphasis": "Employee development, skills, progress, training needs and actions needing "
                                 "managerial attention.",
                     "keywords": ["training", "support", "skills", "progress", "independent"]},
    "technical_owner": {"label": "Technical Owner", "focus": "technical_readiness", "format": "chronological",
                        "emphasis": "Technical evidence, activity-level readiness, conflicting claims, uncovered "
                                    "scenarios and validation needed.",
                        "keywords": ["scenarios", "complex", "independent", "support", "validated", "covered"]},
    "training_responsible": {"label": "Training Responsible", "focus": "training", "format": "action_list",
                             "emphasis": "Training coverage, KT plan, observations, missing learning evidence and "
                                         "recommended follow-up.",
                             "keywords": ["training", "kt", "shadowing", "session", "guide", "runbook"]},
    "hr_business_partner": {"label": "HR Business Partner", "focus": "one_employee", "format": "status_brief",
                            "emphasis": "HR onboarding milestones and employee-support gaps within authorized "
                                        "fields.",
                            "keywords": ["start", "onboarding", "support"]},
    "access_responsible": {"label": "Access Responsible", "focus": "access", "format": "action_list",
                           "emphasis": "Requested / approved / active / usable access, pending approvers, the "
                                       "validation owner and access follow-ups.",
                           "keywords": ["access", "vpn", "portal", "approval", "approved", "active", "provisioned"]},
    "employee": {"label": "Employee", "focus": "my_tasks", "format": "action_list",
                 "emphasis": "Personal progress, upcoming actions and explanations of information shared with the "
                             "employee.",
                 "keywords": ["access", "training", "next"]},
    "management_viewer": {"label": "Management Viewer", "focus": "cross_project", "format": "status_brief",
                          "emphasis": "Concise aggregate summaries and trends, with no unauthorized personal detail.",
                          "keywords": []},
    "auditor": {"label": "Auditor", "focus": "cross_project", "format": "chronological",
                "emphasis": "Chronology, actors, changes and traceability; no unsupported interpretation.",
                "keywords": []},
    "project_member": {"label": "Project Member", "focus": "my_tasks", "format": "action_list",
                       "emphasis": "Project updates and tasks shared with the user.", "keywords": []},
}
FOCUS_KEYWORDS = {
    "access": ["access", "vpn", "portal", "approval", "approved", "active", "provisioned", "desk"],
    "training": ["training", "kt", "shadowing", "session", "guide", "runbook"],
    "technical_readiness": ["scenarios", "complex", "independent", "support", "ready", "readiness"],
}
DETAIL_CITATIONS = {"brief": 2, "standard": 4, "detailed": 6}
DEFAULT_PREFS = {"working_role": None, "focus": "auto", "detail": "standard", "format": None,
                 "include": ["citations", "risks", "ownership"]}

# Guidance that tries to change rules rather than presentation is refused at save time. Citations and permissions
# are enforced in code regardless; this just tells the author early.
FORBIDDEN_GUIDANCE = re.compile(
    r"\b(?:without|no|skip|omit|remove|drop|disable|hide)\b[^.\n]{0,30}\b(?:citation|citations|sources?|evidence)\b"
    r"|\b(?:ignore|bypass|override|disable)\b[^.\n]{0,40}\b(?:permission|permissions|access control|visibility|rules?)"
    r"|\b(?:grant|give)\b[^.\n]{0,40}\b(?:access|permission)"
    r"|\b(?:decide|declare|mark|confirm|approve|sign off)\b[^.\n]{0,40}\b(?:ready|readiness|closure|independent)",
    re.IGNORECASE,
)


def get_preferences(db: Session, ctx: Ctx) -> dict:
    row = db.execute(select(UserPreference).where(UserPreference.org_id == ctx.org_id,
                                                  UserPreference.user_id == ctx.user_id)).scalar_one_or_none()
    prefs = {**DEFAULT_PREFS, **((row.value or {}) if row else {})}
    if prefs.get("working_role") not in ctx.roles:
        prefs["working_role"] = None
    return prefs


def latest_guidance(db: Session, org_id: str) -> AIGuidanceVersion | None:
    return db.execute(select(AIGuidanceVersion).where(AIGuidanceVersion.org_id == org_id)
                      .order_by(AIGuidanceVersion.version.desc()).limit(1)).scalar_one_or_none()


def guidance_out(g: AIGuidanceVersion | None) -> dict | None:
    if g is None:
        return None
    return {"version": g.version, "terminology": g.terminology, "report_structure": g.report_structure,
            "escalation_summary": g.escalation_summary, "formatting": g.formatting, "context": g.context,
            "created_by_user_id": g.created_by_user_id, "created_at": g.created_at.isoformat()}


def resolve(db: Session, ctx: Ctx, overrides: dict | None = None) -> dict:
    """Effective presentation for this request: request overrides > personal preferences > role profile."""
    prefs = get_preferences(db, ctx)
    role = prefs["working_role"] or ctx.role
    profile = PROFILES.get(role, PROFILES["project_member"])
    o = {k: v for k, v in (overrides or {}).items() if v is not None}
    focus = o.get("focus") or prefs.get("focus") or "auto"
    if focus == "auto":
        focus = profile["focus"]
    detail = o.get("detail") or prefs.get("detail") or "standard"
    fmt = o.get("format") or prefs.get("format") or profile["format"]
    include = o.get("include") or prefs.get("include") or DEFAULT_PREFS["include"]
    g = latest_guidance(db, ctx.org_id)
    return {
        "profile": role, "profile_label": profile["label"], "emphasis": profile["emphasis"],
        "focus": focus, "detail": detail, "format": fmt, "include": list(include),
        "max_citations": DETAIL_CITATIONS.get(detail, 4),
        "keywords": sorted(set(profile["keywords"]) | set(FOCUS_KEYWORDS.get(focus, []))),
        "guidance_version": g.version if g else None,
        "guidance": {k: v for k, v in (guidance_out(g) or {}).items()
                     if k in ("terminology", "report_structure", "escalation_summary", "formatting", "context") and v},
    }
