"""Case intake and onboarding workflow: create, import, templates, requirement changes, submitted evidence.

Coordinators and admins create and maintain cases. Every referenced project and person is resolved inside the
caller's org (another org's id is a 404); people must be active members holding the role they are given. Template
versions are snapshotted onto a case when it is created; later template edits never change existing cases."""
import csv
import hashlib
import io
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    CaseRequirement, CaseResponsibility, EmployeeCase, Membership, Project, RoleAssignment, Source, User,
    WorkflowTemplate,
)
from ..models._base import utcnow
from ..schemas.requests import (
    ApplyTemplate, CaseCreate, CsvImport, RequirementCreate, RequirementPatch, SourceSubmit, TemplateCreate,
    TemplateVersionCreate,
)
from ..services import audit
from ..services import serialize as ser
from ..services.cases import case_detail, load_case
from ..services.jobs import enqueue_analysis
from ..services.org_settings import get_org_settings
from ..services.permissions import EMPLOYEE, FULL, Policy
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, get_scoped, require_roles, scoped
from ..services.workflow import (
    MOVEMENT_TEMPLATE, apply_template, current_template, ensure_default_templates, validate_definition,
)

router = APIRouter(tags=["workflow"])
COORD = require_roles("org_admin", "pmo_coordinator")
ADMIN = require_roles("org_admin")
MAX_IMPORT_ROWS = 500
MOVEMENTS = {"new_hire": "new_hire", "new hire": "new_hire", "reallocation": "reallocation",
             "project transfer": "reallocation", "transfer": "reallocation"}


# ---------- helpers ----------

def _next_ref(db: Session, org_id: str, prefix: str = "ONB") -> str:
    refs = db.execute(select(EmployeeCase.ref).where(EmployeeCase.org_id == org_id,
                                                     EmployeeCase.ref.like(f"{prefix}-%"))).scalars()
    nums = [int(m.group(1)) for r in refs if (m := re.fullmatch(rf"{prefix}-(\d+)", r))]
    return f"{prefix}-{(max(nums) + 1 if nums else 1):03d}"


def _eligible(db: Session, org_id: str, user_id: str, role: str, project_id: str | None) -> bool:
    rows = db.execute(select(RoleAssignment.scope_type, RoleAssignment.scope_id).join(
        Membership, (Membership.user_id == RoleAssignment.user_id) & (Membership.org_id == RoleAssignment.org_id))
        .where(RoleAssignment.org_id == org_id, RoleAssignment.user_id == user_id, RoleAssignment.role_code == role,
               RoleAssignment.is_active.is_(True), Membership.status == "active")).all()
    return any(st == "organization" or (st == "project" and sid == project_id) for st, sid in rows)


def _active_member(db: Session, org_id: str, user_id: str) -> bool:
    m = db.execute(select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id)
                   ).scalar_one_or_none()
    return m is not None and m.status == "active"


def _resolve_person(db: Session, org_id: str, value: str) -> str | None:
    """CSV person reference: exact email or exact full name among active members (case-insensitive)."""
    v = value.strip().lower()
    rows = db.execute(select(User).join(Membership, Membership.user_id == User.id).where(
        Membership.org_id == org_id, Membership.status == "active",
        or_(func.lower(User.email) == v, func.lower(User.name) == v))).scalars().all()
    return rows[0].id if len(rows) == 1 else None


