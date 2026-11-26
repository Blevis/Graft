"""Password hashes for fictional demo accounts; provenance of uploaded documents on sources.

users.password_hash: salted scrypt, set only for members of demo organisations (SSO users never have one).
sources.document: {filename, content_type, size, sha256, method, pages} for evidence extracted from an uploaded file.
The original file is not kept; the extracted text is the immutable source body.

Revision ID: d8a4c2e6f1b3
Revises: c7e1a5d9f2b6
Create Date: 2026-11-26 21:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d8a4c2e6f1b3"
down_revision: Union[str, Sequence[str], None] = "c7e1a5d9f2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=200), nullable=True))
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(sa.Column("document", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_column("document")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_hash")
