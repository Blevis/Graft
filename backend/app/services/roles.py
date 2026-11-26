"""Canonical role registry. Role codes are stable machine identifiers; organisations may change display labels only.

Aliases never change permissions or create a new security role (spec §3.2). Legacy codes from the first schema
(`admin`, `viewer`) are accepted on input and mapped here, so older API clients and seeded rows keep working."""

ROLE_REGISTRY: dict[str, dict] = {
    "org_admin": {"label": "Organization Admin", "scope": "organization",
                  "purpose": "Configure the workspace, users, role assignments and settings."},
    "pmo_coordinator": {"label": "PMO Coordinator", "scope": "organization",
                        "purpose": "Coordinate onboarding/KT processes and monitor all cases in the organization."},
    "project_manager": {"label": "Project Manager / Additional Manager", "scope": "project",
                        "purpose": "Lead a project, coordinate its stakeholders and keep project-level visibility; "
                                   "commonly the primary client contact."},
    "line_manager": {"label": "Line Manager", "scope": "case",
                     "purpose": "Follow direct reports' development, skills, training progress and problems."},
    "technical_owner": {"label": "Technical Lead / Technical Owner", "scope": "project",
                        "purpose": "Give technical guidance and, when formally assigned, validate technical readiness."},
    "training_responsible": {"label": "Training Responsible", "scope": "project",
                             "purpose": "Organize, deliver and record training and KT activities."},
    "hr_business_partner": {"label": "HR Business Partner", "scope": "case",
                            "purpose": "Support employee-related onboarding and HR coordination."},
    "access_responsible": {"label": "Access Responsible", "scope": "case",
                           "purpose": "Coordinate access requests and record system-specific validation."},
    "project_member": {"label": "Project Member", "scope": "project",
                       "purpose": "Participate in a project with limited project-context visibility."},
    "employee": {"label": "Employee / New Hire", "scope": "own case",
                 "purpose": "View their own onboarding information and complete assigned actions."},
    "management_viewer": {"label": "Management Viewer", "scope": "organization",
                          "purpose": "Read-only management visibility and reporting."},
    "auditor": {"label": "Auditor", "scope": "organization",
                "purpose": "Read-only access to permitted records and audit history."},
}
ROLE_CODES: tuple[str, ...] = tuple(ROLE_REGISTRY)
LEGACY_ROLE_MAP = {"admin": "org_admin", "viewer": "management_viewer"}

# Per-case accountabilities (spec §4.1). Each one requires the matching role grant.
RESPONSIBILITY_TYPES: tuple[str, ...] = (
    "line_manager", "project_manager", "technical_owner", "training_responsible", "hr_business_partner",
    "access_responsible",
)
# Required by default (interview: on allocation the manager must assign a technical lead and a training person).
# Line manager is tracked by the tracker's MISSING_MANAGER rule; orgs can add it here (setting
# required_responsibilities). Proposed default, awaiting PMO confirmation.
DEFAULT_REQUIRED_RESPONSIBILITIES = ["technical_owner", "training_responsible"]

# Roles that may appear in a project roster (project-scoped grants).
PROJECT_ROLES = ("project_manager", "technical_owner", "training_responsible", "access_responsible",
                 "project_member", "hr_business_partner", "management_viewer", "auditor")
# Org-wide roles a project manager or PMO may never hand out through a project roster.
ORG_ONLY_ROLES = frozenset({"org_admin", "pmo_coordinator"})

# Display priority when one label must represent a person with several roles.
PRIORITY = ("org_admin", "pmo_coordinator", "project_manager", "technical_owner", "line_manager",
            "training_responsible", "hr_business_partner", "access_responsible", "auditor", "management_viewer",
            "project_member", "employee")


def canonical(code: str | None) -> str | None:
    if code is None:
        return None
    return LEGACY_ROLE_MAP.get(code, code)


def primary_role(codes) -> str | None:
    codes = set(codes)
    for code in PRIORITY:
        if code in codes:
            return code
    return None


def role_labels(custom: dict | None) -> dict[str, str]:
    """Default labels overlaid with the org's custom display titles (display only)."""
    labels = {code: meta["label"] for code, meta in ROLE_REGISTRY.items()}
    for code, label in (custom or {}).items():
        if code in labels and isinstance(label, str) and label.strip():
            labels[code] = label.strip()
    return labels
