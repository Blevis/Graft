"""Operator commands for a private deployment. Run inside the backend environment:

    python -m app.ops create-org --name "Acme" --slug acme --admin-name "Ada Admin" --admin-email ada@acme.example
    python -m app.ops service-token --org acme --name mail-relay        # prints the token once
    python -m app.ops revoke-token --org acme --name mail-relay
    python -m app.ops model-status                                      # Ollama reachability + pinned digest
    python -m app.ops jobs [--org acme]                                 # analysis queue status
    python -m app.ops retry-jobs --org acme                             # failed jobs back to queued
    python -m app.ops reminders                                         # overdue reminders/escalations now
    python -m app.ops retention --org acme [--apply]                    # dry run unless --apply

These are operator actions: they never run on startup."""
import argparse
import hashlib
import json
import secrets
import sys
from collections import Counter

from sqlalchemy import select, update

from .db import SessionLocal
from .models import (
    DEFAULT_SETTINGS, AnalysisJob, Membership, Org, RoleAssignment, ServiceCredential, Setting, User,
)
from .models._base import utcnow
from .services import audit


def _org(db, slug: str) -> Org:
    org = db.execute(select(Org).where(Org.slug == slug)).scalar_one_or_none()
    if org is None:
        sys.exit(f"No org with slug '{slug}'")
    return org


def create_org(a) -> None:
    """A private (non-demo) org: real clock, no seeded data, one admin provisioned by email for OIDC sign-in."""
    with SessionLocal() as db:
        if db.execute(select(Org).where(Org.slug == a.slug)).first():
            sys.exit("Slug already in use")
        org = Org(name=a.name, slug=a.slug, is_demo=False)
        db.add(org)
        db.flush()
        settings = {**DEFAULT_SETTINGS, "clock_mode": "real", "timezone": a.timezone,
                    "as_of_date": utcnow().date().isoformat()}
        for k, v in settings.items():
            db.add(Setting(org_id=org.id, key=k, value=v))
        user = db.execute(select(User).where(User.email == a.admin_email)).scalars().first() or \
            User(name=a.admin_name, email=a.admin_email, title="Organization admin")
        db.add(user)
        db.flush()
        db.add(Membership(org_id=org.id, user_id=user.id, status="active", joined_at=utcnow()))
        db.add(RoleAssignment(org_id=org.id, user_id=user.id, role_code="org_admin", scope_type="organization"))
        audit.record(db, org_id=org.id, actor_user_id=None, entity="org", entity_id=org.id, action="created_by_operator",
                     after={"name": a.name, "admin_email": a.admin_email})
        db.commit()
        print(f"Created org {a.slug} ({org.id}); admin {a.admin_email} signs in through OIDC.")


def service_token(a) -> None:
    with SessionLocal() as db:
        org = _org(db, a.org)
        token = "grs_" + secrets.token_urlsafe(32)
        cred = ServiceCredential(org_id=org.id, name=a.name, token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                                 scopes=["inbound:write"], is_active=True)
        db.add(cred)
        db.flush()
        audit.record(db, org_id=org.id, actor_user_id=None, entity="service_credential", entity_id=cred.id,
                     action="created_by_operator", after={"name": a.name, "scopes": cred.scopes})
        db.commit()
        print(token)
        print("Store this token in the relay's secret store now; Graft keeps only its SHA-256.", file=sys.stderr)


def revoke_token(a) -> None:
    with SessionLocal() as db:
        org = _org(db, a.org)
        n = 0
        for cred in db.execute(select(ServiceCredential).where(ServiceCredential.org_id == org.id,
                                                               ServiceCredential.name == a.name)).scalars():
            cred.is_active = False
            audit.record(db, org_id=org.id, actor_user_id=None, entity="service_credential", entity_id=cred.id,
                         action="revoked_by_operator")
            n += 1
        db.commit()
        print(f"Revoked {n} credential(s)")


def model_status(_a) -> None:
    from .ai import client
    print(json.dumps(client.status(refresh=True), indent=2))


def jobs(a) -> None:
    with SessionLocal() as db:
        q = select(AnalysisJob)
        if a.org:
            q = q.where(AnalysisJob.org_id == _org(db, a.org).id)
        rows = db.execute(q).scalars().all()
        print(json.dumps(Counter(j.status for j in rows), indent=2))
        for j in rows:
            if j.status in ("failed", "waiting"):
                print(f"{j.status:9} {j.id} attempts={j.attempts} {j.last_error or ''}")


def retry_jobs(a) -> None:
    with SessionLocal() as db:
        org = _org(db, a.org)
        n = db.execute(update(AnalysisJob).where(AnalysisJob.org_id == org.id, AnalysisJob.status == "failed")
                       .values(status="queued", attempts=0, run_after=utcnow())).rowcount
        db.commit()
        print(f"Re-queued {n} job(s)")


def reminders(_a) -> None:
    from .services.workflow import run_reminders
    with SessionLocal() as db:
        print(json.dumps(run_reminders(db), indent=2))


def retention(a) -> None:
    from .services.retention import apply_retention
    with SessionLocal() as db:
        report = apply_retention(db, _org(db, a.org).id, apply=a.apply)
        if a.apply:
            db.commit()
        print(json.dumps(report, indent=2, default=str))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m app.ops")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-org")
    c.add_argument("--name", required=True)
    c.add_argument("--slug", required=True)
    c.add_argument("--admin-name", required=True)
    c.add_argument("--admin-email", required=True)
    c.add_argument("--timezone", default="Europe/Tirane")
    c.set_defaults(fn=create_org)
    t = sub.add_parser("service-token")
    t.add_argument("--org", required=True)
    t.add_argument("--name", required=True)
    t.set_defaults(fn=service_token)
    r = sub.add_parser("revoke-token")
    r.add_argument("--org", required=True)
    r.add_argument("--name", required=True)
    r.set_defaults(fn=revoke_token)
    sub.add_parser("model-status").set_defaults(fn=model_status)
    j = sub.add_parser("jobs")
    j.add_argument("--org")
    j.set_defaults(fn=jobs)
    rj = sub.add_parser("retry-jobs")
    rj.add_argument("--org", required=True)
    rj.set_defaults(fn=retry_jobs)
    sub.add_parser("reminders").set_defaults(fn=reminders)
    rt = sub.add_parser("retention")
    rt.add_argument("--org", required=True)
    rt.add_argument("--apply", action="store_true")
    rt.set_defaults(fn=retention)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
