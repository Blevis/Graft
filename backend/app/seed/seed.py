"""Load data/seed.json into the demo org "Engineering Albania (demo)" plus a small "Sandbox Co" org.

    python -m app.seed.seed           # idempotent: seeds only if the demo org does not exist
    python -m app.seed.seed --reset   # explicit: wipes BOTH demo orgs (incl. human records) and re-seeds

Startup never deletes human records. People are fictional."""
import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..ai.pipeline import analyze_source
from ..db import SessionLocal
from ..models import (
    DEFAULT_SETTINGS, AgentProposal, AgentRun, AgentStep, AIGuidanceVersion, AccessItem, AnalysisRun, AuditEvent,
    CaseRequirement, CaseResponsibility, Claim, EmployeeCase, TaskAssignment, TaskPause, WorkflowTemplate, Finding, KnowledgeRef, Membership, Notification, Org, Project,
    RejectedCandidate, Review, RoleAssignment, Setting, Source, Task, TrainingEntry, User, UserPreference,
)
from ..models._base import utcnow
from ..config import get_settings
from ..services import audit
from ..services.passwords import demo_email, demo_password_hash, verify_password
from ..services.rules import recompute_case
from ..services.workflow import MOVEMENT_TEMPLATE, apply_template, current_template

DATA = Path(__file__).resolve().parents[3] / "data" / "seed.json"
DEMO_SLUG, SANDBOX_SLUG = "engineering-albania-demo", "sandbox-co"

# Fictional demo identities (email + the shared demo password; see services/passwords.py).
# Line managers come from the tracker's Manager column.
# Roles are granted separately from membership: (role, scope) where scope is "org", a project name, or a case ref.
DEMO_DOMAIN = "demo.graft.example"  # reserved .example domains: these addresses can never reach a real inbox
SANDBOX_DOMAIN = "sandbox.graft.example"
PEOPLE = [
    # key, name, title, org-scoped roles
    ("admin", "Dren Basha", "Workspace admin (demo account)", ["org_admin"]),
    ("coord", "Elira Dervishi", "PMO Coordinator", ["pmo_coordinator"]),
    ("tl_orion", "Ardit Kola", "Technical Lead · Orion, Aurora, Atlas", ["technical_owner", "training_responsible"]),
    ("tl_nimbus", "Nadia Ferri", "Technical Lead · Nimbus, Helios, Nova, Pulse, Vega", ["technical_owner"]),
    ("lm_luca", "Luca Gray", "Line Manager · Orion", ["line_manager", "project_member"]),
    ("emp_eva", "Eva Stone", "Employee · ONB-005", ["employee"]),
    ("emp_leo", "Leo Marin", "Employee · ONB-002", ["employee"]),
    ("mgmt", "Mira Shehu", "Head of Delivery (management)", ["management_viewer"]),
    ("pm", "Klea Hoxha", "Project Lead · Orion, Atlas (client contact)", ["project_manager"]),
    ("trainer", "Besa Leka", "Training Lead · Aurora, Nimbus", ["training_responsible"]),
    ("hr", "Teuta Gjoni", "HR Business Partner", ["hr_business_partner"]),
    ("access", "Gent Morina", "Access Coordinator", ["access_responsible"]),
    ("member", "Erion Daci", "Project Contributor · Orion", ["project_member"]),
    ("auditor", "Ilir Prifti", "Internal Auditor", ["auditor"]),
]
# Project rosters: (person, role, project, default for the project's cases)
PROJECT_TEAM = [
    ("tl_orion", "technical_owner", "Orion", True), ("tl_orion", "training_responsible", "Orion", True),
    ("tl_orion", "technical_owner", "Aurora", True), ("tl_orion", "technical_owner", "Atlas", True),
    ("tl_nimbus", "technical_owner", "Nimbus", True), ("tl_nimbus", "technical_owner", "Helios", True),
    ("tl_nimbus", "technical_owner", "Nova", True), ("tl_nimbus", "technical_owner", "Pulse", True),
    ("tl_nimbus", "technical_owner", "Vega", True),
    ("pm", "project_manager", "Orion", True), ("pm", "project_manager", "Atlas", True),
    ("trainer", "training_responsible", "Aurora", True), ("trainer", "training_responsible", "Nimbus", True),
    ("member", "project_member", "Orion", False), ("lm_luca", "project_member", "Orion", False),
]
# Case-level responsibilities: (case, type, person, notes). ONB-001's training owner overrides the Aurora default.
CASE_RESPONSIBILITIES = [
    ("ONB-005", "line_manager", "lm_luca", None),
    ("ONB-002", "access_responsible", "access", "Coordinates Leo's VPN, Orion Portal and Helix requests."),
    ("ONB-002", "hr_business_partner", "hr", None),
    ("ONB-005", "hr_business_partner", "hr", None),
    ("ONB-001", "training_responsible", "tl_orion", "Ardit runs the Aurora shadowing sessions himself."),
]
PROJECT_CODES = {"Nimbus": "NIM-482"}  # from E1; other codes are not in the starter pack
# Evidence -> case binding by the organiser's identifying details (employee named in the title).
EVIDENCE_CASE = {"E1": "ONB-002", "E2": "ONB-002", "E3": "ONB-005", "E4": "ONB-005", "E5": "ONB-009",
                 "E6": "ONB-010", "E7": "ONB-007"}
