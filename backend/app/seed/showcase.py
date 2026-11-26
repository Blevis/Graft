"""Showcase data: Graft's demo org as it looks mid-quarter (data/showcase.json).

Two phases:
1. Base records the API has no route for, or that come from outside (the tracker, evidence already received):
   people, a project, knowledge links, cases with their tracker fields, access items, sources. Sources are analysed
   from their recorded extractions (ai/recorded.py) through the normal verifier.
2. Activity, replayed through the real HTTP API as the fictional people who would do it (password sign-in, CSRF):
   tasks, claims, pauses, reassignments, access tests, training, reviews and a final sign-off, an HR document upload,
   inbox mail, new cases and PMO AI guidance. Permissions, audit events, notifications and timelines are therefore
   exactly what the product produces.

The starter-pack cases (ONB-001 to ONB-010, including Eva's) are never touched, so the hero walk-through starts clean.
Idempotent: skipped when ONB-011 already exists. Disable with SEED_SHOWCASE=false."""
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import DateTime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.pipeline import analyze_source
from ..config import get_settings
from ..models import (AccessItem, CaseResponsibility, EmployeeCase, KnowledgeRef, Membership, Org, Project,
                      RoleAssignment, Source, User)
from ..models._base import utcnow
from ..services import audit
from ..services.passwords import demo_email, demo_password_hash
from ..services.rules import recompute_case
from ..services.workflow import MOVEMENT_TEMPLATE, apply_template, current_template

DATA = Path(__file__).resolve().parents[3] / "data" / "showcase.json"
FIRST_REF = "ONB-011"
CHAPTER2_REF = "ONB-025"


class ShowcaseError(RuntimeError):
    pass


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def present(db: Session, org: Org, ref: str = FIRST_REF) -> bool:
    return db.execute(select(EmployeeCase.id).where(EmployeeCase.org_id == org.id,
                                                    EmployeeCase.ref == ref)).first() is not None


def complete(db: Session, org: Org) -> bool:
    return present(db, org) and present(db, org, CHAPTER2_REF)


# ---------- phase 1: base records ----------

def _people(db: Session, org: Org, data: dict, domain: str) -> dict[str, User]:
    from .seed import PEOPLE  # starter-pack people, by key
    users: dict[str, User] = {}
    by_name = {u.name: u for u in db.execute(
        select(User).join(Membership, Membership.user_id == User.id).where(Membership.org_id == org.id)).scalars()}
    for key, name, _, _ in PEOPLE:
        users[key] = by_name[name]
    password = demo_password_hash(get_settings().DEMO_PASSWORD)
    for p in data["people"]:
        if p["name"] in by_name:  # created by an earlier chapter
            users[p["key"]] = by_name[p["name"]]
            continue
        u = User(name=p["name"], title=p["title"], email=demo_email(p["name"], domain), password_hash=password)
        db.add(u)
        db.flush()
        db.add(Membership(org_id=org.id, user_id=u.id, status="active"))
        for role in p["roles"]:
            db.add(RoleAssignment(org_id=org.id, user_id=u.id, role_code=role, scope_type="organization"))
        users[p["key"]] = u
    db.flush()
    return users


