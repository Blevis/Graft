"""merge agent tables and case readiness fields

Revision ID: e01208631a81
Revises: b76cd4af091e, e702d683f8d7
Create Date: 2026-11-26 14:13:10.682681

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e01208631a81'
down_revision: Union[str, Sequence[str], None] = ('b76cd4af091e', 'e702d683f8d7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
