"""add_cooperative_features

Revision ID: manual_coop_001
Revises: 216d41782eac
Create Date: 2026-02-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'manual_coop_001'
down_revision: Union[str, None] = '216d41782eac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add COOPERATIVE_MEMBER to role enum
    op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'cooperative_member'")
    op.execute("COMMIT")  # Enum changes usually require commit in some pg versions, but let's try standard flow

    # 2. Create BusinessType enum
    op.execute("CREATE TYPE businesstype AS ENUM ('standard', 'cooperative')")

    # 2b. Add COOPERATIVE to savingstype enum
    op.execute("ALTER TYPE savingstype ADD VALUE IF NOT EXISTS 'cooperative'")
    op.execute("COMMIT")

    # 3. Add business_type column to businesses table
    op.add_column('businesses', sa.Column('business_type', sa.Enum('standard', 'cooperative', name='businesstype'), nullable=False, server_default='standard'))


def downgrade() -> None:
    # Downgrade logic (imperfect for enums)
    op.drop_column('businesses', 'business_type')
    op.execute("DROP TYPE businesstype")
    # Cannot remove enum value easily
