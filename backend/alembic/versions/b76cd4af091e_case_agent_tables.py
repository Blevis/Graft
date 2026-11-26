"""store case investigations and proposed actions

Revision ID: b76cd4af091e
Revises: e9597a669f66
Create Date: 2026-11-26 14:00:14.014136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b76cd4af091e'
down_revision: Union[str, Sequence[str], None] = 'e9597a669f66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('agent_runs',
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('case_id', sa.String(length=32), nullable=False),
    sa.Column('requested_by', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('assessment', sa.Text(), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.Column('prompt_version', sa.String(length=40), nullable=False),
    sa.Column('evidence_hash', sa.String(length=64), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status in ('running','completed','failed','unavailable')", name='ck_agent_run_status'),
    sa.ForeignKeyConstraint(['case_id'], ['cases.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.create_index('ix_agent_case_history', ['org_id', 'case_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_org_id'), ['org_id'], unique=False)
        batch_op.create_index('uq_agent_active_case', ['org_id', 'case_id'], unique=True, sqlite_where=sa.text("status = 'running'"), postgresql_where=sa.text("status = 'running'"))

    op.create_table('agent_proposals',
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('owner_role', sa.String(length=50), nullable=True),
    sa.Column('owner_user_id', sa.String(length=32), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('cited_source_ids', sa.JSON(), nullable=False),
    sa.Column('cited_claim_ids', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('dismiss_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind in ('task','message','access_followup')", name='ck_agent_proposal_kind'),
    sa.CheckConstraint("status in ('open','accepted','dismissed')", name='ck_agent_proposal_status'),
    sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_proposals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_proposals_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_proposals_run_id'), ['run_id'], unique=False)

    op.create_table('agent_steps',
    sa.Column('org_id', sa.String(length=32), nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('index', sa.Integer(), nullable=False),
    sa.Column('tool', sa.String(length=100), nullable=False),
    sa.Column('arguments', sa.JSON(), nullable=False),
    sa.Column('result_summary', sa.Text(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ),
    sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'index', name='uq_agent_step_index')
    )
    with op.batch_alter_table('agent_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_steps_org_id'), ['org_id'], unique=False)

    # SQLite's application connections can have foreign-key cascades disabled.
    if op.get_context().dialect.name == "sqlite":
        op.execute("""CREATE TRIGGER delete_case_agent_history AFTER DELETE ON cases
                   BEGIN
                     DELETE FROM agent_steps WHERE run_id IN
                       (SELECT id FROM agent_runs WHERE case_id = OLD.id);
                     DELETE FROM agent_proposals WHERE run_id IN
                       (SELECT id FROM agent_runs WHERE case_id = OLD.id);
                     DELETE FROM agent_runs WHERE case_id = OLD.id;
                   END""")


def downgrade() -> None:
    if op.get_context().dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS delete_case_agent_history")
    op.drop_table("agent_steps")
    op.drop_table("agent_proposals")
    op.drop_table("agent_runs")
