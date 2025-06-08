"""Add cash payment method

Revision ID: 26f2099148b9
Revises: 26fcf5f629bd
Create Date: 2025-06-08 20:30:42.521170

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '26f2099148b9'
down_revision: Union[str, None] = '26fcf5f629bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Alter the paymentmethod enum to include CASH
    op.execute("ALTER TYPE paymentmethod ADD VALUE 'cash'")

    # Make payment_method column nullable
    op.alter_column(
        'savings_markings',
        'payment_method',
        existing_type=postgresql.ENUM('card', 'bank_transfer', 'cash', name='paymentmethod'),
        nullable=True
    )

def downgrade() -> None:
    """Downgrade schema."""
    # Make payment_method column non-nullable with default 'card'
    op.alter_column(
        'savings_markings',
        'payment_method',
        existing_type=postgresql.ENUM('card', 'bank_transfer', 'cash', name='paymentmethod'),
        nullable=False,
        server_default='card'
    )

    # Remove CASH from paymentmethod enum
    # Note: PostgreSQL does not support dropping enum values directly.
    # To safely downgrade, we create a new enum without 'cash', update the column, and drop the old enum.
    op.execute("CREATE TYPE paymentmethod_temp AS ENUM ('card', 'bank_transfer')")
    op.execute("UPDATE savings_markings SET payment_method = 'card' WHERE payment_method = 'cash'")
    op.alter_column(
        'savings_markings',
        'payment_method',
        type_=sa.Enum('card', 'bank_transfer', name='paymentmethod_temp'),
        postgresql_using='payment_method::paymentmethod_temp'
    )
    op.execute("DROP TYPE paymentmethod")
    op.execute("ALTER TYPE paymentmethod_temp RENAME TO paymentmethod")