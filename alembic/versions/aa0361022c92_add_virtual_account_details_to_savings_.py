"""Add virtual_account_details to savings_markings

Revision ID: aa0361022c92
Revises: 69a9a3be5df6
Create Date: 2025-06-28 14:25:32.928730
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'aa0361022c92'
down_revision = '69a9a3be5df6'
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'savings_markings',
        sa.Column('virtual_account_details', sa.JSON, nullable=True)
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('savings_markings', 'virtual_account_details')