def _create_case(db: Session, ctx: Ctx, data: dict) -> EmployeeCase:
    """Validated create used by the form and the CSV import. Raises HTTPException(422) on a bad reference."""
    project_id = data.get("project_id")
    if project_id:
        get_scoped(db, Project, ctx, project_id)
    for field in ("employee_user_id", "line_manager_user_id", "technical_owner_user_id"):
        if data.get(field) and not _active_member(db, ctx.org_id, data[field]):
            raise HTTPException(422, f"{field.replace('_user_id', '').replace('_', ' ')} is not an active member")
    if data.get("line_manager_user_id") and not _eligible(db, ctx.org_id, data["line_manager_user_id"],
                                                         "line_manager", project_id):
        raise HTTPException(422, "The line manager does not hold the line manager role")
    if data.get("technical_owner_user_id") and not _eligible(db, ctx.org_id, data["technical_owner_user_id"],
                                                            "technical_owner", project_id):
        raise HTTPException(422, "The technical owner does not hold the technical owner role")
    ref = data.get("ref") or _next_ref(db, ctx.org_id)
    if db.execute(scoped(EmployeeCase, ctx).where(EmployeeCase.ref == ref)).first():
        raise HTTPException(409, f"Case reference {ref} already exists")
    if data.get("external_id") and db.execute(scoped(EmployeeCase, ctx).where(
            EmployeeCase.external_id == data["external_id"])).first():
        raise HTTPException(409, f"External id {data['external_id']} already exists")
    template = current_template(db, ctx.org_id, data.get("template_key") or
                               MOVEMENT_TEMPLATE.get(data.get("movement") or "new_hire", "new_hire"))
    case = EmployeeCase(org_id=ctx.org_id, ref=ref, employee=data["employee"].strip(),
                        employee_user_id=data.get("employee_user_id"), movement=data.get("movement"),
                        start_date=data.get("start_date"), project_id=project_id, manager_name=None,
                        tracker_status=None, tracker_updated_at=None, exact_role=data.get("exact_role"),
                        expected_readiness_date=data.get("expected_readiness_date"),
                        external_id=data.get("external_id"))
    db.add(case)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case", entity_id=case.id,
                 action="created", after=audit.snapshot(case))
    for rtype, uid in (("line_manager", data.get("line_manager_user_id")),
                       ("technical_owner", data.get("technical_owner_user_id"))):
        if uid:
            r = CaseResponsibility(org_id=ctx.org_id, case_id=case.id, user_id=uid, responsibility_type=rtype,
                                   is_primary=True, source="manual", assigned_by_user_id=ctx.user_id,
                                   assigned_at=utcnow(), is_active=True)
            db.add(r)
            db.flush()
            audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case_responsibility",
                         entity_id=r.id, action="assigned", after=audit.snapshot(r))
    apply_template(db, case, template, actor_user_id=ctx.user_id, create_tasks=True)
    recompute_case(db, case)
    return case


# ---------- create and maintain ----------

@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, ctx: Ctx = Depends(COORD), db: Session = Depends(get_db)):
    case = _create_case(db, ctx, body.model_dump())
    db.commit()
    return case_detail(db, ctx, case)


@router.get("/cases-meta/form")
def form_options(ctx: Ctx = Depends(COORD), db: Session = Depends(get_db)):
    """What the case form may reference: org projects, active members by eligible role, current templates."""
    ensure_default_templates(db, ctx.org_id)
    db.commit()
    lk = ser.Lookup(db, ctx.org_id)
    holders: dict[str, set[str]] = {}
    for uid, code in db.execute(select(RoleAssignment.user_id, RoleAssignment.role_code).where(
            RoleAssignment.org_id == ctx.org_id, RoleAssignment.is_active.is_(True))).all():
        holders.setdefault(code, set()).add(uid)
    active = [u for uid, u in lk.users.items() if lk.status[uid] == "active"]
    by_role = {code: [lk.user_ref(u.id) for u in sorted(active, key=lambda u: u.name) if u.id in holders.get(code, ())]
               for code in ("line_manager", "technical_owner", "employee")}
    templates = db.execute(scoped(WorkflowTemplate, ctx).where(WorkflowTemplate.is_current.is_(True))
                           .order_by(WorkflowTemplate.key)).scalars().all()
    return {"projects": [lk.project_ref(p) for p in sorted(lk.projects, key=lambda p: lk.projects[p].name)],
            "people": by_role, "members": [lk.user_ref(u.id) for u in sorted(active, key=lambda u: u.name)],
            "templates": [{"key": t.key, "name": t.name, "version": t.version, "movement": t.movement}
                          for t in templates],
            "next_ref": _next_ref(db, ctx.org_id)}


