"""Request bodies (the write side of the API contract). Role never appears in a body."""
from datetime import date
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, BeforeValidator, Field

from ..services.roles import LEGACY_ROLE_MAP

CanonicalRole = Literal[
    "org_admin", "pmo_coordinator", "project_manager", "line_manager", "technical_owner", "training_responsible",
    "hr_business_partner", "access_responsible", "project_member", "employee", "management_viewer", "auditor",
]
# Legacy codes (admin, viewer) are accepted on input and stored canonically.
Role = Annotated[CanonicalRole, BeforeValidator(lambda v: LEGACY_ROLE_MAP.get(v, v) if isinstance(v, str) else v)]
ResponsibilityType = Literal["line_manager", "project_manager", "technical_owner", "training_responsible",
                             "hr_business_partner", "access_responsible"]
Stage = Literal["pre_onboarding", "access", "shadowing", "supported_execution", "independent_execution", "validated"]
AccessState = Literal["requested", "awaiting_approval", "approved", "not_provisioned", "active", "confirmed_usable"]


class DemoLogin(BaseModel):
    user_id: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    owner_user_id: str | None = None
    owner_role: Role | None = None
    due_date: date | None = None
    sla_hours: int | None = Field(default=None, ge=1, le=24 * 60)
    finding_id: str | None = None
    cited_source_ids: list[str] = []
    origin: Literal["manual", "ai_suggested_edited"] = "manual"
    # No owner given: route deterministically (from the finding's rule) or, failing that, to the coordinator queue.
    route: bool = False
    requirement_id: str | None = None


class TaskUpdate(BaseModel):
    status: Literal["open", "done"]


class ReviewCreate(BaseModel):
    disposition: Literal["keep_open", "validate_scope", "close", "reopen"]
    scope: str = Field(min_length=3, max_length=300)
    rationale: str = Field(min_length=10, max_length=4000)
    observed_stage: Stage | None = None
    cited_source_ids: list[str] = Field(default=[], max_length=50)
    task_id: str | None = None
    milestone_key: str | None = Field(default=None, max_length=60)
    exception_reason: str | None = Field(default=None, max_length=2000)


class InboxPost(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=3, max_length=20000)
    author_role: str = Field(min_length=2, max_length=100)
    recipient_role: str | None = Field(default=None, max_length=100)
    date: date
    kind: Literal["email", "update", "tracker_note"] = "email"


class InboxLink(BaseModel):
    case_id: str


class AccessCreate(BaseModel):
    system: str = Field(min_length=2, max_length=200)
    state: AccessState = "requested"
    requested_at: date | None = None
    owner_role: str | None = None
    next_follow_up: date | None = None
    evidence_source_ids: list[str] = []


class AccessUpdate(BaseModel):
    """Send only what changes. tester_user_id is honoured only under the "designated" tester policy."""
    state: AccessState | None = None
    next_follow_up: date | None = None
    tester_user_id: str | None = None


class CasePatch(BaseModel):
    """Coordinator-maintained case fields. Send null to clear a value; omit a key to leave it unchanged.
    Tracker fields (status, last update) stay as reported and are not editable here."""
    expected_readiness_date: date | None = None
    exact_role: str | None = Field(default=None, max_length=200)
    employee: str | None = Field(default=None, min_length=2, max_length=200)
    movement: Literal["new_hire", "reallocation"] | None = None
    start_date: date | None = None
    project_id: str | None = None
    external_id: str | None = Field(default=None, max_length=100)
    employee_user_id: str | None = None


class CaseCreate(BaseModel):
    employee: str = Field(min_length=2, max_length=200)
    movement: Literal["new_hire", "reallocation"] = "new_hire"
    start_date: date | None = None
    ref: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9]{1,9}-\d{1,6}$")
    external_id: str | None = Field(default=None, max_length=100)
    project_id: str | None = None
    employee_user_id: str | None = None
    line_manager_user_id: str | None = None
    technical_owner_user_id: str | None = None
    template_key: str | None = Field(default=None, max_length=60)
    exact_role: str | None = Field(default=None, max_length=200)
    expected_readiness_date: date | None = None


class CsvImport(BaseModel):
    csv: str = Field(min_length=1, max_length=262_144)


class TemplateVersionCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    movement: Literal["new_hire", "reallocation"] | None = None
    definition: dict
    note: str | None = Field(default=None, max_length=1000)


class TemplateCreate(TemplateVersionCreate):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")


