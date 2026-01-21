"""add_vision_support_fields

Revision ID: 786fab8c175e
Revises: e30e6a726384
Create Date: 2026-01-21 12:52:59.577926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '786fab8c175e'
down_revision: Union[str, None] = 'e30e6a726384'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add capability fields to llm_models
    op.add_column('llm_models', sa.Column('supports_text', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('llm_models', sa.Column('supports_vision', sa.Boolean(), nullable=False, server_default='false'))
    
    # Add has_image to usage_records
    op.add_column('usage_records', sa.Column('has_image', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove columns in reverse order
    op.drop_column('usage_records', 'has_image')
    op.drop_column('llm_models', 'supports_vision')
    op.drop_column('llm_models', 'supports_text')
