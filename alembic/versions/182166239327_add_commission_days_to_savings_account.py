"""add commission_amount to savings_accounts

Revision ID: 182166239327
Revises: 9722c53dda72
Create Date: 2025-08-10 00:48:24.460888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '182166239327'
down_revision: Union[str, None] = '9722c53dda72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add commission_amount column as nullable to allow creation
    op.add_column('savings_accounts', sa.Column('commission_amount', sa.Numeric(precision=10, scale=2), nullable=True))
    # Step 2: Populate commission_amount with daily_amount for existing records
    op.execute("UPDATE savings_accounts SET commission_amount = COALESCE(daily_amount, 0.00)")
    # Step 3: Alter column to set NOT NULL constraint
    op.alter_column('savings_accounts', 'commission_amount', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove commission_amount column from savings_accounts
    op.drop_column('savings_accounts', 'commission_amount')