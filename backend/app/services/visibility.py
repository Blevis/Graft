"""Which cases a member may see. Applied on top of tenancy (org scoping).

- org_admin, pmo_coordinator, management_viewer, auditor with organisation scope: every case in the org
  (viewer and auditor at summary level; see services/permissions.py for field-level policy).
- any project-scoped grant: the cases of that project (project manager, technical owner, training responsible,
  project member, access responsible, HR partner, scoped viewer/auditor).
- any case-scoped grant or active case responsibility (line manager, technical owner, HR partner, access
  responsible, ...): that case.
- the employee: their own case.
- a designated access tester: the case of the access item they test (access-only view).
- anyone: a case where they own a task (you can always open the case behind your own work).

Org-scoped eligibility roles (technical_owner, line_manager, ...) grant no case visibility on their own.
A case outside this set behaves exactly like a case in another org: 404, never 403, never data."""
from sqlalchemy import Select, false, or_, select

from ..models import AccessItem, CaseResponsibility, EmployeeCase, Task
from .tenancy import Ctx

SEE_ALL = frozenset({"org_admin", "pmo_coordinator", "management_viewer", "auditor"})


def sees_all(ctx: Ctx) -> bool:
    return bool(ctx.org_roles & SEE_ALL)


def visible_cases(ctx: Ctx) -> Select:
    """SELECT EmployeeCase limited to the org and to what this member may see."""
    q = select(EmployeeCase).where(EmployeeCase.org_id == ctx.org_id)
    if sees_all(ctx):
        return q
    uid = ctx.user_id
    task_cases = select(Task.case_id).where(Task.org_id == ctx.org_id, Task.owner_user_id == uid)
    responsible = select(CaseResponsibility.case_id).where(
        CaseResponsibility.org_id == ctx.org_id, CaseResponsibility.user_id == uid,
        CaseResponsibility.is_active.is_(True))
    testing = select(AccessItem.case_id).where(AccessItem.org_id == ctx.org_id, AccessItem.tester_user_id == uid)
    conditions = [
        EmployeeCase.employee_user_id == uid,
        EmployeeCase.id.in_(task_cases),
        EmployeeCase.id.in_(responsible),
        EmployeeCase.id.in_(testing),  # a designated access tester sees the minimum context of that case
    ]
    if projects := ctx.project_ids():
        conditions.append(EmployeeCase.project_id.in_(projects))
    if cases := ctx.case_grant_ids():
        conditions.append(EmployeeCase.id.in_(cases))
    return q.where(or_(*conditions) if conditions else false())


def visible_case_ids(ctx: Ctx) -> Select:
    return visible_cases(ctx).with_only_columns(EmployeeCase.id)
