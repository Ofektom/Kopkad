"""Update savings schema with duration_months and payment_reference

Revision ID: 18a4b300ade4
Revises: c11a7599fe89
Create Date: 2025-03-29 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# Revision identifiers, used by Alembic
revision = "18a4b300ade4"
down_revision = "c11a7599fe89"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get the inspector to check column existence
    inspector = inspect(op.get_bind())

    # Rename duration_days to duration_months
    op.alter_column(
        "savings_accounts",
        "duration_days",
        new_column_name="duration_months",
        type_=sa.Integer(),
        existing_nullable=False,
    )

    # Ensure savings_type uses the correct enum values
    op.alter_column(
        "savings_accounts",
        "savings_type",
        type_=sa.Enum("daily", "target", name="savingstype"),
        existing_type=sa.Enum("daily", "target", name="savingstype"),
        nullable=False,
    )

    # Check if payment_reference exists in savings_markings
    columns = [col["name"] for col in inspector.get_columns("savings_markings")]
    if "payment_reference" not in columns:
        op.add_column(
            "savings_markings",
            sa.Column("payment_reference", sa.String(length=50), nullable=True)
        )

    # Ensure marked_by_id is nullable
    op.alter_column(
        "savings_markings",
        "marked_by_id",
        type_=sa.Integer(),
        nullable=True,
        existing_type=sa.Integer(),
        existing_nullable=False,  # If it was previously non-nullable
    )


def downgrade() -> None:
    # Get the inspector for downgrade checks
    inspector = inspect(op.get_bind())

    # Revert marked_by_id to non-nullable (if it was originally so)
    op.alter_column(
        "savings_markings",
        "marked_by_id",
        type_=sa.Integer(),
        nullable=False,
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    # Drop payment_reference if it exists
    columns = [col["name"] for col in inspector.get_columns("savings_markings")]
    if "payment_reference" in columns:
        op.drop_column("savings_markings", "payment_reference")

    # Revert duration_months back to duration_days
    op.alter_column(
        "savings_accounts",
        "duration_months",
        new_column_name="duration_days",
        type_=sa.Integer(),
        existing_nullable=False,
    )