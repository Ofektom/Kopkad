"""Add missing audit columns to savings_accounts

Revision ID: c11a7599fe89
Revises: 761ee3de0bfd
Create Date: 2025-03-28 19:14:29.763301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision = "c11a7599fe89"
down_revision = "761ee3de0bfd"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Upgrade schema."""
    # Add missing columns from AuditMixin
    op.add_column(
        "savings_accounts",
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "savings_accounts",
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )

    # Update commission_days default to match model (from 1 to 30)
    op.alter_column(
        "savings_accounts",
        "commission_days",
        server_default="30",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    # Make updated_at nullable to match AuditMixin
    op.alter_column(
        "savings_accounts",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
        existing_onupdate=sa.func.now(),
    )

def downgrade() -> None:
    """Downgrade schema."""
    # Remove added columns
    op.drop_column("savings_accounts", "created_by")
    op.drop_column("savings_accounts", "updated_by")

    # Revert commission_days default to original
    op.alter_column(
        "savings_accounts",
        "commission_days",
        server_default="1",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )

    # Revert updated_at to non-nullable
    op.alter_column(
        "savings_accounts",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
        existing_onupdate=sa.func.now(),
    )