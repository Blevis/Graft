"""Shape ORM rows into the JSON contract mirrored by frontend/src/lib/types.ts."""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AccessItem, AnalysisRun, Claim, EmployeeCase, Finding, KnowledgeRef, Membership, Org, Project,
    RejectedCandidate, Review, RoleAssignment, Source, Task, TrainingEntry, User,
)
from .org_settings import as_of, get_org_settings
from .responsibilities import ResponsibilityIndex
from .roles import primary_role, role_labels

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def utc(v: datetime) -> datetime:
    """SQLite returns naive datetimes; everything we store is UTC."""
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def iso(v: date | datetime | None) -> str | None:
    if v is None:
        return None
    return utc(v).isoformat() if isinstance(v, datetime) else v.isoformat()


class Lookup:
    """Per-request cache of users / projects / roles / responsibilities in one org."""

    def __init__(self, db: Session, org_id: str):
        self.db, self.org_id = db, org_id
        rows = db.execute(
            select(User, Membership.status).join(Membership, Membership.user_id == User.id)
            .where(Membership.org_id == org_id)
        ).all()
        self.users = {u.id: u for u, _ in rows}
        self.status = {u.id: st for u, st in rows}
        self.role_codes: dict[str, set[str]] = {uid: set() for uid in self.users}
        for user_id, code in db.execute(select(RoleAssignment.user_id, RoleAssignment.role_code).where(
                RoleAssignment.org_id == org_id, RoleAssignment.is_active.is_(True))).all():
            self.role_codes.setdefault(user_id, set()).add(code)
        self.roles = {uid: primary_role(codes) or "project_member" for uid, codes in self.role_codes.items()}
        self.projects = {p.id: p for p in db.execute(select(Project).where(Project.org_id == org_id)).scalars()}
        self.settings = get_org_settings(db, org_id)
        self.labels = role_labels(self.settings.get("role_labels"))
        self._idx: ResponsibilityIndex | None = None

    @property
    def idx(self) -> ResponsibilityIndex:
        if self._idx is None:
            self._idx = ResponsibilityIndex(self.db, self.org_id, as_of(self.settings))
        return self._idx

    def user_ref(self, user_id: str | None) -> dict | None:
        u = self.users.get(user_id) if user_id else None
        return {"id": u.id, "name": u.name, "role": self.roles.get(u.id, "project_member")} if u else None

    def project_ref(self, project_id: str | None) -> dict | None:
        p = self.projects.get(project_id) if project_id else None
        return {"id": p.id, "name": p.name, "code": p.code} if p else None

    def tech_owner_id(self, case: EmployeeCase) -> str | None:
        """The case's primary technical reviewer (assigned or inherited from the project default)."""
        return self.idx.primary(case, "technical_owner")

    def line_manager_id(self, case: EmployeeCase) -> str | None:
        return self.idx.primary(case, "line_manager")


def org_out(org: Org, settings: dict) -> dict:
    return {"id": org.id, "name": org.name, "is_demo": org.is_demo, "as_of_date": as_of(settings).isoformat(),
            "clock_mode": settings.get("clock_mode", "as_of"), "timezone": settings.get("timezone")}


def readiness_out(st, lk: "Lookup") -> dict:
    """Final readiness comes only from an authorized close review; the tracker status stays a separate report."""
    f = st.final_review
    return {"status": st.status, "final_review_id": f.id if f else None,
            "signed_off_at": iso(f.created_at) if f else None,
            "signed_off_by": lk.user_ref(f.reviewer_user_id) if f else None,
            "reopened_at": iso(st.reopen_review.created_at) if st.reopen_review and not f else None,
            "validated_milestones": sorted(st.validated)}


def case_out(case: EmployeeCase, lk: Lookup, today: date, latest_review: Review | None, st=None) -> dict:
    stage = latest_review.observed_stage if latest_review else None
    if st is not None and st.status == "signed_off" and stage is None:
        stage = "validated"
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
        "line_manager": lk.user_ref(lk.line_manager_id(case)),
        "employee_user_id": case.employee_user_id,
        "stage": stage,
        "expected_readiness_date": iso(case.expected_readiness_date),
        "exact_role": case.exact_role,
        "external_id": case.external_id,
        "readiness": readiness_out(st, lk) if st is not None else None,
    }


def source_out(s: Source) -> dict:
    return {
        "id": s.id, "ref": s.ref, "kind": s.kind, "title": s.title, "case_id": s.case_id,
        "project_id": s.project_id, "author_role": s.author_role, "recipient_role": s.recipient_role,
        "date": iso(s.date), "header": s.header, "body": s.body, "body_sha256": s.body_sha256,
        "version": s.version, "supersedes_id": s.supersedes_id, "ingested_via": s.ingested_via,
        "created_at": iso(s.created_at), "external_id": s.external_id, "channel": s.channel, "sender": s.sender,
        "received_at": iso(s.received_at), "match_status": s.match_status, "document": s.document,
    }


