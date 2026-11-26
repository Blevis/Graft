"""Bind incoming evidence to an employee case using strong identifiers first.

1. Exactly one case reference (e.g. ONB-005) in the title or body.
2. Otherwise exactly one employee full name.
Several candidates at the same strength = ambiguous: the source goes to the review queue with its candidates and a
person links it. No candidate = unmatched. Source bodies are only searched, never interpreted."""
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EmployeeCase


@dataclass
class Match:
    case: EmployeeCase | None
    status: str  # matched | needs_review | unmatched
    candidates: list[EmployeeCase] = field(default_factory=list)
    reason: str = ""


def match_detail(db: Session, org_id: str, title: str | None, body: str, hint_ref: str | None = None) -> Match:
    text = f"{hint_ref or ''}\n{title or ''}\n{body}"
    cases = db.execute(select(EmployeeCase).where(EmployeeCase.org_id == org_id)).scalars().all()
    by_ref = [c for c in cases if re.search(rf"\b{re.escape(c.ref)}\b", text)]
    if len(by_ref) == 1:
        return Match(by_ref[0], "matched", by_ref, "case reference")
    if len(by_ref) > 1:
        return Match(None, "needs_review", by_ref, "several case references")
    by_name = [c for c in cases if c.employee.lower() in text.lower()]
    if len(by_name) == 1:
        return Match(by_name[0], "matched", by_name, "employee name")
    if len(by_name) > 1:
        return Match(None, "needs_review", by_name, "several employees named")
    return Match(None, "unmatched", [], "no case reference or employee name")


def match_case(db: Session, org_id: str, title: str | None, body: str) -> EmployeeCase | None:
    """Explicit match only: a case ref (ONB-005) or the employee's full name. Ambiguity returns None."""
    return match_detail(db, org_id, title, body).case
