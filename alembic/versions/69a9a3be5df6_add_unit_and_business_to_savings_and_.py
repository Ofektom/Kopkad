"""Add unit_id to savings_accounts and savings_markings

Revision ID: 69a9a3be5df6
Revises: 9d590c954167
Create Date: 2025-06-20 20:50:58.379906

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '69a9a3be5df6'
down_revision: Union[str, None] = '9d590c954167'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Add unit_id column to savings_accounts
    op.add_column(
        'savings_accounts',
        sa.Column('unit_id', sa.Integer, sa.ForeignKey('units.id'), nullable=True)
    )

    # Add unit_id column to savings_markings
    op.add_column(
        'savings_markings',
        sa.Column('unit_id', sa.Integer, sa.ForeignKey('units.id'), nullable=True)
    )

    # Update existing savings_accounts with unit_id based on user_units where available
    op.execute("""
        UPDATE savings_accounts sa
        SET unit_id = (
            SELECT uu.unit_id
            FROM user_units uu
            JOIN units u ON uu.unit_id = u.id
            WHERE uu.user_id = sa.customer_id
            AND u.business_id = sa.business_id
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM user_units uu
            JOIN units u ON uu.unit_id = u.id
            WHERE uu.user_id = sa.customer_id
            AND u.business_id = sa.business_id
        )
    """)

    # Update savings_accounts with no unit_id to use the default unit for their business
    op.execute("""
        UPDATE savings_accounts sa
        SET unit_id = (
            SELECT u.id
            FROM units u
            WHERE u.business_id = sa.business_id
            ORDER BY u.id ASC
            LIMIT 1
        )
        WHERE sa.unit_id IS NULL
    """)

    # Check for savings_accounts with no unit_id (i.e., no units exist for the business)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM savings_accounts sa
                WHERE sa.unit_id IS NULL
            ) THEN
                RAISE EXCEPTION 'Some savings accounts could not be assigned a unit because no units exist for their business';
            END IF;
        END $$;
    """)

    # Update existing savings_markings with unit_id from their corresponding savings_accounts
    op.execute("""
        UPDATE savings_markings sm
        SET unit_id = (
            SELECT sa.unit_id
            FROM savings_accounts sa
            WHERE sa.id = sm.savings_account_id
        )
    """)

    # Alter savings_accounts.unit_id to be non-nullable since all records now have a unit_id
    op.alter_column('savings_accounts', 'unit_id', nullable=False)

    # Alter savings_markings.unit_id to be non-nullable since all records now have a unit_id
    op.alter_column('savings_markings', 'unit_id', nullable=False)

def downgrade() -> None:
    """Downgrade schema."""
    # Alter columns to be nullable before dropping (for safety)
    op.alter_column('savings_markings', 'unit_id', nullable=True)
    op.alter_column('savings_accounts', 'unit_id', nullable=True)

    # Drop unit_id column from savings_markings
    op.drop_column('savings_markings', 'unit_id')

    # Drop unit_id column from savings_accounts
    op.drop_column('savings_accounts', 'unit_id')