def _base(db: Session, org: Org, data: dict, users: dict[str, User]) -> dict[str, EmployeeCase]:
    projects = {p.name: p for p in db.execute(select(Project).where(Project.org_id == org.id)).scalars()}
    for p in data["projects"]:
        proj = Project(org_id=org.id, name=p["name"], code=p.get("code"))
        db.add(proj)
        db.flush()
        projects[p["name"]] = proj
        for key, role, default in p["team"]:
            db.add(RoleAssignment(org_id=org.id, user_id=users[key].id, role_code=role, scope_type="project",
                                  scope_id=proj.id, default_for_cases=default, assigned_by_user_id=users["admin"].id))
    for k in data.get("knowledge", []):
        db.add(KnowledgeRef(org_id=org.id, project_id=projects[k["project"]].id, title=k["title"],
                            location=k["location"], owner_role=k["owner_role"],
                            last_verified=date.fromisoformat(k["last_verified"]), topic=k["topic"],
                            description=k["description"], applies_to_roles=k["applies_to_roles"], tags=k["tags"]))

    cases: dict[str, EmployeeCase] = {c.ref: c for c in db.execute(
        select(EmployeeCase).where(EmployeeCase.org_id == org.id)).scalars()}
    touched: set[str] = set()
    for c in data["cases"]:
        case = EmployeeCase(
            org_id=org.id, ref=c["ref"], employee=c["employee"],
            employee_user_id=users[c["user"]].id if c.get("user") else None, movement=c["movement"],
            start_date=date.fromisoformat(c["start"]),
            project_id=projects[c["project"]].id if c.get("project") else None, manager_name=c.get("manager"),
            tracker_status=c["tracker_status"], tracker_updated_at=date.fromisoformat(c["tracker_updated"]),
            exact_role=c.get("exact_role"),
            expected_readiness_date=date.fromisoformat(c["expected_readiness"]) if c.get("expected_readiness") else None)
        db.add(case)
        db.flush()
        cases[c["ref"]] = case
        touched.add(c["ref"])
        apply_template(db, case, current_template(db, org.id, MOVEMENT_TEMPLATE.get(case.movement, "new_hire")),
                       actor_user_id=None, create_tasks=False)
        for rtype, key in c["responsibilities"]:
            db.add(CaseResponsibility(org_id=org.id, case_id=case.id, user_id=users[key].id, responsibility_type=rtype,
                                      is_primary=True, source="manual", assigned_by_user_id=users["coord"].id,
                                      assigned_at=utcnow()))
        for system, state, requested in c["access"]:
            db.add(AccessItem(org_id=org.id, case_id=case.id, system=system, state=state,
                              requested_at=date.fromisoformat(requested), owner_role="Access Support"))
    db.flush()

    sources: dict[str, Source] = {}
    for s in data["sources"]:
        case = cases[s["case"]]
        src = Source(org_id=org.id, ref=s["ref"], kind=s["kind"], title=s["title"], case_id=case.id,
                     project_id=case.project_id, author_role=s["author_role"],
                     recipient_role=s.get("recipient_role"), date=date.fromisoformat(s["date"]), body=s["body"],
                     body_sha256=hashlib.sha256(s["body"].encode("utf-8")).hexdigest(), version=1,
                     ingested_via="seed", channel="tracker_import")
        db.add(src)
        sources[s["ref"]] = src
        touched.add(s["case"])
    db.flush()
    touched_ids = {cases[r].id for r in touched}
    for a in db.execute(select(AccessItem).where(AccessItem.org_id == org.id)).scalars():
        refs = [r for r, s in sources.items() if s.case_id == a.case_id and a.system in s.body]
        if a.case_id in touched_ids and refs:
            a.evidence_source_ids = list(dict.fromkeys((a.evidence_source_ids or []) + [sources[r].id for r in refs]))
    for src in sources.values():
        analyze_source(db, src, ai_enabled=True, allow_live=False)
    db.flush()
    for ref in touched:
        recompute_case(db, cases[ref])
    audit.record(db, org_id=org.id, actor_user_id=None, entity="org", entity_id=org.id, action="showcase_seeded",
                 after={"cases": len(touched), "sources": len(sources)})
    return cases


# ---------- phase 2: activity through the API ----------

class Actor:
    def __init__(self, app, email: str):
        from fastapi.testclient import TestClient
        self.c = TestClient(app, base_url="http://showcase.local")
        r = self.c.post("/api/auth/login", json={"email": email, "password": get_settings().DEMO_PASSWORD})
        if r.status_code != 200:
            raise ShowcaseError(f"sign-in failed for {email}: {r.text}")
        self.c.headers["X-CSRF-Token"] = self.c.cookies.get("graft_csrf")

    def _check(self, r, what):
        if r.status_code >= 300:
            raise ShowcaseError(f"{what}: {r.status_code} {r.text[:300]}")
        return r.json()

    def get(self, path):
        return self._check(self.c.get(f"/api{path}"), f"GET {path}")

    def post(self, path, body=None, **kw):
        return self._check(self.c.post(f"/api{path}", json=body, **kw), f"POST {path}")

    def patch(self, path, body):
        return self._check(self.c.patch(f"/api{path}", json=body), f"PATCH {path}")


