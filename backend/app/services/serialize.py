"""Shape ORM rows into the JSON contract mirrored by frontend/src/lib/types.ts."""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AccessItem, AnalysisRun, Claim, EmployeeCase, Finding, KnowledgeRef, Membership, Org, Project,
    RejectedCandidate, Review, Source, Task, User,
)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def utc(v: datetime) -> datetime:
    """SQLite returns naive datetimes; everything we store is UTC."""
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def iso(v: date | datetime | None) -> str | None:
    if v is None:
        return None
    return utc(v).isoformat() if isinstance(v, datetime) else v.isoformat()


class Lookup:
    """Per-request cache of users / projects / roles in one org."""

    def __init__(self, db: Session, org_id: str):
        self.db, self.org_id = db, org_id
        rows = db.execute(
            select(User, Membership.role).join(Membership, Membership.user_id == User.id)
            .where(Membership.org_id == org_id)
        ).all()
        self.users = {u.id: u for u, _ in rows}
        self.roles = {u.id: r for u, r in rows}
        self.projects = {p.id: p for p in db.execute(select(Project).where(Project.org_id == org_id)).scalars()}

    def user_ref(self, user_id: str | None) -> dict | None:
        u = self.users.get(user_id) if user_id else None
        return {"id": u.id, "name": u.name, "role": self.roles[u.id]} if u else None

    def project_ref(self, project_id: str | None) -> dict | None:
        p = self.projects.get(project_id) if project_id else None
        return {"id": p.id, "name": p.name, "code": p.code} if p else None

    def tech_owner_id(self, case: EmployeeCase) -> str | None:
        if case.tech_owner_user_id:
            return case.tech_owner_user_id
        p = self.projects.get(case.project_id) if case.project_id else None
        return p.tech_owner_user_id if p else None


def org_out(org: Org, settings: dict) -> dict:
    return {"id": org.id, "name": org.name, "is_demo": org.is_demo, "as_of_date": settings["as_of_date"]}


def case_out(case: EmployeeCase, lk: Lookup, today: date, latest_review: Review | None) -> dict:
    return {
        "id": case.id,
        "ref": case.ref,
        "employee": case.employee,
        "movement": case.movement,
        "start_date": iso(case.start_date),
        "project": lk.project_ref(case.project_id),
        "manager": case.manager_name,
        "tracker_status": case.tracker_status,
        "tracker_updated_at": iso(case.tracker_updated_at),
        "tracker_age_days": (today - case.tracker_updated_at).days if case.tracker_updated_at else None,
        "tech_owner": lk.user_ref(lk.tech_owner_id(case)),
        "employee_user_id": case.employee_user_id,
        "stage": latest_review.observed_stage if latest_review else None,
        "expected_readiness_date": iso(case.expected_readiness_date),
        "exact_role": case.exact_role,
    }


def source_out(s: Source) -> dict:
    return {
        "id": s.id, "ref": s.ref, "kind": s.kind, "title": s.title, "case_id": s.case_id,
        "project_id": s.project_id, "author_role": s.author_role, "recipient_role": s.recipient_role,
        "date": iso(s.date), "header": s.header, "body": s.body, "body_sha256": s.body_sha256,
        "version": s.version, "supersedes_id": s.supersedes_id, "ingested_via": s.ingested_via,
        "created_at": iso(s.created_at),
    }


def run_out(r: AnalysisRun) -> dict:
    return {
        "id": r.id, "source_id": r.source_id, "body_sha256": r.body_sha256, "prompt_version": r.prompt_version,
        "schema_version": r.schema_version, "model": r.model, "mode": r.mode, "status": r.status,
        "error": r.error, "created_at": iso(r.created_at),
    }


def claim_out(c: Claim) -> dict:
    return {"id": c.id, "source_id": c.source_id, "analysis_run_id": c.run_id, "scope": c.scope, "value": c.value,
            "reference": c.reference, "quote": c.quote, "start": c.start, "end": c.end}


def rejected_out(r: RejectedCandidate) -> dict:
    return {"id": r.id, "source_id": r.source_id, "analysis_run_id": r.run_id, "raw": r.raw, "reason": r.reason}


def finding_out(f: Finding) -> dict:
    return {"id": f.id, "rule_id": f.rule_id, "rule_version": f.rule_version, "severity": f.severity,
            "message": f.message, "detail": f.detail, "evidence": f.evidence or [], "created_at": iso(f.created_at)}


def task_out(t: Task, lk: Lookup, case: EmployeeCase | None = None, today: date | None = None) -> dict:
    out = {
        "id": t.id, "case_id": t.case_id, "finding_id": t.finding_id, "title": t.title,
        "owner_user": lk.user_ref(t.owner_user_id), "owner_role": t.owner_role, "due_date": iso(t.due_date),
        "sla_hours": t.sla_hours, "status": t.status, "cited_source_ids": t.cited_source_ids or [],
        "origin": t.origin, "created_by": lk.user_ref(t.created_by_user_id), "created_at": iso(t.created_at),
        "completed_at": iso(t.completed_at),
        "overdue": bool(today and t.status == "open" and t.due_date and t.due_date < today),
    }
    if case is not None:
        out["case"] = {"id": case.id, "ref": case.ref, "employee": case.employee}
    return out


def review_out(r: Review, lk: Lookup) -> dict:
    return {
        "id": r.id, "case_id": r.case_id, "disposition": r.disposition, "scope": r.scope, "rationale": r.rationale,
        "observed_stage": r.observed_stage, "cited_source_ids": r.cited_source_ids or [], "task_id": r.task_id,
        "reviewer": lk.user_ref(r.reviewer_user_id), "created_at": iso(r.created_at),
    }


def access_out(a: AccessItem) -> dict:
    return {"id": a.id, "case_id": a.case_id, "system": a.system, "state": a.state,
            "requested_at": iso(a.requested_at), "owner_role": a.owner_role, "next_follow_up": iso(a.next_follow_up),
            "evidence_source_ids": a.evidence_source_ids or [], "updated_at": iso(a.created_at)}


def knowledge_out(k: KnowledgeRef, lk: Lookup) -> dict:
    return {"id": k.id, "project_id": k.project_id, "project": lk.project_ref(k.project_id), "title": k.title,
            "location": k.location, "owner_role": k.owner_role, "last_verified": iso(k.last_verified),
            "source_id": k.source_id}
