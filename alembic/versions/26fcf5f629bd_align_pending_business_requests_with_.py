"""Align pending_business_requests with models

Revision ID: 26fcf5f629bd
Revises: 3bd080bba7b6
Create Date: 2025-05-29 11:32:56.737563
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '26fcf5f629bd'
down_revision: Union[str, None] = '3bd080bba7b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Drop audit columns from pending_business_requests if they exist
    op.drop_column('pending_business_requests', 'created_by')
    op.drop_column('pending_business_requests', 'updated_by')
    op.drop_column('pending_business_requests', 'updated_at')

    # Add created_by to units
    op.add_column('units', sa.Column('created_by', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'units', 'users', ['created_by'], ['id'])

def downgrade() -> None:
    """Downgrade schema."""
    # Re-add audit columns to pending_business_requests
    op.add_column('pending_business_requests', sa.Column('created_by', sa.Integer(), nullable=True))
    op.add_column('pending_business_requests', sa.Column('updated_by', sa.Integer(), nullable=True))
    op.add_column('pending_business_requests', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(None, 'pending_business_requests', 'users', ['created_by'], ['id'])
    op.create_foreign_key(None, 'pending_business_requests', 'users', ['updated_by'], ['id'])

    # Remove created_by from units
    op.drop_constraint(None, 'units', type_='foreignkey')
    op.drop_column('units', 'created_by')