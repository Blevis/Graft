"""Resolve who is accountable for each responsibility on a case.

Resolution per responsibility type:
1. Active case-level rows (CaseResponsibility) win. Source: case_override (a project default existed when it was
   made), manual, or migrated (legacy column values).
2. Otherwise the project's default holder (a project-scoped RoleAssignment with default_for_cases) is inherited.
   Source: project_default. Nothing is copied, so a case override never changes the project or other cases.
3. Otherwise the responsibility is unassigned and, if the org marks it required, surfaces as an ownership gap.

Read-only. The AI layer may import this; it writes nothing."""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CaseResponsibility, EmployeeCase, RoleAssignment
from .roles import RESPONSIBILITY_TYPES


@dataclass(frozen=True)
class Assigned:
    responsibility_type: str
    user_id: str
    source: str  # project_default | case_override | manual | migrated
    is_primary: bool
    assignment_id: str
    assignment_kind: str  # case_responsibility | role_assignment
    access_item_id: str | None = None
    assigned_by_user_id: str | None = None
    assigned_at: object | None = None
    notes: str | None = None


def _valid(row, today: date | None) -> bool:
    if today is None:
        return True
    return (row.valid_from is None or row.valid_from <= today) and (row.valid_until is None or today <= row.valid_until)


class ResponsibilityIndex:
    """Loads every active responsibility and project default in one org once per request."""

    def __init__(self, db: Session, org_id: str, today: date | None = None):
        self.case_rows: dict[str, list[CaseResponsibility]] = {}
        for r in db.execute(select(CaseResponsibility).where(
                CaseResponsibility.org_id == org_id, CaseResponsibility.is_active.is_(True))
                .order_by(CaseResponsibility.assigned_at)).scalars():
            if _valid(r, today):
                self.case_rows.setdefault(r.case_id, []).append(r)
        self.project_defaults: dict[tuple[str, str], list[RoleAssignment]] = {}
        for g in db.execute(select(RoleAssignment).where(
                RoleAssignment.org_id == org_id, RoleAssignment.is_active.is_(True),
                RoleAssignment.scope_type == "project", RoleAssignment.default_for_cases.is_(True))
                .order_by(RoleAssignment.created_at)).scalars():
            if _valid(g, today) and g.role_code in RESPONSIBILITY_TYPES:
                self.project_defaults.setdefault((g.scope_id, g.role_code), []).append(g)

    def project_default(self, project_id: str | None, rtype: str) -> RoleAssignment | None:
        rows = self.project_defaults.get((project_id, rtype), []) if project_id else []
        return rows[0] if rows else None

    def for_case(self, case: EmployeeCase) -> dict[str, list[Assigned]]:
        out: dict[str, list[Assigned]] = {}
        rows = self.case_rows.get(case.id, [])
        for rtype in RESPONSIBILITY_TYPES:
            mine = [r for r in rows if r.responsibility_type == rtype]
            if mine:
                items = [Assigned(rtype, r.user_id, r.source, r.is_primary, r.id, "case_responsibility",
                                  r.access_item_id, r.assigned_by_user_id, r.assigned_at, r.notes) for r in mine]
            else:
                d = self.project_default(case.project_id, rtype)
                items = [Assigned(rtype, d.user_id, "project_default", True, d.id, "role_assignment",
                                  None, d.assigned_by_user_id, d.created_at, None)] if d else []
            out[rtype] = sorted(items, key=lambda a: (not a.is_primary,))
        return out

    def primary(self, case: EmployeeCase, rtype: str) -> str | None:
        """The one person who acts formally for this responsibility (e.g. the technical reviewer)."""
        items = [a for a in self.for_case(case)[rtype] if a.access_item_id is None]
        primaries = [a for a in items if a.is_primary] or items
        return primaries[0].user_id if primaries else None

    def held_by(self, case: EmployeeCase, user_id: str) -> set[str]:
        return {a.responsibility_type for items in self.for_case(case).values() for a in items if a.user_id == user_id}

    def access_scope(self, case: EmployeeCase, user_id: str) -> tuple[bool, set[str]]:
        """(whole case?, specific access item ids) for which this user is the access responsible."""
        whole, items = False, set()
        for a in self.for_case(case)["access_responsible"]:
            if a.user_id == user_id:
                if a.access_item_id:
                    items.add(a.access_item_id)
                else:
                    whole = True
        return whole, items

    def gaps(self, case: EmployeeCase, required: list[str]) -> list[str]:
        """Required responsibilities nobody holds. Shown as actionable gaps; never auto-filled."""
        resolved = self.for_case(case)
        return [t for t in required if t in RESPONSIBILITY_TYPES and not resolved.get(t)]