EVIDENCE_PROJECT = {"E8": "Atlas"}
KIND = {"Email": "email", "Update": "update"}


def _d(s: str | None, fmt: str) -> date | None:
    return datetime.strptime(s, fmt).date() if s else None


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def wipe(db: Session, slugs: tuple[str, ...]) -> None:
    org_ids = [o.id for o in db.execute(select(Org).where(Org.slug.in_(slugs))).scalars()]
    if not org_ids:
        return
    for model in (Notification, AuditEvent, AgentProposal, AgentStep, AgentRun, TrainingEntry, CaseResponsibility,
                  TaskPause, TaskAssignment, Review, Task, CaseRequirement, Finding, Claim, RejectedCandidate,
                  AnalysisRun, KnowledgeRef, AccessItem):
        db.execute(delete(model).where(model.org_id.in_(org_ids)))
    # Sources reference each other (supersedes_id): delete newest versions first.
    while True:
        superseded = select(Source.supersedes_id).where(Source.supersedes_id.is_not(None))
        leaves = select(Source.id).where(Source.org_id.in_(org_ids), Source.id.not_in(superseded))
        n = db.execute(delete(Source).where(Source.id.in_(leaves))).rowcount
        if not n:
            break
    user_ids = [m.user_id for m in db.execute(select(Membership).where(Membership.org_id.in_(org_ids))).scalars()]
    for model in (RoleAssignment, UserPreference, AIGuidanceVersion, EmployeeCase, WorkflowTemplate, Project, Setting,
                  Membership):
        db.execute(delete(model).where(model.org_id.in_(org_ids)))
    db.execute(delete(Org).where(Org.id.in_(org_ids)))
    db.flush()
    still_used = select(Membership.user_id)
    db.execute(delete(User).where(User.id.in_(user_ids), User.id.not_in(still_used)))
    db.flush()