# ---------- CSV import ----------

def _parse(db: Session, ctx: Ctx, text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or "employee" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(422, "The CSV needs a header row with at least an 'employee' column")
    projects = {p.name.lower(): p.id for p in db.execute(scoped(Project, ctx)).scalars()}
    projects |= {p.code.lower(): p.id for p in db.execute(scoped(Project, ctx)).scalars() if p.code}
    existing_ext = set(db.execute(scoped(EmployeeCase, ctx).with_only_columns(EmployeeCase.external_id)).scalars())
    existing_ref = set(db.execute(scoped(EmployeeCase, ctx).with_only_columns(EmployeeCase.ref)).scalars())
    templates = set(db.execute(scoped(WorkflowTemplate, ctx).with_only_columns(WorkflowTemplate.key)).scalars())
    rows, seen = [], {}
    for i, raw in enumerate(reader, start=2):
        if i - 1 > MAX_IMPORT_ROWS:
            raise HTTPException(422, f"At most {MAX_IMPORT_ROWS} rows per import")
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        errors, data = [], {}
        data["employee"] = r.get("employee", "")
        if len(data["employee"]) < 2:
            errors.append("employee is required")
        mv = MOVEMENTS.get(r.get("movement", "").lower() or "new_hire")
        if mv is None:
            errors.append("movement must be new_hire or reallocation")
        data["movement"] = mv
        for f in ("start_date", "expected_readiness_date"):
            if r.get(f):
                try:
                    data[f] = date.fromisoformat(r[f])
                except ValueError:
                    errors.append(f"{f} must be YYYY-MM-DD")
        if r.get("project"):
            data["project_id"] = projects.get(r["project"].lower())
            if not data["project_id"]:
                errors.append(f"unknown project '{r['project']}'")
        for col, field, role in (("line_manager", "line_manager_user_id", "line_manager"),
                                 ("technical_owner", "technical_owner_user_id", "technical_owner"),
                                 ("employee_email", "employee_user_id", None)):
            if r.get(col):
                uid = _resolve_person(db, ctx.org_id, r[col])
                if uid is None:
                    errors.append(f"{col} '{r[col]}' is not exactly one active member")
                elif role and not _eligible(db, ctx.org_id, uid, role, data.get("project_id")):
                    errors.append(f"{col} '{r[col]}' does not hold the {role.replace('_', ' ')} role")
                else:
                    data[field] = uid
        if r.get("ref"):
            if not re.fullmatch(r"[A-Z][A-Z0-9]{1,9}-\d{1,6}", r["ref"]):
                errors.append("ref must look like ONB-011")
            data["ref"] = r["ref"]
        data["external_id"] = r.get("external_id") or None
        if r.get("template"):
            if r["template"] not in templates and r["template"] not in ("new_hire", "project_transfer"):
                errors.append(f"unknown template '{r['template']}'")
            data["template_key"] = r["template"]
        data["exact_role"] = r.get("exact_role") or None
        # Dedupe key: external id, else ref, else employee + start date + project.
        key = ("ext", data["external_id"]) if data["external_id"] else ("ref", data.get("ref")) if data.get("ref") \
            else ("natural", data["employee"].lower(), str(data.get("start_date")), data.get("project_id"))
        action, duplicate = "create", None
        if (data["external_id"] and data["external_id"] in existing_ext) or (data.get("ref") in existing_ref):
            action, duplicate = "skip_existing", "already imported"
        elif key in seen:
            action, duplicate = "error", f"duplicate of line {seen[key]}"
            errors.append(duplicate)
        else:
            seen[key] = i
        if errors and action != "skip_existing":
            action = "error"
        rows.append({"line": i, "employee": data["employee"], "external_id": data["external_id"],
                     "ref": data.get("ref"), "action": action, "errors": errors, "duplicate": duplicate,
                     "_data": data})
    return rows


def _public(rows):
    return [{k: v for k, v in r.items() if k != "_data"} for r in rows]


@router.post("/cases/import/preview")
def import_preview(body: CsvImport, ctx: Ctx = Depends(COORD), db: Session = Depends(get_db)):
    rows = _parse(db, ctx, body.csv)
    return {"rows": _public(rows), "summary": {a: sum(r["action"] == a for r in rows)
                                               for a in ("create", "skip_existing", "error")}}


@router.post("/cases/import")
def import_commit(body: CsvImport, ctx: Ctx = Depends(COORD), db: Session = Depends(get_db)):
    """Creates every valid row in one transaction; invalid rows are reported and skipped. Resubmitting the same
    file is safe: rows whose external id or ref already exists are skipped, so fix-and-resubmit never duplicates."""
    rows = _parse(db, ctx, body.csv)
    created = []
    for r in rows:
        if r["action"] != "create":
            continue
        try:
            # Rows were validated in _parse; _create_case re-checks references before it writes anything.
            case = _create_case(db, ctx, r["_data"])
            created.append(case.ref)
            r["action"], r["ref"] = "created", case.ref
        except HTTPException as e:
            r["action"], r["errors"] = "error", [str(e.detail)]
    digest = hashlib.sha256(body.csv.encode()).hexdigest()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="import", entity_id=digest[:32],
                 action="cases_imported", after={"created": created,
                                                 "skipped": sum(r["action"] == "skip_existing" for r in rows),
                                                 "errors": sum(r["action"] == "error" for r in rows)})
    db.commit()
    return {"rows": _public(rows), "created": created}


