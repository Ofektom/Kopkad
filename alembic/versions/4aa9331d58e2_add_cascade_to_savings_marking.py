"""Add ondelete=CASCADE to savings_markings.savings_account_id

Revision ID: 4aa9331d58e2
Revises: 26f2099148b9
Create Date: 2025-06-09 23:05:22.049698

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4aa9331d58e2'
down_revision = '26f2099148b9'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the existing foreign key constraint
    op.drop_constraint('savings_markings_savings_account_id_fkey', 'savings_markings', type_='foreignkey')
    
    # Create a new foreign key constraint with ondelete='CASCADE'
    op.create_foreign_key(
        'savings_markings_savings_account_id_fkey',
        'savings_markings',
        'savings_accounts',
        ['savings_account_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    # Drop the foreign key constraint with CASCADE
    op.drop_constraint('savings_markings_savings_account_id_fkey', 'savings_markings', type_='foreignkey')
    
    # Recreate the original foreign key constraint without CASCADE
    op.create_foreign_key(
        'savings_markings_savings_account_id_fkey',
        'savings_markings',
        'savings_accounts',
        ['savings_account_id'],
        ['id']
    )