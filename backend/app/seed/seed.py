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
    DEFAULT_SETTINGS, AccessItem, AnalysisRun, AuditEvent, Claim, EmployeeCase, Finding, KnowledgeRef, Membership,
    Notification, Org, Project, RejectedCandidate, Review, Setting, Source, Task, User,
)
from ..services import audit
from ..services.rules import recompute_case

DATA = Path(__file__).resolve().parents[3] / "data" / "seed.json"
DEMO_SLUG, SANDBOX_SLUG = "engineering-albania-demo", "sandbox-co"

# Fictional demo identities. Line managers come from the tracker's Manager column.
PEOPLE = [
    # key, name, title, role
    ("admin", "Dren Basha", "Platform admin", "admin"),
    ("coord", "Elira Dervishi", "PMO Coordinator", "pmo_coordinator"),
    ("tl_orion", "Ardit Kola", "Technical Lead · Orion, Aurora, Atlas", "technical_owner"),
    ("tl_nimbus", "Nadia Ferri", "Technical Lead · Nimbus, Helios, Nova, Pulse, Vega", "technical_owner"),
    ("lm_luca", "Luca Gray", "Line Manager · Orion", "line_manager"),
    ("emp_eva", "Eva Stone", "Employee · ONB-005", "employee"),
    ("emp_leo", "Leo Marin", "Employee · ONB-002", "employee"),
    ("mgmt", "Mira Shehu", "Head of Delivery (management)", "viewer"),
]
PROJECT_OWNER = {"Orion": "tl_orion", "Aurora": "tl_orion", "Atlas": "tl_orion", "Nimbus": "tl_nimbus",
                 "Helios": "tl_nimbus", "Nova": "tl_nimbus", "Pulse": "tl_nimbus", "Vega": "tl_nimbus"}
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
    for model in (Notification, AuditEvent, Review, Task, Finding, Claim, RejectedCandidate, AnalysisRun,
                  KnowledgeRef, AccessItem):
        db.execute(delete(model).where(model.org_id.in_(org_ids)))
    # Sources reference each other (supersedes_id): delete newest versions first.
    while True:
        superseded = select(Source.supersedes_id).where(Source.supersedes_id.is_not(None))
        leaves = select(Source.id).where(Source.org_id.in_(org_ids), Source.id.not_in(superseded))
        n = db.execute(delete(Source).where(Source.id.in_(leaves))).rowcount
        if not n:
            break
    user_ids = [m.user_id for m in db.execute(select(Membership).where(Membership.org_id.in_(org_ids))).scalars()]
    for model in (EmployeeCase, Project, Setting, Membership):
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
    for key, name, title, role in PEOPLE:
        u = User(name=name, title=title)
        db.add(u)
        db.flush()
        db.add(Membership(org_id=org.id, user_id=u.id, role=role))
        users[key] = u

    projects: dict[str, Project] = {}
    for row in data["cases"]:
        name = row["project"]
        if name and name not in projects:
            projects[name] = Project(org_id=org.id, name=name, code=PROJECT_CODES.get(name),
                                     tech_owner_user_id=users[PROJECT_OWNER[name]].id)
    for name in EVIDENCE_PROJECT.values():
        projects.setdefault(name, Project(org_id=org.id, name=name, tech_owner_user_id=users[PROJECT_OWNER[name]].id))
    db.add_all(projects.values())
    db.flush()

    employees = {"Eva Stone": users["emp_eva"], "Leo Marin": users["emp_leo"]}
    managers = {"Luca Gray": users["lm_luca"]}
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
            line_manager_user_id=managers[row["manager"]].id if row["manager"] in managers else None,
            tracker_status=row["status"], tracker_updated_at=last,
            tech_owner_user_id=p.tech_owner_user_id if p else None,
        )
        db.add(c)
        cases[row["case"]] = c
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
                        last_verified=date(2026, 10, 11), source_id=sources["E8"].id))

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
    admin = User(name="Sam Rivera", title="Sandbox admin")
    db.add(admin)
    db.flush()
    db.add(Membership(org_id=org.id, user_id=admin.id, role="admin"))
    project = Project(org_id=org.id, name="Pilot", tech_owner_user_id=admin.id)
    db.add(project)
    db.flush()
    case = EmployeeCase(org_id=org.id, ref="SBX-001", employee="Jordan Lee", movement="new_hire",
                        start_date=date(2026, 10, 1), project_id=project.id, manager_name=None,
                        tracker_status="On Track", tracker_updated_at=date(2026, 10, 12),
                        tech_owner_user_id=admin.id)
    db.add(case)
    db.flush()
    recompute_case(db, case)
    audit.record(db, org_id=org.id, actor_user_id=None, entity="org", entity_id=org.id, action="seeded")
    return org


def run(reset: bool = False) -> str:
    with SessionLocal() as db:
        exists = db.execute(select(Org).where(Org.slug == DEMO_SLUG)).scalar_one_or_none()
        if exists and not reset:
            return "Demo org already present; nothing to do (use --reset to rebuild)."
        if reset:
            wipe(db, (DEMO_SLUG, SANDBOX_SLUG))
        seed_demo(db)
        seed_sandbox(db)
        db.commit()
        return "Seeded Engineering Albania (demo) and Sandbox Co."


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe the demo orgs (including human records) first")
    print(run(reset=ap.parse_args().reset))