# ---------- templates ----------

def _template_out(t: WorkflowTemplate, lk=None) -> dict:
    return {"id": t.id, "key": t.key, "version": t.version, "name": t.name, "movement": t.movement,
            "definition": t.definition, "is_current": t.is_current, "note": t.note,
            "created_at": ser.iso(t.created_at), "created_by": lk.user_ref(t.created_by_user_id) if lk else None}


@router.get("/templates")
def list_templates(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    ensure_default_templates(db, ctx.org_id)
    db.commit()
    lk = ser.Lookup(db, ctx.org_id)
    rows = db.execute(scoped(WorkflowTemplate, ctx).order_by(WorkflowTemplate.key, WorkflowTemplate.version.desc())
                      ).scalars().all()
    return {"templates": [_template_out(t, lk) for t in rows], "can_edit": "org_admin" in ctx.org_roles}


@router.post("/templates", status_code=201)
def create_template(body: TemplateCreate, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    if db.execute(scoped(WorkflowTemplate, ctx).where(WorkflowTemplate.key == body.key)).first():
        raise HTTPException(409, "A template with this key exists; add a version instead")
    t = WorkflowTemplate(org_id=ctx.org_id, key=body.key, version=1, name=body.name, movement=body.movement,
                         definition=validate_definition(body.definition), is_current=True, note=body.note,
                         created_by_user_id=ctx.user_id)
    db.add(t)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="template", entity_id=t.id,
                 action="created", after=_template_out(t))
    db.commit()
    return _template_out(t, ser.Lookup(db, ctx.org_id))


@router.post("/templates/{key}/versions", status_code=201)
def add_version(key: str, body: TemplateVersionCreate, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    """A new version for new cases. Cases created from earlier versions keep their snapshot."""
    cur = current_template(db, ctx.org_id, key)
    t = WorkflowTemplate(org_id=ctx.org_id, key=key, version=cur.version + 1, name=body.name,
                         movement=body.movement if body.movement is not None else cur.movement,
                         definition=validate_definition(body.definition), is_current=True, note=body.note,
                         created_by_user_id=ctx.user_id)
    cur.is_current = False
    db.add(t)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="template", entity_id=t.id,
                 action="version_added", before=_template_out(cur), after=_template_out(t))
    db.commit()
    return _template_out(t, ser.Lookup(db, ctx.org_id))


# ---------- per-case requirements ----------

@router.post("/cases/{case_id}/apply-template")
def apply_case_template(case_id: str, body: ApplyTemplate, ctx: Ctx = Depends(COORD), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    apply_template(db, case, current_template(db, ctx.org_id, body.template_key), actor_user_id=ctx.user_id,
                   create_tasks=body.create_tasks)
    db.commit()
    return case_detail(db, ctx, case)


@router.post("/cases/{case_id}/requirements", status_code=201)
def add_requirement(case_id: str, body: RequirementCreate, ctx: Ctx = Depends(COORD), db: Session = Depends(get_db)):
    case = load_case(db, ctx, case_id)
    if db.execute(scoped(CaseRequirement, ctx).where(CaseRequirement.case_id == case.id,
                                                     CaseRequirement.key == body.key)).first():
        raise HTTPException(409, "This case already has a requirement with that key")
    pos = db.execute(select(func.count()).select_from(CaseRequirement).where(
        CaseRequirement.case_id == case.id)).scalar_one()
    r = CaseRequirement(org_id=ctx.org_id, case_id=case.id, key=body.key, title=body.title, kind=body.kind,
                        applicability=body.applicability, evidence_expectation=body.evidence_expectation,
                        due_date=body.due_date, assignee_role=body.assignee_role, position=pos,
                        changed_by_user_id=ctx.user_id, change_reason=body.reason)
    db.add(r)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case_requirement", entity_id=r.id,
                 action="added", after=audit.snapshot(r))
    db.commit()
    return case_detail(db, ctx, case)


@router.patch("/cases/{case_id}/requirements/{requirement_id}")
def patch_requirement(case_id: str, requirement_id: str, body: RequirementPatch, ctx: Ctx = Depends(COORD),
                      db: Session = Depends(get_db)):
    """Targeted change for one case (e.g. a milestone that does not apply), with a mandatory, audited reason."""
    case = load_case(db, ctx, case_id)
    r = get_scoped(db, CaseRequirement, ctx, requirement_id)
    if r.case_id != case.id:
        raise HTTPException(404, "Not found")
    before = audit.snapshot(r)
    for field in ("applicability", "due_date", "title"):
        if field in body.model_fields_set and getattr(body, field) is not None:
            setattr(r, field, getattr(body, field))
    r.change_reason, r.changed_by_user_id = body.reason.strip(), ctx.user_id
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="case_requirement", entity_id=r.id,
                 action="changed", before=before, after=audit.snapshot(r))
    db.commit()
    return case_detail(db, ctx, case)


