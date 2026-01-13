"""add paddle sync fields

Revision ID: 4a6db2f62ec5
Revises: ef55233a9283
Create Date: 2026-01-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a6db2f62ec5"
down_revision: Union[str, None] = "ef55233a9283"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "billing_accounts",
        sa.Column("last_webhook_event_id", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "billing_accounts",
        sa.Column("last_transaction_id", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "billing_accounts",
        sa.Column("next_billing_date", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "billing_accounts",
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_billing_accounts_last_webhook_event_id"),
        "billing_accounts",
        ["last_webhook_event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_billing_accounts_last_webhook_event_id"), table_name="billing_accounts")
    op.drop_column("billing_accounts", "cancelled_at")
    op.drop_column("billing_accounts", "next_billing_date")
    op.drop_column("billing_accounts", "last_transaction_id")
    op.drop_column("billing_accounts", "last_webhook_event_id")