def seed_demo(db: Session) -> Org:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    org = Org(name="Engineering Albania (demo)", slug=DEMO_SLUG, is_demo=True)
    db.add(org)
    db.flush()
    for k, v in {**DEFAULT_SETTINGS, "as_of_date": data["as_of_date"]}.items():
        db.add(Setting(org_id=org.id, key=k, value=v))

    users: dict[str, User] = {}
    for key, name, title, roles in PEOPLE:
        u = User(name=name, title=title, email=demo_email(name, DEMO_DOMAIN), password_hash=_demo_hash())
        db.add(u)
        db.flush()
        db.add(Membership(org_id=org.id, user_id=u.id, status="active"))
        for role in roles:
            db.add(RoleAssignment(org_id=org.id, user_id=u.id, role_code=role, scope_type="organization"))
        users[key] = u

    projects: dict[str, Project] = {}
    for row in data["cases"]:
        name = row["project"]
        if name and name not in projects:
            projects[name] = Project(org_id=org.id, name=name, code=PROJECT_CODES.get(name))
    for name in EVIDENCE_PROJECT.values():
        projects.setdefault(name, Project(org_id=org.id, name=name))
    db.add_all(projects.values())
    db.flush()
    for key, role, project, default in PROJECT_TEAM:
        db.add(RoleAssignment(org_id=org.id, user_id=users[key].id, role_code=role, scope_type="project",
                              scope_id=projects[project].id, default_for_cases=default,
                              assigned_by_user_id=users["admin"].id))

    employees = {"Eva Stone": users["emp_eva"], "Leo Marin": users["emp_leo"]}
    cases: dict[str, EmployeeCase] = {}
    for row in data["cases"]:
        start = _d(row["start"], "%d-%b-%y")
        last = _d(f"{row['last_update']}-{start.year}", "%d-%b-%Y") if row["last_update"] else None
        p = projects.get(row["project"]) if row["project"] else None
        c = EmployeeCase(
            org_id=org.id, ref=row["case"], employee=row["employee"],
            employee_user_id=employees[row["employee"]].id if row["employee"] in employees else None,
            movement={"New Hire": "new_hire", "Reallocation": "reallocation"}.get(row["movement"]),
            start_date=start, project_id=p.id if p else None, manager_name=row["manager"],
            tracker_status=row["status"], tracker_updated_at=last,
        )
        db.add(c)
        cases[row["case"]] = c
    db.flush()
    # Every seeded case gets its template's requirements (no tasks: the demo starts with an empty task list).
    for c in cases.values():
        apply_template(db, c, current_template(db, org.id, MOVEMENT_TEMPLATE.get(c.movement or "", "new_hire")),
                       actor_user_id=None, create_tasks=False)
    for ref, rtype, key, notes in CASE_RESPONSIBILITIES:
        case = cases[ref]
        inherited = any(t[2] == next((n for n, pr in projects.items() if pr.id == case.project_id), None)
                        and t[1] == rtype and t[3] for t in PROJECT_TEAM)
        db.add(CaseResponsibility(org_id=org.id, case_id=case.id, user_id=users[key].id, responsibility_type=rtype,
                                  is_primary=True, source="case_override" if inherited else "manual",
                                  assigned_by_user_id=users["coord"].id, assigned_at=utcnow(), notes=notes))
    db.flush()

    sources: dict[str, Source] = {}
    for e in data["evidence"]:
        case = cases.get(EVIDENCE_CASE.get(e["id"], ""))
        project = projects.get(EVIDENCE_PROJECT.get(e["id"], ""))
        src_date = _d(e["date"], "%d %b %Y")
        if src_date is None and e["header"] and "Last tracker update:" in e["header"]:
            src_date = _d(e["header"].split("Last tracker update:")[1].split("|")[0].strip(), "%d %b %Y")
        s = Source(
            org_id=org.id, ref=e["id"], kind="tracker_note" if e["header"] else KIND[e["type"]],
            title=e["title"], case_id=case.id if case else None,
            project_id=(project.id if project else (case.project_id if case else None)),
            author_role=e["from"], recipient_role=e["to"], date=src_date, header=e["header"], body=e["body"],
            body_sha256=_sha(e["body"]), version=1, ingested_via="seed",
        )
        db.add(s)
        sources[e["id"]] = s
    db.flush()

    # Leo's access items, as reported in E1 (requested 07 Oct) and E2 (latest dated status, 14 Oct).
    leo = cases["ONB-002"]
    for system, state in (("Nova VPN", "active"), ("Orion Portal", "awaiting_approval"),
                          ("Helix Service Desk", "not_provisioned")):
        db.add(AccessItem(org_id=org.id, case_id=leo.id, system=system, state=state,
                          requested_at=date(2026, 10, 7), owner_role="Access Support",
                          evidence_source_ids=[sources["E1"].id, sources["E2"].id]))

    # E8: Atlas documentation. Store the folder reference only.
    db.add(KnowledgeRef(org_id=org.id, project_id=projects["Atlas"].id, title="Training guide and runbook",
                        location="/Team/Operations/Onboarding", owner_role="KT Owner",
                        last_verified=date(2026, 10, 11), source_id=sources["E8"].id, topic="kt_activity",
                        description="Atlas training guide and runbook, kept in the project's own folder (E8).",
                        applies_to_roles=["technical_owner", "training_responsible", "employee"],
                        tags=["atlas", "runbook", "training"]))

    # Seed analysis replays committed recorded examples only (deterministic, no API spend).
    for s in sources.values():
        analyze_source(db, s, ai_enabled=True, allow_live=False)
    db.flush()
    for c in cases.values():
        recompute_case(db, c)

    audit.record(db, org_id=org.id, actor_user_id=None, entity="org", entity_id=org.id, action="seeded",
                 after={"cases": len(cases), "sources": len(sources)})
    return org


