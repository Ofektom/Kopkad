"""Add token version to user table

Revision ID: 9d590c954167
Revises: 306c4d3def03
Create Date: 2025-06-15 12:13:10.817452
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9d590c954167'
down_revision: Union[str, None] = '306c4d3def03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Add token_version column to users table."""
    op.add_column('users', sa.Column('token_version', sa.Integer, nullable=False, server_default='1'))

def downgrade() -> None:
    """Drop token_version column from users table."""
    op.drop_column('users', 'token_version')