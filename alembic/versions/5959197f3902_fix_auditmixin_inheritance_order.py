"""Fix AuditMixin inheritance order

Revision ID: 5959197f3902
Revises: 96664650bbc4
Create Date: 2025-04-01 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5959197f3902'
down_revision: Union[str, None] = '96664650bbc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Ensure created_at and updated_at are nullable to match AuditMixin
    op.alter_column(
        "savings_accounts",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "savings_markings",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "savings_accounts",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
        existing_onupdate=sa.func.now(),
    )
    op.alter_column(
        "savings_markings",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text("now()"),
        existing_onupdate=sa.func.now(),
    )

def downgrade() -> None:
    # Revert created_at and updated_at to non-nullable
    op.alter_column(
        "savings_accounts",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "savings_markings",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )
    op.alter_column(
        "savings_accounts",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
        existing_onupdate=sa.func.now(),
    )
    op.alter_column(
        "savings_markings",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
        existing_onupdate=sa.func.now(),
    )