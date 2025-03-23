"""Add PendingBusinessRequest model to the database

Revision ID: 327a421c978e
Revises: 37ae8aeb59ae
Create Date: 2025-03-21 20:09:52.862009
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '327a421c978e'
down_revision: Union[str, None] = '37ae8aeb59ae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pending_business_requests',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('business_id', sa.Integer, sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('token', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('pending_business_requests')