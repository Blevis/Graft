"""Gap rules. Pure functions of evidence, verified claims, access items and org settings.
Findings are derived: recompute_case() replaces them. No import path to task or review writers."""
import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import product

from sqlalchemy import select
from sqlalchemy.orm import Session

from .responsibilities import ResponsibilityIndex
from ..models import AccessItem, Claim, EmployeeCase, Finding, Project, Source
from .evidence import current_claims, latest_sources
from .org_settings import as_of, get_org_settings

RULE_VERSION = "v1"

CLOSURE = {("onboarding_closure", "reported_closed"), ("overall_independence", "reported_independent")}
QUALIFIER = {
    ("complex_scenarios", "coverage_pending"),
    ("standard_requests", "occasional_support"),
    ("standard_requests", "support_required"),
    ("technical_readiness_report", "ready_with_support"),
    ("technical_readiness_report", "partially_ready"),
    ("technical_readiness_report", "not_ready"),
}
BLOCKING_ACCESS = {"not_provisioned", "awaiting_approval"}


@dataclass
class Draft:
    rule_id: str
    severity: str
    message: str
    key: str
    detail: str | None = None
    evidence: list[dict] = field(default_factory=list)


def working_days_between(start: date, end: date) -> int:
    """Weekdays strictly after start, up to and including end."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def evaluate(
    case: EmployeeCase,
    project: Project | None,
    sources: list[Source],
    claims: list[Claim],
    access: list[AccessItem],
    settings: dict,
    tech_owner_id: str | None = None,
) -> list[Draft]:
    today = as_of(settings)
    out: list[Draft] = []

    # Missing tracker fields stay NULL and raise MISSING_* findings.
    if case.project_id is None:
        out.append(Draft("MISSING_PROJECT", "medium", "Project not recorded in tracker", "project"))
    if not case.manager_name:
        out.append(Draft("MISSING_MANAGER", "medium", "Manager not recorded in tracker", "manager"))
    if settings.get("flag_missing_readiness_date") and case.expected_readiness_date is None:
        out.append(Draft("MISSING_READINESS_DATE", "medium", "Expected readiness date not recorded", "readiness_date",
                         detail="The checklist requires an expected readiness date; nobody has recorded one."))
    if project is not None and not tech_owner_id:
        out.append(Draft("MISSING_TECH_OWNER", "high", "No technical owner can validate readiness", "tech_owner"))

    # A tracker status is one report among others; flag it when it is old.
    if case.tracker_updated_at is not None:
        age = (today - case.tracker_updated_at).days
        if age > int(settings["stale_days"]):
            out.append(Draft("STALE_TRACKER", "medium", f"Tracker not updated for {age} days",
                             "stale", detail=f"Last tracker update {case.tracker_updated_at.isoformat()}; "
                             f"threshold {settings['stale_days']} days."))

    # Closure conflict: a broad closure report vs a scoped qualification from a distinct, same-day source.
    by_source: dict[str, list[Claim]] = {}
    for c in claims:
        by_source.setdefault(c.source_id, []).append(c)
    src = {s.id: s for s in sources}
    closers = {sid: [c for c in cs if (c.scope, c.value) in CLOSURE] for sid, cs in by_source.items()}
    quals = {sid: [c for c in cs if (c.scope, c.value) in QUALIFIER] for sid, cs in by_source.items()}
    for a, b in product(closers, quals):
        if a == b or not closers[a] or not quals[b]:
            continue
        sa, sb = src.get(a), src.get(b)
        if sa is None or sb is None or sa.date is None or sa.date != sb.date:
            continue
        ev = [{"source_id": c.source_id, "claim_id": c.id} for c in closers[a] + quals[b]]
        out.append(Draft(
            "CLOSURE_CONFLICT", "high", "Closure needs technical review", f"closure:{a}:{b}",
            detail=f"{sa.author_role or 'A sender'} ({sa.ref or 'source'}) reports closure; "
                   f"{sb.author_role or 'another sender'} ({sb.ref or 'source'}) reports a scoped qualification "
                   f"on the same date ({sa.date.isoformat()}). The date tie establishes no order.",
            evidence=ev,
        ))

    # Access: requested != approved != active != confirmed usable.
    pending = [a for a in access if a.state != "confirmed_usable"]
    if pending:
        blocked = [a for a in pending if a.state in BLOCKING_ACCESS]
        out.append(Draft(
            "ACCESS_NOT_CONFIRMED", "high" if blocked else "medium",
            f"Access not confirmed usable: {len(pending)} of {len(access)} systems",
            "access",
            detail="; ".join(f"{a.system}: {a.state.replace('_', ' ')}" for a in pending)
                   + ". Only a successful test by the employee counts as usable.",
            evidence=[{"source_id": sid, "claim_id": None}
                      for sid in dict.fromkeys(s for a in pending for s in (a.evidence_source_ids or []))],
        ))

    # Unanswered request: a request whose recipient has not replied within N working days.
    for s in sources:
        if not s.recipient_role or s.date is None:
            continue
        is_reply = any(o.author_role == s.recipient_role and o.recipient_role == s.author_role
                       and o.date and o.date <= s.date and o.id != s.id for o in sources)
        replied = any(o.author_role == s.recipient_role and o.date and o.date >= s.date and o.id != s.id
                      for o in sources)
        if is_reply or replied:
            continue
        days = working_days_between(s.date, today)
        if days > int(settings["unanswered_working_days"]):
            out.append(Draft(
                "UNANSWERED_REQUEST", "high", f"Request to {s.recipient_role} unanswered for {days} working days",
                f"unanswered:{s.id}",
                detail=f"{s.author_role} wrote on {s.date.isoformat()}; no later source from {s.recipient_role}.",
                evidence=[{"source_id": s.id, "claim_id": None}],
            ))
    return out


def finding_id(case_id: str, d: Draft) -> str:
    return hashlib.sha1(f"{case_id}|{d.rule_id}|{RULE_VERSION}|{d.key}".encode()).hexdigest()[:32]


def recompute_case(db: Session, case: EmployeeCase) -> list[Finding]:
    settings = get_org_settings(db, case.org_id)
    project = db.get(Project, case.project_id) if case.project_id else None
    sources = latest_sources(db, case.org_id, case_id=case.id)
    claims, _, _ = current_claims(db, sources)
    access = list(db.execute(
        select(AccessItem).where(AccessItem.org_id == case.org_id, AccessItem.case_id == case.id)).scalars())
    tech_owner = ResponsibilityIndex(db, case.org_id, as_of(settings)).primary(case, "technical_owner")
    drafts = evaluate(case, project, sources, claims, access, settings, tech_owner)

    existing = {f.id: f for f in db.execute(
        select(Finding).where(Finding.org_id == case.org_id, Finding.case_id == case.id)).scalars()}
    keep: list[Finding] = []
    for d in drafts:
        fid = finding_id(case.id, d)
        f = existing.pop(fid, None)
        if f is None:
            f = Finding(id=fid, org_id=case.org_id, case_id=case.id)
            db.add(f)
        f.rule_id, f.rule_version, f.severity = d.rule_id, RULE_VERSION, d.severity
        f.message, f.detail, f.evidence = d.message, d.detail, d.evidence
        keep.append(f)
    for stale in existing.values():
        db.delete(stale)
    db.flush()
    return keep
