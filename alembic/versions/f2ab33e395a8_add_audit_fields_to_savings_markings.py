"""Add audit fields to savings_markings

Revision ID: f2ab33e395a8
Revises: 18a4b300ade4
Create Date: 2025-03-30 07:21:57.096511

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = "f2ab33e395a8"
down_revision = "18a4b300ade4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # Get the existing columns in savings_markings
    existing_columns = [col["name"] for col in inspector.get_columns("savings_markings")]

    # Add only if the column does not exist
    if "created_by" not in existing_columns:
        op.add_column("savings_markings", sa.Column("created_by", sa.Integer, nullable=True))
    
    if "updated_by" not in existing_columns:
        op.add_column("savings_markings", sa.Column("updated_by", sa.Integer, nullable=True))

    if "created_at" not in existing_columns:
        op.add_column(
            "savings_markings",
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now())
        )


def downgrade() -> None:
    op.drop_column("savings_markings", "updated_at")
    op.drop_column("savings_markings", "created_at")
    op.drop_column("savings_markings", "updated_by")
    op.drop_column("savings_markings", "created_by")