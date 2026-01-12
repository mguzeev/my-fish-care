"""add plan_agents many-to-many relationship

Revision ID: 10805613c4fc
Revises: 9c2f3b1c1d0a
Create Date: 2026-01-12 19:31:44.016345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10805613c4fc'
down_revision: Union[str, None] = '9c2f3b1c1d0a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create plan_agents association table
    op.create_table(
        'plan_agents',
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['subscription_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('plan_id', 'agent_id')
    )


def downgrade() -> None:
    op.drop_table('plan_agents')
