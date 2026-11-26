"""OIDC identity links (issuer + subject -> user). No credentials are stored.

Revision ID: c7e1a5d9f2b6
Revises: b4d2e8f1a9c3
Create Date: 2026-11-26 19:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7e1a5d9f2b6"
down_revision: Union[str, Sequence[str], None] = "b4d2e8f1a9c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("issuer", sa.String(300), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("issuer", "subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
