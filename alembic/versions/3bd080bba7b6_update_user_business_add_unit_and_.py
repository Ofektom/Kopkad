"""Update User, Business, add Unit and PendingBusinessRequest changes

Revision ID: 3bd080bba7b6
Revises: 527297a63e4b
Create Date: 2025-05-28 16:55:37.285766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3bd080bba7b6'
down_revision: Union[str, None] = '527297a63e4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create units table
    op.create_table('units',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('business_id', sa.Integer(), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create user_units table
    op.create_table('user_units',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['unit_id'], ['units.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'unit_id')
    )
    
    # Add unit_id and audit fields to pending_business_requests
    op.add_column('pending_business_requests', sa.Column('unit_id', sa.Integer(), nullable=True))
    op.add_column('pending_business_requests', sa.Column('created_by', sa.Integer(), nullable=True))
    op.add_column('pending_business_requests', sa.Column('updated_by', sa.Integer(), nullable=True))
    op.add_column('pending_business_requests', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(None, 'pending_business_requests', 'units', ['unit_id'], ['id'])
    op.create_foreign_key(None, 'pending_business_requests', 'users', ['created_by'], ['id'])
    op.create_foreign_key(None, 'pending_business_requests', 'users', ['updated_by'], ['id'])
    
    # Rename businesses.location to address
    op.alter_column('businesses', 'location', new_column_name='address', type_=sa.String(length=255), existing_nullable=True)
    
    # Add unique constraint to businesses.agent_id
    op.create_unique_constraint('unique_agent_id', 'businesses', ['agent_id'])
    
    # Drop location from users
    op.drop_column('users', 'location')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add location to users
    op.add_column('users', sa.Column('location', sa.VARCHAR(), autoincrement=False, nullable=True))
    
    # Remove unique constraint from businesses.agent_id
    op.drop_constraint('unique_agent_id', 'businesses', type_='unique')
    
    # Rename businesses.address back to location
    op.alter_column('businesses', 'address', new_column_name='location', type_=sa.String(length=100), existing_nullable=True)
    
    # Remove columns from pending_business_requests
    op.drop_constraint(None, 'pending_business_requests', type_='foreignkey')
    op.drop_constraint(None, 'pending_business_requests', type_='foreignkey')
    op.drop_column('pending_business_requests', 'updated_at')
    op.drop_column('pending_business_requests', 'updated_by')
    op.drop_column('pending_business_requests', 'created_by')
    op.drop_column('pending_business_requests', 'unit_id')
    
    # Drop user_units and units tables
    op.drop_table('user_units')
    op.drop_table('units')