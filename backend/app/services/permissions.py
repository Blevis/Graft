"""Central authorization policy. Routers ask this module; they never compare role names themselves.

Every decision combines (a) the caller's active role grants at organisation, project and case scope and (b) the
responsibilities they hold on the specific case (assigned or inherited). A role in one project grants nothing in
another. Org-scoped "eligibility" roles such as technical_owner or line_manager grant no case access by themselves:
the person must be assigned (responsibility or project roster).

View levels (field-level policy, applied by services/cases.py before any data leaves the server, including to
the LLM):
  full         case team: evidence, claims, findings with quotes, reviews with rationale, training notes
  employee     their own case: their evidence and progress; reviewer-only content (rationale, rejected AI
               candidates) hidden
  summary      read-only or adjacent roles (management viewer, auditor, HR business partner, project member):
               status, findings without quotes, tasks, access states, review disposition; no raw evidence and no
               technical assessment notes
  access_only  access responsible: minimum case identity plus the access items and tasks in their scope
  task_only    someone whose only link to the case is a task assigned to them: case identity, their own tasks
               and exactly the sources those tasks cite. Nothing else, including through AI, search or Insights"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AccessItem, EmployeeCase, Task
from .org_settings import as_of, get_org_settings
from .responsibilities import ResponsibilityIndex
from .tenancy import Ctx

FULL, EMPLOYEE, SUMMARY, ACCESS_ONLY, TASK_ONLY = "full", "employee", "summary", "access_only", "task_only"
LEVEL_RANK = {None: 0, TASK_ONLY: 1, ACCESS_ONLY: 1, SUMMARY: 2, EMPLOYEE: 3, FULL: 4}

COORDINATOR_ROLES = frozenset({"org_admin", "pmo_coordinator"})
SEE_ALL_SUMMARY = frozenset({"management_viewer", "auditor"})
SEE_ALL = COORDINATOR_ROLES | SEE_ALL_SUMMARY
FULL_SCOPED = frozenset({"project_manager", "technical_owner", "training_responsible", "line_manager"})
SUMMARY_SCOPED = frozenset({"management_viewer", "auditor", "hr_business_partner", "project_member"})
TASK_CREATOR_RESPONSIBILITIES = frozenset({"line_manager", "technical_owner", "training_responsible",
                                           "hr_business_partner", "access_responsible", "project_manager"})
TRAINING_WRITERS = frozenset({"training_responsible", "technical_owner", "project_manager"})

RESTRICTED_SECTIONS = {
    FULL: [],
    EMPLOYEE: ["review rationale", "rejected AI candidates"],
    SUMMARY: ["original evidence", "claims", "finding quotes", "review rationale", "training notes"],
    ACCESS_ONLY: ["evidence", "findings", "reviews", "training", "knowledge", "tasks of others",
                  "access items outside your systems"],
    TASK_ONLY: ["evidence not cited by your tasks", "findings", "reviews", "training", "access", "knowledge",
                "tasks of others"],
}


class Policy:
    """Per-request policy with cached lookups. Construct once per request: Policy(db, ctx)."""

    def __init__(self, db: Session, ctx: Ctx):
        self.db, self.ctx = db, ctx
        self.settings = get_org_settings(db, ctx.org_id)
        self.today = as_of(self.settings)
        self._idx: ResponsibilityIndex | None = None
        self._task_cases: set[str] | None = None

    # ---- basics ----
    @property
    def idx(self) -> ResponsibilityIndex:
        if self._idx is None:
            self._idx = ResponsibilityIndex(self.db, self.ctx.org_id, self.today)
        return self._idx

    @property
    def task_case_ids(self) -> set[str]:
        if self._task_cases is None:
            self._task_cases = set(self.db.execute(select(Task.case_id).where(
                Task.org_id == self.ctx.org_id, Task.owner_user_id == self.ctx.user_id)).scalars())
        return self._task_cases

    def is_coordinator(self) -> bool:
        return bool(self.ctx.org_roles & COORDINATOR_ROLES)

    def has_org_role(self, *roles: str) -> bool:
        return bool(self.ctx.org_roles & set(roles))

    def roles_for_case(self, case: EmployeeCase) -> set[str]:
        """Roles the caller holds *for this case*: project grants on its project, case grants, responsibilities."""
        ctx = self.ctx
        roles = {g.role for g in ctx.grants
                 if (g.scope_type == "project" and case.project_id and g.scope_id == case.project_id)
                 or (g.scope_type == "case" and g.scope_id == case.id)}
        return roles | self.idx.held_by(case, ctx.user_id)

    def responsibilities_held(self, case: EmployeeCase) -> set[str]:
        return self.idx.held_by(case, self.ctx.user_id)

    # ---- visibility ----
    def level(self, case: EmployeeCase) -> str | None:
        ctx = self.ctx
        if ctx.org_roles & COORDINATOR_ROLES:
            return FULL
        scoped = self.roles_for_case(case)
        if scoped & FULL_SCOPED:
            return FULL
        if case.employee_user_id == ctx.user_id:
            return EMPLOYEE
        if scoped & SUMMARY_SCOPED or ctx.org_roles & SEE_ALL_SUMMARY:
            return SUMMARY
        if "access_responsible" in scoped or case.id in self.tester_case_ids:
            return ACCESS_ONLY
        if case.id in self.task_case_ids:
            return TASK_ONLY
        return None

    def task_cited_source_ids(self, case: EmployeeCase) -> set[str]:
        """Sources cited by the caller's own tasks on this case: what a task-only assignee may read."""
        ids: set[str] = set()
        for cited in self.db.execute(select(Task.cited_source_ids).where(
                Task.org_id == self.ctx.org_id, Task.case_id == case.id,
                Task.owner_user_id == self.ctx.user_id)).scalars():
            ids |= set(cited or [])
        return ids

    @property
    def tester_case_ids(self) -> set[str]:
        if not hasattr(self, "_tester_cases"):
            self._tester_cases = set(self.db.execute(select(AccessItem.case_id).where(
                AccessItem.org_id == self.ctx.org_id, AccessItem.tester_user_id == self.ctx.user_id)).scalars())
        return self._tester_cases

    def sees_evidence(self, case: EmployeeCase) -> bool:
        return self.level(case) in (FULL, EMPLOYEE)

    def can_view_field(self, field: str, case: EmployeeCase) -> bool:
        level = self.level(case)
        allowed = {
            "evidence": (FULL, EMPLOYEE), "claims": (FULL, EMPLOYEE), "rejected": (FULL,),
            "finding_detail": (FULL, EMPLOYEE), "review_rationale": (FULL,), "training_notes": (FULL, EMPLOYEE),
            "findings": (FULL, EMPLOYEE, SUMMARY), "reviews": (FULL, EMPLOYEE, SUMMARY),
            "training": (FULL, EMPLOYEE, SUMMARY), "knowledge": (FULL, EMPLOYEE, SUMMARY),
            "timeline": (FULL, EMPLOYEE, SUMMARY), "tracker": (FULL, EMPLOYEE, SUMMARY),
        }.get(field, (FULL,))
        return level in allowed

    # ---- capabilities ----
    def can_create_task(self, case: EmployeeCase) -> bool:
        if self.is_coordinator():
            return True
        return bool(self.roles_for_case(case) & TASK_CREATOR_RESPONSIBILITIES - {"access_responsible"}) or \
            "access_responsible" in self.responsibilities_held(case)

    def can_assign(self, case: EmployeeCase) -> bool:
        if self.is_coordinator():
            return True
        return bool(self.settings.get("project_manager_can_assign")) and case.project_id is not None and \
            case.project_id in self.ctx.project_ids("project_manager")

    def can_manage_project_team(self, project_id: str) -> bool:
        if self.is_coordinator():
            return True
        return bool(self.settings.get("project_manager_can_assign")) and \
            project_id in self.ctx.project_ids("project_manager")

    def can_review(self, case: EmployeeCase) -> bool:
        """Only the case's primary technical owner signs off. Org admin is not implicitly a technical owner."""
        return self.idx.primary(case, "technical_owner") == self.ctx.user_id

    def can_record_training(self, case: EmployeeCase) -> bool:
        return self.is_coordinator() or bool(self.roles_for_case(case) & TRAINING_WRITERS)

    def training_capacity(self, case: EmployeeCase) -> str:
        held = self.roles_for_case(case)
        for cap in ("training_responsible", "technical_owner", "project_manager"):
            if cap in held:
                return cap
        return "pmo_coordinator" if "pmo_coordinator" in self.ctx.org_roles else "org_admin"

    def can_edit_access(self, case: EmployeeCase, item: AccessItem | None = None) -> bool:
        """Request/approve/activate states. confirmed_usable is separate (can_confirm_access)."""
        if self.is_coordinator():
            return True
        if case.project_id and case.project_id in self.ctx.project_ids("project_manager"):
            return True
        whole, items = self.idx.access_scope(case, self.ctx.user_id)
        return whole or (item is not None and item.id in items)

    def access_items_in_scope(self, case: EmployeeCase, items: list[AccessItem]) -> list[AccessItem]:
        level = self.level(case)
        if level == TASK_ONLY:
            return [a for a in items if a.tester_user_id == self.ctx.user_id]
        if level != ACCESS_ONLY:
            return items
        whole, ids = self.idx.access_scope(case, self.ctx.user_id)
        return items if whole else [a for a in items if a.id in ids or a.tester_user_id == self.ctx.user_id]

    def access_tester(self, case: EmployeeCase, item: AccessItem) -> str | None:
        if self.settings.get("access_tester_policy") == "designated" and item.tester_user_id:
            return item.tester_user_id
        return case.employee_user_id

    def can_confirm_access(self, case: EmployeeCase, item: AccessItem) -> bool:
        return self.access_tester(case, item) == self.ctx.user_id

    def can_analyze(self) -> bool:
        return self.is_coordinator()

    def can_manage_roles(self) -> bool:
        return self.has_org_role("org_admin")

    def can_edit_ai_guidance(self) -> bool:
        return self.is_coordinator()

    def audit_scope(self) -> str:
        """all: every event in the org. own: only events the caller performed."""
        return "all" if self.has_org_role("org_admin", "pmo_coordinator", "auditor") else "own"

    def can_upload_document(self, case: EmployeeCase) -> bool:
        """The employee (own case) and the case team add evidence. HR business partners read summaries only, but
        may contribute HR evidence (e.g. a check-in report) to cases in their scope."""
        return self.level(case) in (FULL, EMPLOYEE) or "hr_business_partner" in self.roles_for_case(case)

    def case_permissions(self, case: EmployeeCase) -> dict:
        return {
            "can_upload_document": self.can_upload_document(case),
            "can_create_task": self.can_create_task(case),
            "can_analyze": self.can_analyze(),
            "can_review": self.can_review(case),
            "can_edit_access": self.can_edit_access(case),
            "can_confirm_access": case.employee_user_id == self.ctx.user_id,
            "can_assign": self.can_assign(case),
            "can_record_training": self.can_record_training(case),
            "can_patch_case": self.is_coordinator(),
            "can_run_agent": self.is_coordinator(),
            # First-hand observations (role workspace): the employee on their own case, the case's line manager.
            "observation_kinds": (["employee_evidence"] if case.employee_user_id == self.ctx.user_id else []) +
            (["manager_check_in"] if "line_manager" in self.responsibilities_held(case) else []),
        }