def _activity(data: dict, users: dict[str, User]):
    from ..main import create_app
    app = create_app(static_dir="does-not-exist")
    who = {k: Actor(app, u.email) for k, u in users.items()
           if k in ("coord", "admin", "tl_orion", "tl_nimbus", "tl_lyra", "trainer", "hr", "access", "lm_luca",
                    "emp_arben", "emp_ilda")}
    elira, ardit, nadia, marko, besa = who["coord"], who["tl_orion"], who["tl_nimbus"], who["tl_lyra"], who["trainer"]
    uid = {k: u.id for k, u in users.items()}

    def detail(ref):
        return elira.get(f"/cases/{ref}")

    def src(d, ref):
        return next(s["id"] for s in d["sources"] if s["ref"] == ref)

    def access(d, system):
        return next(a["id"] for a in d["access_items"] if a["system"] == system)

    def task(ref, title, owner, due, finding=None, cited=(), sla=None):
        who_owns = {"owner_role": owner[5:]} if owner.startswith("role:") else {"owner_user_id": uid[owner]}
        body = {"title": title, **who_owns, "due_date": due, "cited_source_ids": list(cited)}
        if finding:
            body["finding_id"] = finding
        if sla:
            body["sla_hours"] = sla
        return elira.post(f"/cases/{ref}/tasks", body)["id"]

    def review(actor, ref, disposition, scope, rationale, cited, milestone=None, stage=None):
        body = {"disposition": disposition, "scope": scope, "rationale": rationale, "cited_source_ids": cited}
        if milestone:
            body["milestone_key"] = milestone
        if stage:
            body["observed_stage"] = stage
        return actor.post(f"/cases/{ref}/reviews", body)

    def training(actor, ref, kind, title, notes, day, cited=()):
        actor.post(f"/cases/{ref}/training", {"kind": kind, "title": title, "notes": notes, "activity_date": day,
                                              "cited_source_ids": list(cited)})

    # ONB-011 Arben: the full journey to final sign-off.
    d = detail("ONB-011")
    s1, s2 = src(d, "S01"), src(d, "S02")
    training(ardit, "ONB-011", "plan", "Orion support KT plan", "Product training, three shadow shifts, then "
             "supported requests; escalation scenarios observed in week 7.", "2026-08-18")
    training(ardit, "ONB-011", "session", "Escalation scenarios walkthrough", "Both escalation paths rehearsed on the "
             "staging tenant.", "2026-10-01")
    training(ardit, "ONB-011", "observation", "Observed escalation handling", "Resolved both complex escalation "
             "scenarios without help.", "2026-10-08", [s2])
    for system in ("Orion Portal", "Orion CRM"):
        who["emp_arben"].patch(f"/access-items/{access(d, system)}", {"state": "confirmed_usable"})
    t = task("ONB-011", "Record Orion runbook location in the KT checklist", "tl_orion", "2026-10-09", cited=[s2])
    ardit.patch(f"/tasks/{t}", {"status": "done"})
    review(ardit, "ONB-011", "validate_scope", "KT plan and training owner", "Plan agreed on day two; Ardit owns "
           "the Orion KT and ran every session himself.", [s1], "kt_plan")
    review(ardit, "ONB-011", "validate_scope", "Standard requests with support", "Observed in week four: standard "
           "requests handled with occasional support, as reported in S01.", [s1], "supported_execution",
           "supported_execution")
    review(ardit, "ONB-011", "validate_scope", "Complex escalation scenarios", "Both escalation scenarios observed "
           "on 8 October and resolved without help.", [s2], "complex_scenarios", "independent_execution")
    review(ardit, "ONB-011", "validate_scope", "KT documentation location", "The Orion support runbook lives in "
           "/Projects/Orion/Runbooks/Support, recorded in S02.", [s2], "kt_docs")
    review(ardit, "ONB-011", "close", "Whole onboarding", "Every required milestone is validated with cited "
           "evidence and Arben confirmed both Orion systems himself. Signing off.", [s2], stage="validated")

    # ONB-012 Sara: one scope validated, complex scenarios kept open, follow-up assigned.
    d = detail("ONB-012")
    s3 = src(d, "S03")
    training(besa, "ONB-012", "session", "Aurora product training", "Two-day product course completed.",
             "2026-09-15", [s3])
    review(ardit, "ONB-012", "validate_scope", "Standard requests with support", "Sara handles standard requests "
           "with occasional support, per the training responsible's update.", [s3], "supported_execution",
           "supported_execution")
    review(ardit, "ONB-012", "keep_open", "Complex scenarios", "Complex scenarios are not covered yet; keep the "
           "case open until they are observed.", [s3])
    task("ONB-012", "Plan coverage of the Aurora complex scenarios", "tl_orion", "2026-10-17", cited=[s3])

    # ONB-013 Ilda: access blocked; the VPN works, the console waits; an overdue chase is with the access lead.
    d = detail("ONB-013")
    who["emp_ilda"].patch(f"/access-items/{access(d, 'Nimbus VPN')}", {"state": "confirmed_usable"})
    finding = next(f["id"] for f in detail("ONB-013")["findings"] if f["rule_id"] == "ACCESS_NOT_CONFIRMED")
    task("ONB-013", "Chase the Nimbus Console approval", "access", "2026-10-10", finding, [src(d, "S04")], sla=48)

    # ONB-014 Tom: stale tracker, untested pipeline.
    d = detail("ONB-014")
    task("ONB-014", "Ask Tom to test the Helios deploy pipeline", "tl_nimbus", "2026-10-16", cited=[src(d, "S08")])

    # ONB-015 Dafina: closure conflict, claimed by the technical owner, kept open with a scope.
    d = detail("ONB-015")
    conflict = next(f["id"] for f in d["findings"] if f["rule_id"] == "CLOSURE_CONFLICT")
    # Routed to the technical-owner queue, then claimed by Nadia (queue -> owner, with history).
    t = task("ONB-015", "Observe the quarterly reconciliation scenario", "role:technical_owner", "2026-10-11", conflict,
             [src(d, "S05"), src(d, "S06")])
    nadia.post(f"/tasks/{t}/claim")
    review(nadia, "ONB-015", "keep_open", "Quarterly reconciliation scenario", "The line manager reports closure, but "
           "the reconciliation scenario is still uncovered. Keep open until it is observed.",
           [src(d, "S05"), src(d, "S06")])

    # ONB-016 Ben: unanswered request, no line manager anywhere.
    task("ONB-016", "Confirm the Vega KT owner and first session", "tl_nimbus", "2026-10-15",
         cited=[src(detail("ONB-016"), "S07")])

    # ONB-018 Omar: two scopes validated, complex scenarios kept open.
    d = detail("ONB-018")
    s9 = src(d, "S09")
    review(nadia, "ONB-018", "validate_scope", "KT plan and training owner", "Nadia owns Omar's Nova KT; plan "
           "agreed at start.", [s9], "kt_plan")
    review(nadia, "ONB-018", "validate_scope", "Standard requests", "Omar handles standard requests independently.",
           [s9], "supported_execution", "supported_execution")
    review(nadia, "ONB-018", "keep_open", "Second complex scenario", "One of two complex scenarios is covered; the "
           "second is still outstanding.", [s9])

    # ONB-019 Elsa: HR uploads a check-in document (text extracted on the server, file not kept).
    doc = data["documents"][0]
    who["hr"].post(f"/cases/{doc['case']}/documents", files={"file": (doc["filename"], doc["text"].encode("utf-8"),
                                                                       "text/plain")},
                   data={"title": doc["title"], "date": doc["date"]})
    training(marko, "ONB-019", "plan", "Lyra integration KT plan", "Shadow the integration team for two weeks, "
             "then supported deployments.", "2026-09-29")
    task("ONB-019", "Schedule a second deployment runbook session for Elsa", "tl_lyra", "2026-10-21")

    # ONB-020 Jon: client sandbox blocked; one task paused, one reassigned.
    d = detail("ONB-020")
    t = task("ONB-020", "Get client sandbox access approved", "tl_orion", "2026-10-12", cited=[src(d, "S10")])
    ardit.post(f"/tasks/{t}/pause", {"reason": "Waiting for the client's IT team"})
    t = task("ONB-020", "Book the second escalation scenario session", "tl_orion", "2026-10-20")
    elira.post(f"/tasks/{t}/reassign", {"owner_user_id": uid["lm_luca"], "reason": "Luca runs the escalation rota"})

    # ONB-021 Mia: training log from the training responsible.
    d = detail("ONB-021")
    s11 = src(d, "S11")
    training(besa, "ONB-021", "plan", "Aurora first-line KT plan", "Induction, two weeks of shadowing, then "
             "supported requests.", "2026-09-28")
    training(besa, "ONB-021", "session", "Aurora induction course", "Completed with the September cohort.",
             "2026-10-02", [s11])
    training(besa, "ONB-021", "observation", "Shadowing the first-line team", "Mia follows the triage rota and "
             "asks good questions; not yet handling requests.", "2026-10-12", [s11])

    # Inbox: one matched (analysed), one ambiguous (needs review), one unmatched.
    for item in data["inbox"]:
        elira.post("/inbox", {k: item[k] for k in ("title", "body", "author_role", "date", "kind")})

    # Two new cases created in Graft (not from the tracker), with owners and the default template.
    projects = {p["name"]: p["id"] for p in elira.get("/projects")}
    for c in data["new_cases"]:
        elira.post("/cases", {"employee": c["employee"], "movement": c["movement"], "start_date": c["start_date"],
                              "ref": c["ref"], "project_id": projects[c["project"]],
                              "technical_owner_user_id": uid[c["technical_owner"]],
                              "line_manager_user_id": uid[c["line_manager"]], "exact_role": c["exact_role"],
                              "expected_readiness_date": c["expected_readiness_date"]})

    # PMO AI guidance (versioned, presentation only).
    elira.patch("/settings/ai-guidance", data["ai_guidance"])


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _backdate(db: Session, org: Org, started: datetime, finished: datetime, as_of: date,
              days: tuple[int, int] = (3, 1)) -> None:
    """The activity ran seconds ago; the demo org lives on 14 Oct 2026. Map every timestamp a chapter wrote, in
    order, onto a window of days before the as-of date (days=(from, to), counted back from it), so timelines,
    ages and metrics read naturally and a later chapter always lands after an earlier one."""
    from ..db import Base
    start = datetime.combine(as_of - timedelta(days=days[0]), time(8, 30), tzinfo=timezone.utc)
    end = datetime.combine(as_of - timedelta(days=days[1]), time(8, 30), tzinfo=timezone.utc)
    span = max((finished - started).total_seconds(), 1.0)

    def shift(value):
        return start + (end - start) * ((_aware(value) - started).total_seconds() / span)

    for mapper in Base.registry.mappers:
        cls = mapper.class_
        table = getattr(cls, "__table__", None)
        if table is None or "org_id" not in table.c:
            continue
        cols = [c.name for c in table.c if isinstance(c.type, DateTime)]
        if not cols:
            continue
        for row in db.execute(select(cls).where(cls.org_id == org.id)).scalars():
            for name in cols:
                value = getattr(row, name)
                if value is not None and started <= _aware(value) <= finished:
                    setattr(row, name, shift(value))
    db.commit()