class RequirementPatch(BaseModel):
    applicability: Literal["required", "optional", "not_applicable"] | None = None
    due_date: date | None = None
    title: str | None = Field(default=None, min_length=3, max_length=300)
    reason: str = Field(min_length=5, max_length=1000)


class RequirementCreate(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")
    title: str = Field(min_length=3, max_length=300)
    kind: Literal["milestone", "access"] = "milestone"
    applicability: Literal["required", "optional", "not_applicable"] = "required"
    evidence_expectation: str | None = Field(default=None, max_length=1000)
    due_date: date | None = None
    assignee_role: ResponsibilityType | None = None
    reason: str = Field(min_length=5, max_length=1000)


class ApplyTemplate(BaseModel):
    template_key: str = Field(max_length=60)
    create_tasks: bool = True


class TaskReassign(BaseModel):
    owner_user_id: str | None = None
    owner_role: Role | None = None
    reason: str = Field(min_length=3, max_length=500)


class TaskPauseBody(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class SourceSubmit(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    body: str = Field(min_length=3, max_length=20000)
    source_date: Optional[date] = Field(default=None, alias="date")
    kind: Literal["email", "update", "tracker_note"] = "update"


class WorkingHours(BaseModel):
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    days: list[int] = Field(min_length=1, max_length=7)


class SettingsPatch(BaseModel):
    stale_days: int | None = Field(default=None, ge=1, le=90)
    unanswered_working_days: int | None = Field(default=None, ge=1, le=30)
    as_of_date: date | None = None
    ai_enabled: bool | None = None
    default_sla_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    flag_missing_readiness_date: bool | None = None
    required_responsibilities: list[ResponsibilityType] | None = None
    project_manager_can_assign: bool | None = None
    access_tester_policy: Literal["employee", "designated"] | None = None
    allow_closure_exceptions: bool | None = None
    clock_mode: Literal["as_of", "real"] | None = None
    timezone: str | None = Field(default=None, max_length=60)
    working_hours: WorkingHours | None = None
    holidays: list[date] | None = Field(default=None, max_length=100)
    escalation_working_days: int | None = Field(default=None, ge=1, le=30)


class MemberCreate(BaseModel):
    """Add a demo member. Real invitations (email + SSO) are on the roadmap; no password is ever stored."""
    name: str = Field(min_length=2, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)


class MemberPatch(BaseModel):
    status: Literal["active", "suspended"]


class RoleAssignmentCreate(BaseModel):
    user_id: str
    role_code: Role
    scope_type: Literal["organization", "project", "case"] = "organization"
    scope_id: str | None = None
    default_for_cases: bool = False
    valid_from: date | None = None
    valid_until: date | None = None


class RoleAssignmentPatch(BaseModel):
    default_for_cases: bool | None = None
    valid_from: date | None = None
    valid_until: date | None = None


class ProjectAssignmentCreate(BaseModel):
    user_id: str
    role_code: Role
    default_for_cases: bool = False


class RoleLabelsPatch(BaseModel):
    labels: dict[str, str] = Field(max_length=20)


class ResponsibilityCreate(BaseModel):
    user_id: str
    responsibility_type: ResponsibilityType
    access_item_id: str | None = None
    is_primary: bool = True
    notes: str | None = Field(default=None, max_length=500)
    valid_from: date | None = None
    valid_until: date | None = None


class ResponsibilityPatch(BaseModel):
    is_primary: bool | None = None
    notes: str | None = Field(default=None, max_length=500)
    valid_until: date | None = None


class TrainingCreate(BaseModel):
    kind: Literal["plan", "session", "observation"]
    title: str = Field(min_length=3, max_length=300)
    notes: str = Field(default="", max_length=4000)
    activity_date: date | None = None
    cited_source_ids: list[str] = []


Focus = Literal["auto", "my_tasks", "one_employee", "one_project", "cross_project", "access", "training",
                "technical_readiness"]
Detail = Literal["brief", "standard", "detailed"]
Format = Literal["action_list", "status_brief", "chronological", "stakeholder_report"]
Include = Literal["risks", "ownership", "citations", "deadlines", "open_questions"]


class PreferencesPatch(BaseModel):
    """Presentation only. None of these values is ever read by an authorization check."""
    working_role: str | None = None
    focus: Focus | None = None
    detail: Detail | None = None
    format: Format | None = None
    include: list[Include] | None = None


class AIGuidancePatch(BaseModel):
    terminology: str = Field(default="", max_length=2000)
    report_structure: str = Field(default="", max_length=2000)
    escalation_summary: str = Field(default="", max_length=2000)
    formatting: str = Field(default="", max_length=1000)
    context: str = Field(default="", max_length=4000)
