"""Fix plan_type enum values

Revision ID: plantype_enum_fix_001
Revises: 5b0a0e4dfd6f
Create Date: 2026-01-17 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'plantype_enum_fix_001'
down_revision: Union[str, Sequence[str], None] = '5b0a0e4dfd6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix the plan_type enum values to match SQLAlchemy's expected enum member names.
    
    The issue: when plan_type column was created, it stored lowercase values ('subscription', 'one_time')
    but SQLAlchemy's enum handling expects values to match enum member names ('SUBSCRIPTION', 'ONE_TIME').
    
    This migration updates the database values to match the enum member names.
    """
    # Update subscription plan_type values to match enum member names
    op.execute("UPDATE subscription_plans SET plan_type = 'SUBSCRIPTION' WHERE plan_type = 'subscription'")
    op.execute("UPDATE subscription_plans SET plan_type = 'ONE_TIME' WHERE plan_type = 'one_time'")


def downgrade() -> None:
    """Revert the plan_type enum values to lowercase."""
    # Revert back to lowercase values
    op.execute("UPDATE subscription_plans SET plan_type = 'subscription' WHERE plan_type = 'SUBSCRIPTION'")
    op.execute("UPDATE subscription_plans SET plan_type = 'one_time' WHERE plan_type = 'ONE_TIME'")