def _relay_credential(db: Session, org: Org) -> str:
    """A scoped service identity for the mail relay (normally created with python -m app.ops service-token)."""
    import secrets
    from ..models import ServiceCredential
    token = "grs_" + secrets.token_urlsafe(32)
    cred = ServiceCredential(org_id=org.id, name="showcase-mail-relay",
                             token_sha256=hashlib.sha256(token.encode()).hexdigest(), scopes=["inbound:write"],
                             is_active=True)
    db.add(cred)
    db.flush()
    audit.record(db, org_id=org.id, actor_user_id=None, entity="service_credential", entity_id=cred.id,
                 action="created_by_operator", after={"name": cred.name, "scopes": cred.scopes})
    return token


def _recorded_agent_run(db: Session, org: Org, spec: dict, users: dict[str, User], detail: dict) -> list[str]:
    """A recorded case-agent run (provider "recorded", like the recorded extractions), so the agent trace and the
    human handoff are visible without a model. Proposals start open; people accept or dismiss them via the API."""
    from ..ai.agent_tools import evidence_hash
    from ..models import AgentProposal, AgentRun, AgentStep
    sources = {s["ref"]: s["id"] for s in detail["sources"]}
    run = AgentRun(org_id=org.id, case_id=detail["case"]["id"], requested_by=users[spec["requested_by"]].id,
                   status="completed", assessment=spec["assessment"], model=spec["model"],
                   prompt_version=spec["prompt_version"], evidence_hash=evidence_hash(detail), provider="recorded")
    db.add(run)
    db.flush()
    for i, (tool, args, summary, ms) in enumerate(spec["steps"]):
        db.add(AgentStep(org_id=org.id, run_id=run.id, index=i, tool=tool, arguments=args, result_summary=summary,
                         duration_ms=ms))
    ids = []
    for pr in spec["proposals"]:
        row = AgentProposal(org_id=org.id, run_id=run.id, kind=pr["kind"], title=pr["title"], body=pr["body"],
                            owner_role=pr["owner_role"], owner_user_id=users[pr["owner"]].id if pr["owner"] else None,
                            due_date=date.fromisoformat(pr["due"]) if pr["due"] else None,
                            cited_source_ids=[sources[pr["cite"]]], cited_claim_ids=[], status="open")
        db.add(row)
        db.flush()
        ids.append(row.id)
    audit.record(db, org_id=org.id, actor_user_id=run.requested_by, entity="agent_run", entity_id=run.id,
                 action="completed", after={"model": run.model, "provider": "recorded", "proposals": len(ids)})
    db.commit()
    return ids


