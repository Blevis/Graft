"""Bind incoming evidence to an employee case using identifying details (employee name, case ref)."""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EmployeeCase


def match_case(db: Session, org_id: str, title: str | None, body: str) -> EmployeeCase | None:
    """Explicit match only: a case ref (ONB-005) or the employee's full name. Ambiguity returns None."""
    text = f"{title or ''}\n{body}"
    cases = db.execute(select(EmployeeCase).where(EmployeeCase.org_id == org_id)).scalars().all()

    by_ref = [c for c in cases if re.search(rf"\b{re.escape(c.ref)}\b", text)]
    if len(by_ref) == 1:
        return by_ref[0]

    by_name = [c for c in cases if c.employee.lower() in text.lower()]
    if len(by_name) == 1:
        return by_name[0]
    return None
