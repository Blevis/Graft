"""Which cases a member may see, by role. Applied on top of tenancy (org scoping).

- admin, pmo_coordinator, viewer (management): every case in the org.
- technical_owner: cases they own (directly or as the project's technical owner).
- line_manager: cases they manage.
- employee: their own case.
- anyone: a case where they own a task (you can always open the case behind your own work).

A case outside this set behaves exactly like a case in another org: 404, never 403, never data."""
from sqlalchemy import Select, or_, select

from ..models import EmployeeCase, Project, Task
from .tenancy import Ctx

SEE_ALL = frozenset({"admin", "pmo_coordinator", "viewer"})


def sees_all(ctx: Ctx) -> bool:
    return ctx.role in SEE_ALL


def visible_cases(ctx: Ctx) -> Select:
    """SELECT EmployeeCase limited to the org and to what this member may see."""
    q = select(EmployeeCase).where(EmployeeCase.org_id == ctx.org_id)
    if sees_all(ctx):
        return q
    uid = ctx.user_id
    owned_projects = select(Project.id).where(Project.org_id == ctx.org_id, Project.tech_owner_user_id == uid)
    task_cases = select(Task.case_id).where(Task.org_id == ctx.org_id, Task.owner_user_id == uid)
    by_role = {
        "technical_owner": or_(EmployeeCase.tech_owner_user_id == uid, EmployeeCase.project_id.in_(owned_projects)),
        "line_manager": EmployeeCase.line_manager_user_id == uid,
        "employee": EmployeeCase.employee_user_id == uid,
    }.get(ctx.role)
    conditions = [EmployeeCase.id.in_(task_cases)]
    if by_role is not None:
        conditions.append(by_role)
    return q.where(or_(*conditions))


def visible_case_ids(ctx: Ctx) -> Select:
    return visible_cases(ctx).with_only_columns(EmployeeCase.id)