# ---------- evidence submitted from the case (employee or case team) ----------

@router.post("/cases/{case_id}/sources", status_code=201)
def submit_source(case_id: str, body: SourceSubmit, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    """The employee (own case) or the case team adds evidence. It is stored verbatim, versioned like any source and
    analysed in the background; it is one report among others, never a decision."""
    case = load_case(db, ctx, case_id)
    policy = Policy(db, ctx)
    level = policy.level(case)
    if level not in (FULL, EMPLOYEE):
        raise HTTPException(403, "Only the employee or the case team can add evidence to this case")
    labels = ser.Lookup(db, ctx.org_id).labels
    role = "employee" if level == EMPLOYEE else (sorted(policy.roles_for_case(case)) or [ctx.role])[0]
    s = Source(org_id=ctx.org_id, kind=body.kind, title=body.title.strip(), case_id=case.id,
               project_id=case.project_id, author_role=labels.get(role, role), recipient_role=None,
               date=body.source_date or policy.today, body=body.body,
               body_sha256=hashlib.sha256(body.body.encode("utf-8")).hexdigest(), version=1, ingested_via="paste",
               created_by_user_id=ctx.user_id, channel="case_page", sender=ctx.user.name)
    db.add(s)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="source", entity_id=s.id,
                 action="submitted", after=ser.source_meta(s))
    job = enqueue_analysis(db, s, reason="submitted")
    db.commit()
    return {"source": ser.source_out(s), "job": ser.job_out(job) if job else None}
