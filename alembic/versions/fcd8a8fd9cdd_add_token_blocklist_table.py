"""Add token_blocklist table

Revision ID: fcd8a8fd9cdd
Revises: 5bdbc0d87a02
Create Date: 2025-06-14 05:54:46.051747
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func

# revision identifiers, used by Alembic.
revision = 'fcd8a8fd9cdd'
down_revision = '5bdbc0d87a02'
branch_labels = None
depends_on = None

def upgrade():
    """Upgrade schema to add token_blocklist table."""
    op.create_table(
        'token_blocklist',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_token_blocklist_id'), 'token_blocklist', ['id'], unique=False)
    op.create_index(op.f('ix_token_blocklist_token'), 'token_blocklist', ['token'], unique=True)

def downgrade():
    """Downgrade schema by dropping token_blocklist table."""
    op.drop_index(op.f('ix_token_blocklist_token'), table_name='token_blocklist')
    op.drop_index(op.f('ix_token_blocklist_id'), table_name='token_blocklist')
    op.drop_table('token_blocklist')