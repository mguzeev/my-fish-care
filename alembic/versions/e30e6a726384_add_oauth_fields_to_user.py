"""add_oauth_fields_to_user

Revision ID: e30e6a726384
Revises: 276584265f54
Create Date: 2026-01-20 20:08:25.561867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e30e6a726384'
down_revision: Union[str, None] = '276584265f54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite-compatible migration using batch operations
    
    # Update agents table - make model_name nullable
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.alter_column('model_name',
                   existing_type=sa.VARCHAR(length=100),
                   nullable=True)
    
    # Update subscription_plans table - change plan_type to enum
    with op.batch_alter_table('subscription_plans', schema=None) as batch_op:
        batch_op.alter_column('plan_type',
                   existing_type=sa.VARCHAR(length=20),
                   type_=sa.Enum('SUBSCRIPTION', 'ONE_TIME', name='plantype', native_enum=False),
                   existing_nullable=False,
                   existing_server_default=sa.text("'subscription'"))
    
    # Update users table - add OAuth fields
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('oauth_provider', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('oauth_id', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('picture_url', sa.String(length=500), nullable=True))
        batch_op.alter_column('hashed_password',
                   existing_type=sa.VARCHAR(length=255),
                   nullable=True)
        batch_op.create_index(batch_op.f('ix_users_oauth_id'), ['oauth_id'], unique=False)


def downgrade() -> None:
    # SQLite-compatible downgrade using batch operations
    
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_oauth_id'))
        batch_op.alter_column('hashed_password',
                   existing_type=sa.VARCHAR(length=255),
                   nullable=False)
        batch_op.drop_column('picture_url')
        batch_op.drop_column('oauth_id')
        batch_op.drop_column('oauth_provider')
    
    with op.batch_alter_table('subscription_plans', schema=None) as batch_op:
        batch_op.alter_column('plan_type',
                   existing_type=sa.Enum('SUBSCRIPTION', 'ONE_TIME', name='plantype', native_enum=False),
                   type_=sa.VARCHAR(length=20),
                   existing_nullable=False,
                   existing_server_default=sa.text("'subscription'"))
    
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.alter_column('model_name',
                   existing_type=sa.VARCHAR(length=100),
                   nullable=False)