def seed_sandbox(db: Session) -> Org:
    """A second tenant, so cross-org isolation is visible and testable."""
    org = Org(name="Sandbox Co", slug=SANDBOX_SLUG, is_demo=True)
    db.add(org)
    db.flush()
    for k, v in DEFAULT_SETTINGS.items():
        db.add(Setting(org_id=org.id, key=k, value=v))
    admin = User(name="Sam Rivera", title="Sandbox admin", email=demo_email("Sam Rivera", SANDBOX_DOMAIN),
                 password_hash=_demo_hash())
    db.add(admin)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=admin.id, status="active"))
    project = Project(org_id=org.id, name="Pilot")
    db.add(project)
    db.flush()
    for role, scope_type, scope_id, default in (("org_admin", "organization", None, False),
                                               ("technical_owner", "organization", None, False),
                                               ("technical_owner", "project", project.id, True)):
        db.add(RoleAssignment(org_id=org.id, user_id=admin.id, role_code=role, scope_type=scope_type,
                              scope_id=scope_id, default_for_cases=default))
    case = EmployeeCase(org_id=org.id, ref="SBX-001", employee="Jordan Lee", movement="new_hire",
                        start_date=date(2026, 10, 1), project_id=project.id, manager_name=None,
                        tracker_status="On Track", tracker_updated_at=date(2026, 10, 12))
    db.add(case)
    db.flush()
    apply_template(db, case, current_template(db, org.id, "new_hire"), actor_user_id=None, create_tasks=False)
    recompute_case(db, case)
    audit.record(db, org_id=org.id, actor_user_id=None, entity="org", entity_id=org.id, action="seeded")
    return org


def _demo_hash() -> str:
    return demo_password_hash(get_settings().DEMO_PASSWORD)


def ensure_demo_credentials(db: Session) -> int:
    """Give every member of a demo organisation an email and the current demo password (idempotent). Databases seeded
    before password sign-in existed, and members an admin added to a demo org, become able to sign in."""
    rows = db.execute(select(User, Org).join(Membership, Membership.user_id == User.id)
                      .join(Org, Org.id == Membership.org_id).where(Org.is_demo.is_(True))).all()
    password = get_settings().DEMO_PASSWORD
    taken = {u.email.lower() for u, _ in rows if u.email}
    changed = 0
    for u, org in rows:
        if not u.email:
            base = demo_email(u.name, SANDBOX_DOMAIN if org.slug == SANDBOX_SLUG else DEMO_DOMAIN)
            email, n = base, 2
            while email in taken:
                local, domain = base.split("@")
                email, n = f"{local}{n}@{domain}", n + 1
            u.email = email
            taken.add(email)
            changed += 1
        if u.password_hash != _demo_hash() and not verify_password(password, u.password_hash):
            u.password_hash = _demo_hash()
            changed += 1
    return changed


def run(reset: bool = False) -> str:
    with SessionLocal() as db:
        exists = db.execute(select(Org).where(Org.slug == DEMO_SLUG)).scalar_one_or_none()
        if exists and not reset:
            changed = ensure_demo_credentials(db)
            db.commit()
            return (f"Demo org already present; {changed} demo credential update(s) (use --reset to rebuild)."
                    + _showcase(db))
        if reset:
            wipe(db, (DEMO_SLUG, SANDBOX_SLUG))
        seed_demo(db)
        seed_sandbox(db)
        db.commit()
        return "Seeded Engineering Albania (demo) and Sandbox Co." + _showcase(db)


def _showcase(db: Session) -> str:
    """Add data/showcase.json to the demo org once (SEED_SHOWCASE, on by default). A failure never blocks start-up:
    the starter pack is already committed and the reason is reported."""
    from . import showcase
    if not get_settings().SEED_SHOWCASE:
        return ""
    org = db.execute(select(Org).where(Org.slug == DEMO_SLUG)).scalar_one_or_none()
    if org is None or showcase.present(db, org):
        return ""
    try:
        return " " + showcase.run(db, org, DEMO_DOMAIN)
    except Exception as exc:  # noqa: BLE001 - report, never crash the container on demo data
        db.rollback()
        return f" Showcase not loaded: {exc}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe the demo orgs (including human records) first")
    print(run(reset=ap.parse_args().reset))