def run_out(r: AnalysisRun) -> dict:
    return {
        "id": r.id, "source_id": r.source_id, "body_sha256": r.body_sha256, "prompt_version": r.prompt_version,
        "schema_version": r.schema_version, "model": r.model, "provider": r.provider,
        "model_digest": r.model_digest, "mode": r.mode, "status": r.status,
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


def task_out(t: Task, lk: Lookup, case: EmployeeCase | None = None, today: date | None = None,
             clock: dict | None = None) -> dict:
    out = {
        "id": t.id, "case_id": t.case_id, "finding_id": t.finding_id, "title": t.title,
        "owner_user": lk.user_ref(t.owner_user_id), "owner_role": t.owner_role, "due_date": iso(t.due_date),
        "sla_hours": t.sla_hours, "status": t.status, "cited_source_ids": t.cited_source_ids or [],
        "origin": t.origin, "created_by": lk.user_ref(t.created_by_user_id), "created_at": iso(t.created_at),
        "completed_at": iso(t.completed_at),
        "overdue": bool(today and t.status == "open" and t.due_date and t.due_date < today
                        and not (clock or {}).get("waiting")),
        "queue": t.queue, "requirement_id": t.requirement_id,
        "reminded_at": iso(t.reminded_at), "escalated_at": iso(t.escalated_at),
        "waiting": bool((clock or {}).get("waiting")), "waiting_reason": (clock or {}).get("waiting_reason"),
        "working_hours": (clock or {}).get("working_hours"), "waiting_hours": (clock or {}).get("waiting_hours"),
    }
    if case is not None:
        out["case"] = {"id": case.id, "ref": case.ref, "employee": case.employee}
    return out


def review_out(r: Review, lk: Lookup) -> dict:
    from .readiness import legacy_gaps

    return {
        "id": r.id, "case_id": r.case_id, "disposition": r.disposition, "scope": r.scope, "rationale": r.rationale,
        "observed_stage": r.observed_stage, "cited_source_ids": r.cited_source_ids or [], "task_id": r.task_id,
        "reviewer": lk.user_ref(r.reviewer_user_id), "created_at": iso(r.created_at),
        "milestone_key": r.milestone_key, "supersedes_review_id": r.supersedes_review_id,
        "exception_reason": r.exception_reason, "bypassed_criteria": r.bypassed_criteria or [],
        "policy_version": r.policy_version, "gaps": legacy_gaps(r),
    }


def access_out(a: AccessItem, lk: "Lookup | None" = None) -> dict:
    return {"id": a.id, "case_id": a.case_id, "system": a.system, "state": a.state,
            "requested_at": iso(a.requested_at), "owner_role": a.owner_role, "next_follow_up": iso(a.next_follow_up),
            "evidence_source_ids": a.evidence_source_ids or [], "updated_at": iso(a.created_at),
            "tester": lk.user_ref(a.tester_user_id) if lk else None,
            "tested_by": lk.user_ref(a.tested_by_user_id) if lk else None, "tested_at": iso(a.tested_at)}


def knowledge_out(k: KnowledgeRef, lk: Lookup, today: date | None = None, review_after_days: int = 90) -> dict:
    stale = bool(today and (k.last_verified is None or (today - k.last_verified).days > review_after_days))
    return {"id": k.id, "project_id": k.project_id, "project": lk.project_ref(k.project_id), "title": k.title,
            "location": k.location, "owner_role": k.owner_role, "last_verified": iso(k.last_verified),
            "source_id": k.source_id, "topic": k.topic, "description": k.description,
            "applies_to_roles": k.applies_to_roles or [], "tags": k.tags or [], "needs_review": stale}


def training_out(e: TrainingEntry, lk: Lookup, with_notes: bool = True) -> dict:
    return {"id": e.id, "case_id": e.case_id, "kind": e.kind, "title": e.title,
            "notes": e.notes if with_notes else None, "activity_date": iso(e.activity_date),
            "cited_source_ids": (e.cited_source_ids or []) if with_notes else [],
            "recorded_by": lk.user_ref(e.recorded_by_user_id), "capacity": e.capacity, "created_at": iso(e.created_at)}


def stakeholders_out(case: EmployeeCase, lk: Lookup, access_items: dict[str, str] | None = None) -> list[dict]:
    """The Stakeholders & Responsibilities panel: one row per responsibility type, unassigned rows included."""
    from .roles import RESPONSIBILITY_TYPES

    required = set(lk.settings.get("required_responsibilities") or [])
    resolved = lk.idx.for_case(case)
    holders: dict[str, set[str]] = {}
    for items in resolved.values():
        for a in items:
            holders.setdefault(a.user_id, set()).add(a.responsibility_type)
    out = []
    for rtype in RESPONSIBILITY_TYPES:
        out.append({
            "responsibility_type": rtype,
            "label": lk.labels.get(rtype, rtype),
            "required": rtype in required,
            "assignments": [{
                "id": a.assignment_id, "kind": a.assignment_kind, "user": lk.user_ref(a.user_id),
                "source": a.source, "is_primary": a.is_primary, "access_item_id": a.access_item_id,
                "system": (access_items or {}).get(a.access_item_id) if a.access_item_id else None,
                "assigned_by": lk.user_ref(a.assigned_by_user_id), "assigned_at": iso(a.assigned_at),
                "notes": a.notes,
                "also_holds": sorted(holders.get(a.user_id, set()) - {rtype}),
            } for a in resolved[rtype]],
        })
    return out


SOURCE_META_FIELDS = ("id", "ref", "kind", "title", "case_id", "project_id", "author_role", "recipient_role", "date",
                      "body_sha256", "version", "supersedes_id", "ingested_via", "external_id", "channel", "sender",
                      "received_at", "match_status", "document")


def source_meta(s: Source) -> dict:
    """Audit/operational view of a source: provenance and hash, never the body (the body lives only in the
    canonical evidence row)."""
    return {k: iso(getattr(s, k)) if isinstance(getattr(s, k), (date, datetime)) else getattr(s, k)
            for k in SOURCE_META_FIELDS}


def job_out(j) -> dict:
    return {"id": j.id, "source_id": j.source_id, "case_id": j.case_id, "status": j.status, "reason": j.reason,
            "attempts": j.attempts, "max_attempts": j.max_attempts, "outcome_mode": j.outcome_mode,
            "last_error": j.last_error, "run_after": iso(j.run_after), "created_at": iso(j.created_at),
            "finished_at": iso(j.finished_at)}
