"""People & Roles (Settings) and Project teams. The only writer of memberships and role assignments.

Rules enforced here, server-side:
- Only an org admin grants or revokes roles at organisation scope. Nobody grants themselves anything.
- Project rosters may also be edited by the PMO and, when the org allows it, by that project's manager; they can
  only add people who already hold that role in the organisation, and never org-wide roles.
- A project or case scope must belong to the caller's org (another org's id is a 404, like any other read).
- The last active org admin cannot be revoked or suspended.
- Revocation is soft: history and who granted what stay visible. Every change emits an AuditEvent."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import EmployeeCase, Membership, Project, RoleAssignment, Setting, User
from ..models._base import utcnow
from ..schemas.requests import (
    MemberCreate, MemberPatch, ProjectAssignmentCreate, RoleAssignmentCreate, RoleAssignmentPatch, RoleLabelsPatch,
)
from ..services import audit
from ..services import serialize as ser
from ..services.cases import case_rows
from ..services.org_settings import get_org_settings
from ..services.permissions import Policy
from ..services.roles import (
    ORG_ONLY_ROLES, PROJECT_ROLES, RESPONSIBILITY_TYPES, ROLE_REGISTRY, role_labels,
)
from ..services.rules import recompute_case
from ..services.tenancy import Ctx, get_ctx, get_scoped, require_roles, scoped
from ..services.visibility import sees_all, visible_cases

router = APIRouter(tags=["people"])
ADMIN = require_roles("org_admin")


# ---------- helpers ----------

def grant_out(g: RoleAssignment, lk: ser.Lookup, db: Session) -> dict:
    scope_name = None
    if g.scope_type == "project":
        scope_name = (lk.project_ref(g.scope_id) or {}).get("name")
    elif g.scope_type == "case":
        c = db.get(EmployeeCase, g.scope_id)
        scope_name = c.ref if c else None
    return {
        "id": g.id, "user": lk.user_ref(g.user_id), "role_code": g.role_code,
        "role_label": lk.labels.get(g.role_code, g.role_code), "scope_type": g.scope_type, "scope_id": g.scope_id,
        "scope_name": scope_name, "default_for_cases": g.default_for_cases, "is_active": g.is_active,
        "assigned_by": lk.user_ref(g.assigned_by_user_id), "created_at": ser.iso(g.created_at),
        "valid_from": ser.iso(g.valid_from), "valid_until": ser.iso(g.valid_until),
        "revoked_at": ser.iso(g.revoked_at), "revoked_by": lk.user_ref(g.revoked_by_user_id),
    }


def _active_member(db: Session, ctx: Ctx, user_id: str) -> Membership:
    m = db.execute(scoped(Membership, ctx).where(Membership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Not found")
    if m.status != "active":
        raise HTTPException(422, "This member is not active")
    return m


def _active_admins(db: Session, org_id: str) -> set[str]:
    rows = db.execute(select(RoleAssignment.user_id).join(
        Membership, (Membership.user_id == RoleAssignment.user_id) & (Membership.org_id == RoleAssignment.org_id))
        .where(RoleAssignment.org_id == org_id, RoleAssignment.role_code == "org_admin",
               RoleAssignment.scope_type == "organization", RoleAssignment.is_active.is_(True),
               Membership.status == "active")).scalars()
    return set(rows)


def _check_scope(db: Session, ctx: Ctx, scope_type: str, scope_id: str | None) -> None:
    if scope_type == "organization":
        if scope_id is not None:
            raise HTTPException(422, "Organization scope takes no scope_id")
        return
    if not scope_id:
        raise HTTPException(422, f"A {scope_type} scope needs a scope_id")
    get_scoped(db, Project if scope_type == "project" else EmployeeCase, ctx, scope_id)  # other org: 404


def _recompute_project(db: Session, org_id: str, project_id: str | None) -> None:
    if not project_id:
        return
    for case in db.execute(select(EmployeeCase).where(EmployeeCase.org_id == org_id,
                                                      EmployeeCase.project_id == project_id)).scalars():
        recompute_case(db, case)


def _create_grant(db: Session, ctx: Ctx, *, user_id: str, role_code: str, scope_type: str, scope_id: str | None,
                  default_for_cases: bool, valid_from=None, valid_until=None) -> RoleAssignment:
    if user_id == ctx.user_id:
        raise HTTPException(403, "You cannot grant a role to yourself; another administrator must do it")
    _active_member(db, ctx, user_id)
    _check_scope(db, ctx, scope_type, scope_id)
    if role_code in ORG_ONLY_ROLES and scope_type != "organization":
        raise HTTPException(422, "This role applies to the whole organization")
    if default_for_cases:
        if scope_type != "project" or role_code not in RESPONSIBILITY_TYPES:
            raise HTTPException(422, "Only a project-scoped responsibility role can be the project default")
        clash = db.execute(scoped(RoleAssignment, ctx).where(
            RoleAssignment.scope_type == "project", RoleAssignment.scope_id == scope_id,
            RoleAssignment.role_code == role_code, RoleAssignment.default_for_cases.is_(True),
            RoleAssignment.is_active.is_(True))).scalar_one_or_none()
        if clash is not None:
            raise HTTPException(409, "This project already has a default for that responsibility; clear it first")
    dup = db.execute(scoped(RoleAssignment, ctx).where(
        RoleAssignment.user_id == user_id, RoleAssignment.role_code == role_code,
        RoleAssignment.scope_type == scope_type, RoleAssignment.scope_id.is_(None) if scope_id is None
        else RoleAssignment.scope_id == scope_id, RoleAssignment.is_active.is_(True))).scalar_one_or_none()
    if dup is not None:
        raise HTTPException(409, "This person already holds that role at that scope")
    g = RoleAssignment(org_id=ctx.org_id, user_id=user_id, role_code=role_code, scope_type=scope_type,
                       scope_id=scope_id, default_for_cases=default_for_cases, assigned_by_user_id=ctx.user_id,
                       valid_from=valid_from, valid_until=valid_until, is_active=True)
    db.add(g)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="role_assignment", entity_id=g.id,
                 action="granted", after=audit.snapshot(g))
    return g


def _revoke(db: Session, ctx: Ctx, g: RoleAssignment) -> None:
    if not g.is_active:
        raise HTTPException(409, "Already revoked")
    if g.role_code == "org_admin" and g.scope_type == "organization" and _active_admins(db, ctx.org_id) == {g.user_id}:
        raise HTTPException(409, "Assign another organization admin before removing the last one")
    before = audit.snapshot(g)
    g.is_active, g.revoked_at, g.revoked_by_user_id = False, utcnow(), ctx.user_id
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="role_assignment", entity_id=g.id,
                 action="revoked", before=before, after=audit.snapshot(g))


# ---------- members ----------

@router.get("/org/members")
def list_members(ctx: Ctx = Depends(require_roles("org_admin", "pmo_coordinator")), db: Session = Depends(get_db)):
    lk = ser.Lookup(db, ctx.org_id)
    members = db.execute(scoped(Membership, ctx).order_by(Membership.created_at)).scalars().all()
    grants: dict[str, list] = {}
    for g in db.execute(scoped(RoleAssignment, ctx).order_by(RoleAssignment.created_at)).scalars():
        grants.setdefault(g.user_id, []).append(grant_out(g, lk, db))
    out = []
    for m in members:
        u = lk.users[m.user_id]
        out.append({"membership_id": m.id, "user": {"id": u.id, "name": u.name, "title": u.title, "email": u.email},
                    "status": m.status, "joined_at": ser.iso(m.joined_at),
                    "grants": [g for g in grants.get(u.id, []) if g["is_active"]],
                    "history": [g for g in grants.get(u.id, []) if not g["is_active"]]})
    return {"members": out, "can_manage": "org_admin" in ctx.org_roles}


@router.post("/org/members", status_code=201)
def add_member(body: MemberCreate, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    u = User(name=body.name.strip(), title=(body.title or "").strip() or None, email=(body.email or "").strip() or None)
    db.add(u)
    db.flush()
    m = Membership(org_id=ctx.org_id, user_id=u.id, status="active", joined_at=utcnow())
    db.add(m)
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="membership", entity_id=m.id,
                 action="added", after={**audit.snapshot(m), "name": u.name})
    db.commit()
    return {"membership_id": m.id, "user_id": u.id, "status": m.status}


@router.patch("/org/members/{user_id}")
def patch_member(user_id: str, body: MemberPatch, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    m = db.execute(scoped(Membership, ctx).where(Membership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Not found")
    if user_id == ctx.user_id:
        raise HTTPException(403, "You cannot change your own membership status")
    if body.status == "suspended" and _active_admins(db, ctx.org_id) == {user_id}:
        raise HTTPException(409, "Assign another organization admin before suspending the last one")
    before = audit.snapshot(m)
    m.status = body.status
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="membership", entity_id=m.id,
                 action=f"status_{body.status}", before=before, after=audit.snapshot(m))
    db.commit()
    return {"membership_id": m.id, "user_id": user_id, "status": m.status}


# ---------- role registry and labels ----------

@router.get("/org/roles")
def list_roles(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    settings = get_org_settings(db, ctx.org_id)
    labels = role_labels(settings.get("role_labels"))
    counts = dict(db.execute(select(RoleAssignment.role_code, func.count()).where(
        RoleAssignment.org_id == ctx.org_id, RoleAssignment.is_active.is_(True))
        .group_by(RoleAssignment.role_code)).all())
    return [{"code": code, "default_label": meta["label"], "label": labels[code], "scope": meta["scope"],
             "purpose": meta["purpose"], "is_responsibility": code in RESPONSIBILITY_TYPES,
             "project_assignable": code in PROJECT_ROLES, "active_grants": counts.get(code, 0)}
            for code, meta in ROLE_REGISTRY.items()]


@router.patch("/org/roles/labels")
def patch_labels(body: RoleLabelsPatch, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    """Display titles only. Unknown codes are rejected; codes themselves can never be renamed."""
    unknown = set(body.labels) - set(ROLE_REGISTRY)
    if unknown:
        raise HTTPException(422, f"Unknown role codes: {', '.join(sorted(unknown))}")
    clean = {k: v.strip()[:80] for k, v in body.labels.items() if v.strip()}
    row = db.execute(select(Setting).where(Setting.org_id == ctx.org_id, Setting.key == "role_labels")
                     ).scalar_one_or_none()
    before = row.value if row else {}
    if row is None:
        db.add(Setting(org_id=ctx.org_id, key="role_labels", value=clean))
    else:
        row.value = clean
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="settings", entity_id=ctx.org_id,
                 action="role_labels_updated", before={"role_labels": before}, after={"role_labels": clean})
    db.commit()
    return list_roles(ctx, db)


# ---------- role assignments ----------

@router.get("/org/role-assignments")
def list_assignments(user_id: str | None = None, include_inactive: int = 0,
                     ctx: Ctx = Depends(require_roles("org_admin", "pmo_coordinator")), db: Session = Depends(get_db)):
    q = scoped(RoleAssignment, ctx)
    if user_id:
        q = q.where(RoleAssignment.user_id == user_id)
    if not include_inactive:
        q = q.where(RoleAssignment.is_active.is_(True))
    lk = ser.Lookup(db, ctx.org_id)
    return [grant_out(g, lk, db) for g in db.execute(q.order_by(RoleAssignment.created_at)).scalars()]


@router.post("/org/role-assignments", status_code=201)
def create_assignment(body: RoleAssignmentCreate, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    g = _create_grant(db, ctx, user_id=body.user_id, role_code=body.role_code, scope_type=body.scope_type,
                      scope_id=body.scope_id, default_for_cases=body.default_for_cases, valid_from=body.valid_from,
                      valid_until=body.valid_until)
    if g.default_for_cases:
        _recompute_project(db, ctx.org_id, g.scope_id)
    db.commit()
    return grant_out(g, ser.Lookup(db, ctx.org_id), db)


@router.patch("/org/role-assignments/{assignment_id}")
def patch_assignment(assignment_id: str, body: RoleAssignmentPatch, ctx: Ctx = Depends(ADMIN),
                     db: Session = Depends(get_db)):
    g = get_scoped(db, RoleAssignment, ctx, assignment_id)
    return _patch_grant(db, ctx, g, body)


def _patch_grant(db: Session, ctx: Ctx, g: RoleAssignment, body: RoleAssignmentPatch) -> dict:
    if not g.is_active:
        raise HTTPException(409, "A revoked assignment cannot be changed; grant a new one")
    if g.user_id == ctx.user_id:
        raise HTTPException(403, "You cannot change your own role assignment")
    before = audit.snapshot(g)
    changes = body.model_fields_set
    if "default_for_cases" in changes and body.default_for_cases is not None and \
            body.default_for_cases != g.default_for_cases:
        if body.default_for_cases:
            if g.scope_type != "project" or g.role_code not in RESPONSIBILITY_TYPES:
                raise HTTPException(422, "Only a project-scoped responsibility role can be the project default")
            clash = db.execute(scoped(RoleAssignment, ctx).where(
                RoleAssignment.scope_type == "project", RoleAssignment.scope_id == g.scope_id,
                RoleAssignment.role_code == g.role_code, RoleAssignment.default_for_cases.is_(True),
                RoleAssignment.is_active.is_(True), RoleAssignment.id != g.id)).scalar_one_or_none()
            if clash is not None:
                raise HTTPException(409, "This project already has a default for that responsibility; clear it first")
        g.default_for_cases = body.default_for_cases
    if "valid_from" in changes:
        g.valid_from = body.valid_from
    if "valid_until" in changes:
        g.valid_until = body.valid_until
    db.flush()
    audit.record(db, org_id=ctx.org_id, actor_user_id=ctx.user_id, entity="role_assignment", entity_id=g.id,
                 action="updated", before=before, after=audit.snapshot(g))
    if g.scope_type == "project":
        _recompute_project(db, ctx.org_id, g.scope_id)
    db.commit()
    return grant_out(g, ser.Lookup(db, ctx.org_id), db)


@router.delete("/org/role-assignments/{assignment_id}")
def revoke_assignment(assignment_id: str, ctx: Ctx = Depends(ADMIN), db: Session = Depends(get_db)):
    g = get_scoped(db, RoleAssignment, ctx, assignment_id)
    _revoke(db, ctx, g)
    if g.scope_type == "project":
        _recompute_project(db, ctx.org_id, g.scope_id)
    db.commit()
    return grant_out(g, ser.Lookup(db, ctx.org_id), db)


# ---------- projects and project teams ----------

def _visible_project_ids(db: Session, ctx: Ctx) -> set[str]:
    if sees_all(ctx):
        return set(db.execute(scoped(Project, ctx).with_only_columns(Project.id)).scalars())
    ids = set(ctx.project_ids())
    ids |= {c.project_id for c in db.execute(visible_cases(ctx)).scalars() if c.project_id}
    return ids


def _load_project(db: Session, ctx: Ctx, project_id: str) -> Project:
    p = get_scoped(db, Project, ctx, project_id)
    if p.id not in _visible_project_ids(db, ctx):
        raise HTTPException(404, "Not found")
    return p


def _team(db: Session, ctx: Ctx, p: Project, lk: ser.Lookup, include_inactive: bool = False) -> list[dict]:
    q = scoped(RoleAssignment, ctx).where(RoleAssignment.scope_type == "project", RoleAssignment.scope_id == p.id)
    if not include_inactive:
        q = q.where(RoleAssignment.is_active.is_(True))
    return [grant_out(g, lk, db) for g in db.execute(q.order_by(RoleAssignment.created_at)).scalars()]


@router.get("/projects")
def list_projects(ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    lk = ser.Lookup(db, ctx.org_id)
    ids = _visible_project_ids(db, ctx)
    rows = case_rows(db, ctx, "all")
    required = [t for t in (lk.settings.get("required_responsibilities") or [])]
    out = []
    for p in sorted((lk.projects[i] for i in ids if i in lk.projects), key=lambda p: p.name):
        prs = [r for r in rows if r["project"] == p.name]
        team = _team(db, ctx, p, lk)
        defaults = {g["role_code"] for g in team if g["default_for_cases"]}
        out.append({
            "id": p.id, "name": p.name, "code": p.code, "case_count": len(prs),
            "at_risk": sum(1 for r in prs if any(x["severity"] in ("high", "medium") for x in r["reasons"])),
            "cases_with_gaps": sum(1 for r in prs if r["ownership_gaps"]),
            "team_size": len({g["user"]["id"] for g in team if g["user"]}),
            "missing_defaults": [t for t in required if t not in defaults and t != "line_manager"],
            "my_roles": sorted({g.role for g in ctx.grants if g.scope_type == "project" and g.scope_id == p.id}),
        })
    return out


@router.get("/projects/{project_id}")
def get_project(project_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    p = _load_project(db, ctx, project_id)
    lk = ser.Lookup(db, ctx.org_id)
    policy = Policy(db, ctx)
    from ..models import KnowledgeRef
    knowledge = db.execute(scoped(KnowledgeRef, ctx).where(KnowledgeRef.project_id == p.id)).scalars().all()
    can_manage = policy.can_manage_project_team(p.id)
    return {
        "project": {"id": p.id, "name": p.name, "code": p.code},
        "team": _team(db, ctx, p, lk),
        "history": [g for g in _team(db, ctx, p, lk, include_inactive=True) if not g["is_active"]],
        "cases": [r for r in case_rows(db, ctx, "all") if r["project"] == p.name],
        "knowledge": [ser.knowledge_out(k, lk, policy.today) for k in knowledge],
        "permissions": {
            "can_manage_team": can_manage,
            "is_admin": "org_admin" in ctx.org_roles,
            "reason": None if can_manage else "You can view this project but cannot change its role assignments.",
        },
        "eligible": _eligible(db, ctx, lk) if can_manage else {},
    }


def _eligible(db: Session, ctx: Ctx, lk: ser.Lookup) -> dict[str, list[dict]]:
    """Who may be added to a roster per role: admins may add any active member; others only people who already
    hold that role in the organization."""
    admin = "org_admin" in ctx.org_roles
    org_holders: dict[str, set[str]] = {}
    for g in db.execute(scoped(RoleAssignment, ctx).where(RoleAssignment.is_active.is_(True),
                                                          RoleAssignment.scope_type == "organization")).scalars():
        org_holders.setdefault(g.role_code, set()).add(g.user_id)
    active = [u for uid, u in lk.users.items() if lk.status[uid] == "active" and uid != ctx.user_id]
    return {code: [lk.user_ref(u.id) for u in sorted(active, key=lambda u: u.name)
                   if admin or u.id in org_holders.get(code, set())] for code in PROJECT_ROLES}


@router.get("/projects/{project_id}/assignments")
def project_assignments(project_id: str, ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    p = _load_project(db, ctx, project_id)
    return _team(db, ctx, p, ser.Lookup(db, ctx.org_id))


@router.post("/projects/{project_id}/assignments", status_code=201)
def add_project_assignment(project_id: str, body: ProjectAssignmentCreate, ctx: Ctx = Depends(get_ctx),
                           db: Session = Depends(get_db)):
    p = _load_project(db, ctx, project_id)
    policy = Policy(db, ctx)
    if not policy.can_manage_project_team(p.id):
        raise HTTPException(403, "You can view this project but cannot change its role assignments")
    if body.role_code not in PROJECT_ROLES:
        raise HTTPException(422, "This role cannot be granted on a project")
    if "org_admin" not in ctx.org_roles:
        holds = db.execute(scoped(RoleAssignment, ctx).where(
            RoleAssignment.user_id == body.user_id, RoleAssignment.role_code == body.role_code,
            RoleAssignment.scope_type == "organization", RoleAssignment.is_active.is_(True))).first()
        if holds is None:
            raise HTTPException(422, "This person does not hold that role in the organization; ask an admin")
        if body.role_code == "project_manager" and not policy.is_coordinator():
            raise HTTPException(403, "Only the PMO or an admin can add a project manager")
    g = _create_grant(db, ctx, user_id=body.user_id, role_code=body.role_code, scope_type="project",
                      scope_id=p.id, default_for_cases=body.default_for_cases)
    if g.default_for_cases:
        _recompute_project(db, ctx.org_id, p.id)
    db.commit()
    return grant_out(g, ser.Lookup(db, ctx.org_id), db)


def _project_grant(db: Session, ctx: Ctx, project_id: str, assignment_id: str) -> RoleAssignment:
    p = _load_project(db, ctx, project_id)
    if not Policy(db, ctx).can_manage_project_team(p.id):
        raise HTTPException(403, "You can view this project but cannot change its role assignments")
    g = get_scoped(db, RoleAssignment, ctx, assignment_id)
    if g.scope_type != "project" or g.scope_id != p.id:
        raise HTTPException(404, "Not found")
    if g.role_code == "project_manager" and not Policy(db, ctx).is_coordinator():
        raise HTTPException(403, "Only the PMO or an admin can change a project manager assignment")
    return g


@router.patch("/projects/{project_id}/assignments/{assignment_id}")
def patch_project_assignment(project_id: str, assignment_id: str, body: RoleAssignmentPatch,
                             ctx: Ctx = Depends(get_ctx), db: Session = Depends(get_db)):
    return _patch_grant(db, ctx, _project_grant(db, ctx, project_id, assignment_id), body)


@router.delete("/projects/{project_id}/assignments/{assignment_id}")
def remove_project_assignment(project_id: str, assignment_id: str, ctx: Ctx = Depends(get_ctx),
                              db: Session = Depends(get_db)):
    g = _project_grant(db, ctx, project_id, assignment_id)
    _revoke(db, ctx, g)
    _recompute_project(db, ctx.org_id, g.scope_id)
    db.commit()
    return grant_out(g, ser.Lookup(db, ctx.org_id), db)
