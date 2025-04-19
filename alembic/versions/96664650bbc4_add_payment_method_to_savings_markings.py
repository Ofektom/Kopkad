"""Add payment_method to savings_markings

Revision ID: 96664650bbc4
Revises: 5959197f3902
Create Date: 2025-03-31 10:43:17.588296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '96664650bbc4'
down_revision: Union[str, None] = '5959197f3902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Step 1: Create the paymentmethod enum type
    op.execute("CREATE TYPE paymentmethod AS ENUM ('card', 'bank_transfer')")
    
    # Step 2: Add the payment_method column with the enum type and a default value
    op.add_column(
        "savings_markings",
        sa.Column(
            "payment_method",
            sa.Enum(name="paymentmethod", native_enum=True),
            nullable=False,
            server_default="card"  # Set database-level default
        )
    )

def downgrade() -> None:
    # Drop the column first
    op.drop_column("savings_markings", "payment_method")
    # Then drop the enum type
    op.execute("DROP TYPE paymentmethod")