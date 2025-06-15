# migrations/versions/306c4d3def03_remove_token_blocklist.py
"""Remove token_blocklist

Revision ID: 306c4d3def03
Revises: fcd8a8fd9cdd
Create Date: 2025-06-15 12:04:32.331217
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '306c4d3def03'
down_revision: Union[str, None] = 'fcd8a8fd9cdd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Drop token_blocklist table and its indexes."""
    op.drop_index(op.f('ix_token_blocklist_token'), table_name='token_blocklist')
    op.drop_index(op.f('ix_token_blocklist_id'), table_name='token_blocklist')
    op.drop_table('token_blocklist')

def downgrade() -> None:
    """Recreate token_blocklist table with original schema."""
    op.create_table(
        'token_blocklist',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_token_blocklist_id'), 'token_blocklist', ['id'], unique=False)
    op.create_index(op.f('ix_token_blocklist_token'), 'token_blocklist', ['token'], unique=True)