def _activity2(db: Session, org: Org, data: dict, users: dict[str, User], relay_token: str):
    from fastapi.testclient import TestClient

    from ..main import create_app
    ch = data["chapter2"]
    app = create_app(static_dir="does-not-exist")
    who = {k: Actor(app, users[k].email) for k in ("coord", "admin", "tl_orion", "tl_nimbus")}
    elira, dren, ardit, nadia = who["coord"], who["admin"], who["tl_orion"], who["tl_nimbus"]
    uid = {k: u.id for k, u in users.items()}

    def detail(ref):
        return elira.get(f"/cases/{ref}")

    def src(d, ref):
        return next(s["id"] for s in d["sources"] if s["ref"] == ref)

    def review(actor, ref, disposition, scope, rationale, cited, milestone=None, stage=None, exception=None):
        body = {"disposition": disposition, "scope": scope, "rationale": rationale, "cited_source_ids": cited}
        for key, value in (("milestone_key", milestone), ("observed_stage", stage), ("exception_reason", exception)):
            if value:
                body[key] = value
        return actor.post(f"/cases/{ref}/reviews", body)

    def task(ref, title, owner, due=None, finding=None, cited=(), **extra):
        body = {"title": title, "owner_user_id": uid[owner], "cited_source_ids": list(cited), **extra}
        if due:
            body["due_date"] = due
        if finding:
            body["finding_id"] = finding
        return elira.post(f"/cases/{ref}/tasks", body)

    dren.patch("/settings", ch["settings"])

    # Every observed stage on some case (the latest review per case drives the stage chart).
    d = detail("ONB-022")
    review(nadia, "ONB-022", "keep_open", "Start of onboarding", "Dea started on 12 October; pipeline access is "
           "requested and there is nothing to validate yet.", [src(d, "S12")], stage="pre_onboarding")
    d = detail("ONB-013")
    review(nadia, "ONB-013", "keep_open", "Access", "Ilda confirmed the VPN herself; Nimbus Console still awaits the "
           "application owner and Ticket Desk is only requested.", [src(d, "S04")], stage="access")
    d = detail("ONB-021")
    review(ardit, "ONB-021", "keep_open", "Shadowing", "Mia is shadowing the first-line team; supported execution "
           "has not been observed.", [src(d, "S11")], stage="shadowing")
    d = detail("ONB-020")
    review(ardit, "ONB-020", "validate_scope", "Standard requests with support", "Jon handles standard Orion "
           "requests with support, as reported in S10.", [src(d, "S10")], "supported_execution", "supported_execution")
    d = detail("ONB-018")
    review(nadia, "ONB-018", "keep_open", "Standard requests", "Omar handles standard requests independently; one "
           "complex scenario is still outstanding.", [src(d, "S09")], stage="independent_execution")

    # ONB-025 Kai: signed off early with a documented exception, then reopened after a client escalation.
    d = detail("ONB-025")
    s13, s14 = src(d, "S13"), src(d, "S14")
    review(ardit, "ONB-025", "validate_scope", "KT plan and training owner", "Atlas KT plan agreed with Ardit as "
           "training owner.", [s13], "kt_plan")
    review(ardit, "ONB-025", "validate_scope", "Standard requests", "Kai handles standard requests independently.",
           [s13], "supported_execution", "supported_execution")
    review(ardit, "ONB-025", "close", "Whole onboarding", "Signed off early so Kai could start on the client project.",
           [s13], stage="independent_execution",
           exception="Client start date moved forward; month-end reconciliation to be observed on the project.")
    review(ardit, "ONB-025", "reopen", "Whole onboarding", "The client escalated a failed month-end reconciliation "
           "that was never covered in Kai's KT. Reopening until it is observed.", [s14])
    task("ONB-025", "Cover the Atlas month-end reconciliation with Kai", "tl_orion", "2026-10-16", cited=[s14])

    # Task shapes: no due date given (the SLA sets it), due later, and an ownership gap routed to the admin.
    task("ONB-017", "Confirm Rina's project assignment before her start date", "coord")
    task("ONB-019", "Observe Elsa's first Lyra deployment", "tl_lyra", "2026-11-02")
    d = detail("ONB-026")
    gap = next(f["id"] for f in d["findings"] if f["rule_id"] == "MISSING_TECH_OWNER")
    task("ONB-026", "Name a technical owner for Sirius", "admin", "2026-10-15", gap, [src(d, "S15")])

    # Relayed mail: the authenticated intake endpoint (service token, no session).
    relay = TestClient(app, base_url="http://showcase.local")
    for m in ch["relay"]:
        r = relay.post("/api/integrations/inbound", headers={"Authorization": f"Bearer {relay_token}"},
                       json={k: v for k, v in m.items() if k != "claims"})
        if r.status_code >= 300:
            raise ShowcaseError(f"relay: {r.status_code} {r.text[:300]}")

    # A recorded agent run on Mia's case; Elira accepts one proposal into a task and dismisses the other.
    spec = ch["agent_run"]
    d = detail(spec["case"])
    ids = _recorded_agent_run(db, org, spec, users, d)
    for pid, pr in zip(ids, spec["proposals"]):
        if pr["decision"] == "accept":
            task(spec["case"], pr["title"], pr["owner"], pr["due"], cited=[src(d, pr["cite"])], proposal_id=pid)
        else:
            elira.post(f"/agent-proposals/{pid}/dismiss", {"reason": pr["reason"]})


