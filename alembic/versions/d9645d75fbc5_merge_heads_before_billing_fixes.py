"""merge_heads_before_billing_fixes

Revision ID: d9645d75fbc5
Revises: b3c4d5e6f7g8, plantype_enum_fix_001
Create Date: 2026-01-18 12:49:08.124539

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9645d75fbc5'
down_revision: Union[str, None] = ('b3c4d5e6f7g8', 'plantype_enum_fix_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
