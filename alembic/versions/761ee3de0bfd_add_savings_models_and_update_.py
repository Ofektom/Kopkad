"""Add savings models and update permissions

Revision ID: 761ee3de0bfd
Revises: 327a421c978e
Create Date: 2025-03-24 09:43:54.304289
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.sql import text

# Revision identifiers, used by Alembic
revision = "761ee3de0bfd"
down_revision = "327a421c978e"
branch_labels = None
depends_on = None

# Define enums
savings_type_enum = ENUM("daily", "target", name="savingstype", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    # Create savings_type enum if it doesn’t exist
    savings_type_enum.create(op.get_bind(), checkfirst=True)

    # Create savings_accounts table
    op.create_table(
        "savings_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("tracking_number", sa.String(length=10), nullable=False),
        sa.Column(
            "savings_type", savings_type_enum, nullable=False, server_default="daily"
        ),
        sa.Column("daily_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("target_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("commission_days", sa.Integer(), server_default="1", nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tracking_number", name="uq_savings_accounts_tracking_number"
        ),
    )

    # Create savings_markings table
    op.create_table(
        "savings_markings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("savings_account_id", sa.Integer(), nullable=False),
        sa.Column("marked_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("marked_by_id", sa.Integer(), nullable=False),
        sa.Column("payment_reference", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["marked_by_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["savings_account_id"],
            ["savings_accounts.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("savings_account_id", "marked_date", name="unique_marking"),
    )

    # Update permission enum by checking existing values
    existing_permissions = (
        op.get_bind()
        .execute(text("SELECT unnest(enum_range(NULL::permission))"))
        .fetchall()
    )
    existing_values = {row[0] for row in existing_permissions}

    new_permissions = [
        "create_savings",
        "reinitiate_savings",
        "update_savings",
        "mark_savings",
        "mark_savings_bulk",
    ]

    for perm in new_permissions:
        if perm not in existing_values:
            op.execute(text(f"ALTER TYPE permission ADD VALUE '{perm}'"))


def downgrade() -> None:
    """Downgrade schema."""
    # Drop savings_markings and savings_accounts tables
    op.drop_table("savings_markings")
    op.drop_table("savings_accounts")

    # Drop savings_type enum
    savings_type_enum.drop(op.get_bind(), checkfirst=True)

    # Remove new permissions from user_permissions
    op.execute(
        text(
            """
        DELETE FROM user_permissions
        WHERE permission IN ('create_savings', 'reinitiate_savings', 'update_savings', 'mark_savings', 'mark_savings_bulk')
    """
        )
    )