def _chapter(db: Session, org: Org, fn, days: tuple) -> None:
    from ..services.org_settings import as_of, get_org_settings
    started = datetime.now(timezone.utc) - timedelta(seconds=1)
    fn()
    db.expire_all()
    _backdate(db, org, started, datetime.now(timezone.utc) + timedelta(seconds=1), as_of(get_org_settings(db, org.id)),
              days)


def run(db: Session, org: Org, domain: str) -> str:
    """Load whichever chapters are missing (a database seeded with chapter 1 only gets chapter 2)."""
    data = load()
    done = []
    if not present(db, org):
        def one():
            users = _people(db, org, data, domain)
            _base(db, org, data, users)
            db.commit()  # the API runs in its own sessions
            _activity(data, users)
        _chapter(db, org, one, (3, 1))  # chapter 1: 11 to 13 Oct
        done.append(f"{len(data['cases']) + len(data['new_cases'])} cases, {len(data['sources'])} sources")
    if not present(db, org, CHAPTER2_REF):
        ch = data["chapter2"]

        def two():
            users = _people(db, org, data, domain)
            _base(db, org, {"projects": ch["projects"], "cases": ch["cases"], "sources": ch["sources"]}, users)
            token = _relay_credential(db, org)
            db.commit()
            _activity2(db, org, data, users, token)
        _chapter(db, org, two, (1, 0))  # chapter 2: 13 to 14 Oct, always after chapter 1
        done.append(f"{len(ch['cases'])} cases, {len(ch['sources'])} sources (chapter 2)")
    return f"Showcase loaded: {'; '.join(done)}." if done else ""
