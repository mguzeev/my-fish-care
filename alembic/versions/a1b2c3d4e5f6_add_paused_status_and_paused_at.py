"""Add paused status and paused_at field.

Revision ID: a1b2c3d4e5f6
Revises: 5b0a0e4dfd6f
Create Date: 2026-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str = '5b0a0e4dfd6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add paused_at column to billing_accounts
    op.add_column('billing_accounts', sa.Column('paused_at', sa.DateTime(), nullable=True))
    
    # Note: subscription_status is stored as VARCHAR (native_enum=False in SQLAlchemy)
    # so we don't need to alter the enum type in the database.
    # The new 'paused' value will be accepted as a string.


def downgrade() -> None:
    # Remove paused_at column
    op.drop_column('billing_accounts', 'paused_at')
    
    # Update any 'paused' statuses back to 'active' before downgrade
    op.execute("UPDATE billing_accounts SET subscription_status = 'active' WHERE subscription_status = 'paused'")