# ---- spec-named helpers (GRAFT_ROLE_AND_ORGANIZATION_SPEC §10.3) ----

def has_permission(db: Session, ctx: Ctx, permission: str, resource: EmployeeCase | None = None) -> bool:
    p = Policy(db, ctx)
    checks = {
        "manage_roles": lambda: p.can_manage_roles(),
        "edit_ai_guidance": lambda: p.can_edit_ai_guidance(),
        "analyze": lambda: p.can_analyze(),
        "create_task": lambda: resource is not None and p.can_create_task(resource),
        "assign": lambda: resource is not None and p.can_assign(resource),
        "review": lambda: resource is not None and p.can_review(resource),
        "record_training": lambda: resource is not None and p.can_record_training(resource),
        "edit_access": lambda: resource is not None and p.can_edit_access(resource),
    }
    return checks[permission]() if permission in checks else False


def can_view_field(db: Session, ctx: Ctx, field_name: str, resource: EmployeeCase) -> bool:
    return Policy(db, ctx).can_view_field(field_name, resource)


def require(allowed: bool, message: str) -> None:
    if not allowed:
        raise HTTPException(403, message)


def require_case_responsibility(db: Session, ctx: Ctx, case: EmployeeCase, responsibility_type: str) -> None:
    require(responsibility_type in Policy(db, ctx).responsibilities_held(case),
            f"Requires the {responsibility_type.replace('_', ' ')} responsibility on this case")


def require_project_scope(ctx: Ctx, project_id: str) -> None:
    if ctx.org_roles & SEE_ALL:
        return
    if project_id not in ctx.project_ids():
        raise HTTPException(404, "Not found")
