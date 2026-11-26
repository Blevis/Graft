"""Scoped role grants, case responsibilities, training log, AI preferences and versioned PMO guidance.

Migrates the legacy single-role and owner columns without loss, then drops them so the assignment tables are the
only source of truth:
  memberships.role              -> role_assignments (organization scope; admin -> org_admin, viewer -> management_viewer)
  projects.tech_owner_user_id   -> role_assignments (technical_owner, project scope, default for the project's cases)
  cases.line_manager_user_id    -> case_responsibilities (line_manager, source "migrated")
  cases.tech_owner_user_id      -> case_responsibilities (technical_owner, "migrated") only where it differs from
                                   the project default; otherwise the case simply inherits it
  tasks / agent_proposals owner_role legacy codes -> canonical codes

Revision ID: a3c9f1d2b7e4
Revises: e01208631a81
Create Date: 2026-11-26 18:00:00
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3c9f1d2b7e4"
down_revision: Union[str, Sequence[str], None] = "e01208631a81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY = {"admin": "org_admin", "viewer": "management_viewer"}
REVERSE = {"org_admin": "admin", "management_viewer": "viewer"}
PRIORITY = ("org_admin", "pmo_coordinator", "technical_owner", "line_manager", "employee", "management_viewer")


def _id() -> str:
    return uuid.uuid4().hex


def upgrade() -> None:
    now = datetime.now(timezone.utc)
    op.create_table(
        "role_assignments",
        sa.Column("org_id", sa.String(32), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_code", sa.String(32), nullable=False),
        sa.Column("scope_type", sa.String(12), nullable=False),
        sa.Column("scope_id", sa.String(32), nullable=True),
        sa.Column("default_for_cases", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_role_assignments_org_id", "role_assignments", ["org_id"])
    op.create_index("ix_role_assignments_user_id", "role_assignments", ["user_id"])
    op.create_index("ix_role_assignments_scope_id", "role_assignments", ["scope_id"])

    with op.batch_alter_table("access_items") as b:
        b.add_column(sa.Column("tester_user_id", sa.String(32), sa.ForeignKey("users.id",
                               name="fk_access_items_tester_user_id"), nullable=True))
        b.add_column(sa.Column("tested_by_user_id", sa.String(32), sa.ForeignKey("users.id",
                               name="fk_access_items_tested_by_user_id"), nullable=True))
        b.add_column(sa.Column("tested_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "case_responsibilities",
        sa.Column("org_id", sa.String(32), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("case_id", sa.String(32), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("responsibility_type", sa.String(32), nullable=False),
        sa.Column("access_item_id", sa.String(32), sa.ForeignKey("access_items.id"), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("assigned_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("id", sa.String(32), primary_key=True),
    )
    op.create_index("ix_case_responsibilities_org_id", "case_responsibilities", ["org_id"])
    op.create_index("ix_case_responsibilities_case_id", "case_responsibilities", ["case_id"])
    op.create_index("ix_case_responsibilities_user_id", "case_responsibilities", ["user_id"])

    op.create_table(
        "user_preferences",
        sa.Column("org_id", sa.String(32), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.UniqueConstraint("org_id", "user_id"),
    )
    op.create_index("ix_user_preferences_org_id", "user_preferences", ["org_id"])
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"])

    op.create_table(
        "ai_guidance_versions",
        sa.Column("org_id", sa.String(32), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("terminology", sa.Text(), nullable=False),
        sa.Column("report_structure", sa.Text(), nullable=False),
        sa.Column("escalation_summary", sa.Text(), nullable=False),
        sa.Column("formatting", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "version"),
    )
    op.create_index("ix_ai_guidance_versions_org_id", "ai_guidance_versions", ["org_id"])

    op.create_table(
        "training_entries",
        sa.Column("org_id", sa.String(32), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("case_id", sa.String(32), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=True),
        sa.Column("cited_source_ids", sa.JSON(), nullable=False),
        sa.Column("recorded_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("capacity", sa.String(32), nullable=False),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_training_entries_org_id", "training_entries", ["org_id"])
    op.create_index("ix_training_entries_case_id", "training_entries", ["case_id"])

    with op.batch_alter_table("knowledge_refs") as b:
        b.add_column(sa.Column("topic", sa.String(40), nullable=True))
        b.add_column(sa.Column("description", sa.Text(), nullable=True))
        b.add_column(sa.Column("applies_to_roles", sa.JSON(), nullable=True))
        b.add_column(sa.Column("tags", sa.JSON(), nullable=True))

    with op.batch_alter_table("memberships") as b:
        b.add_column(sa.Column("status", sa.String(12), nullable=False, server_default="active"))
        b.add_column(sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True))

    # ---- data: legacy single role and owner columns -> assignment tables ----
    conn = op.get_bind()
    ra = sa.table("role_assignments", *[sa.column(c) for c in (
        "id", "org_id", "user_id", "role_code", "scope_type", "scope_id", "default_for_cases", "is_active",
        "created_at")])
    cr = sa.table("case_responsibilities", *[sa.column(c) for c in (
        "id", "org_id", "case_id", "user_id", "responsibility_type", "is_primary", "source", "assigned_at",
        "is_active", "notes")])
    grants: set[tuple] = set()

    def grant(org, user, role, scope_type="organization", scope_id=None, default=False):
        key = (org, user, role, scope_type, scope_id)
        if key in grants:
            return
        grants.add(key)
        conn.execute(ra.insert().values(id=_id(), org_id=org, user_id=user, role_code=role, scope_type=scope_type,
                                        scope_id=scope_id, default_for_cases=default, is_active=True,
                                        created_at=now))

    for org, user, role, created in conn.execute(sa.text(
            "SELECT org_id, user_id, role, created_at FROM memberships")).all():
        grant(org, user, LEGACY.get(role, role))
        conn.execute(sa.text("UPDATE memberships SET joined_at = :t WHERE org_id = :o AND user_id = :u"),
                     {"t": created or now, "o": org, "u": user})

    project_owner = {}
    for pid, org, owner in conn.execute(sa.text(
            "SELECT id, org_id, tech_owner_user_id FROM projects WHERE tech_owner_user_id IS NOT NULL")).all():
        project_owner[pid] = owner
        grant(org, owner, "technical_owner")
        grant(org, owner, "technical_owner", "project", pid, default=True)

    for cid, org, pid, lm, to in conn.execute(sa.text(
            "SELECT id, org_id, project_id, line_manager_user_id, tech_owner_user_id FROM cases")).all():
        if lm:
            grant(org, lm, "line_manager")
            conn.execute(cr.insert().values(id=_id(), org_id=org, case_id=cid, user_id=lm,
                                            responsibility_type="line_manager", is_primary=True, source="migrated",
                                            assigned_at=now, is_active=True,
                                            notes="Migrated from cases.line_manager_user_id"))
        if to and to != project_owner.get(pid):
            grant(org, to, "technical_owner")
            conn.execute(cr.insert().values(id=_id(), org_id=org, case_id=cid, user_id=to,
                                            responsibility_type="technical_owner", is_primary=True, source="migrated",
                                            assigned_at=now, is_active=True,
                                            notes="Migrated from cases.tech_owner_user_id"))

    for old, new in LEGACY.items():
        conn.execute(sa.text("UPDATE tasks SET owner_role = :n WHERE owner_role = :o"), {"n": new, "o": old})
        conn.execute(sa.text("UPDATE agent_proposals SET owner_role = :n WHERE owner_role = :o"), {"n": new, "o": old})

    # The assignment tables are now authoritative: drop the legacy columns.
    with op.batch_alter_table("memberships") as b:
        b.drop_column("role")
    with op.batch_alter_table("projects") as b:
        b.drop_column("tech_owner_user_id")
    with op.batch_alter_table("cases") as b:
        b.drop_column("line_manager_user_id")
        b.drop_column("tech_owner_user_id")


def downgrade() -> None:
    conn = op.get_bind()
    with op.batch_alter_table("memberships") as b:
        b.add_column(sa.Column("role", sa.String(32), nullable=False, server_default="viewer"))
    with op.batch_alter_table("projects") as b:
        b.add_column(sa.Column("tech_owner_user_id", sa.String(32), nullable=True))
    with op.batch_alter_table("cases") as b:
        b.add_column(sa.Column("line_manager_user_id", sa.String(32), nullable=True))
        b.add_column(sa.Column("tech_owner_user_id", sa.String(32), nullable=True))

    roles: dict[tuple, set] = {}
    for org, user, code in conn.execute(sa.text(
            "SELECT org_id, user_id, role_code FROM role_assignments WHERE is_active AND scope_type = 'organization'")):
        roles.setdefault((org, user), set()).add(code)
    for (org, user), codes in roles.items():
        best = next((c for c in PRIORITY if c in codes), None)
        if best:
            conn.execute(sa.text("UPDATE memberships SET role = :r WHERE org_id = :o AND user_id = :u"),
                         {"r": REVERSE.get(best, best), "o": org, "u": user})
    for pid, user in conn.execute(sa.text(
            "SELECT scope_id, user_id FROM role_assignments WHERE is_active AND scope_type = 'project' "
            "AND role_code = 'technical_owner' AND default_for_cases")).all():
        conn.execute(sa.text("UPDATE projects SET tech_owner_user_id = :u WHERE id = :p"), {"u": user, "p": pid})
    for cid, user, rtype in conn.execute(sa.text(
            "SELECT case_id, user_id, responsibility_type FROM case_responsibilities WHERE is_active AND is_primary "
            "AND responsibility_type IN ('line_manager', 'technical_owner')")).all():
        col = "line_manager_user_id" if rtype == "line_manager" else "tech_owner_user_id"
        conn.execute(sa.text(f"UPDATE cases SET {col} = :u WHERE id = :c"), {"u": user, "c": cid})
    for new, old in REVERSE.items():
        conn.execute(sa.text("UPDATE tasks SET owner_role = :o WHERE owner_role = :n"), {"n": new, "o": old})

    with op.batch_alter_table("memberships") as b:
        b.drop_column("status")
        b.drop_column("joined_at")
    with op.batch_alter_table("knowledge_refs") as b:
        for c in ("topic", "description", "applies_to_roles", "tags"):
            b.drop_column(c)
    with op.batch_alter_table("access_items") as b:
        b.drop_constraint("fk_access_items_tester_user_id", type_="foreignkey")
        b.drop_constraint("fk_access_items_tested_by_user_id", type_="foreignkey")
        for c in ("tester_user_id", "tested_by_user_id", "tested_at"):
            b.drop_column(c)
    for t in ("training_entries", "ai_guidance_versions", "user_preferences", "case_responsibilities",
              "role_assignments"):
        op.drop_table(t)
