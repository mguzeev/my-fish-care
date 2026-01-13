"""merge heads for paddle sync and llm models

Revision ID: 5b0a0e4dfd6f
Revises: 4a6db2f62ec5, c472b1280b95
Create Date: 2026-01-13 12:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5b0a0e4dfd6f"
down_revision: Union[str, Sequence[str], None] = ("4a6db2f62ec5", "c472b1280b95")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No-op merge migration.
    pass


def downgrade() -> None:
    # No-op merge migration.
    pass
