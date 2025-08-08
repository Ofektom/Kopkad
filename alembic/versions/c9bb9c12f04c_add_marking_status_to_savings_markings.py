"""Add marking_status to savings_accounts and update payment_method enum

Revision ID: c9bb9c12f04c
Revises: 3a738fa595d9
Create Date: 2025-08-06 18:21:17.629715

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from models.savings import MarkingStatus

# revision identifiers, used by Alembic.
revision: str = 'c9bb9c12f04c'
down_revision: Union[str, None] = '3a738fa595d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Create the markingstatus ENUM type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE markingstatus AS ENUM ('not_started', 'in_progress', 'completed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Add marking_status to savings_accounts
    op.add_column(
        'savings_accounts',
        sa.Column(
            'marking_status',
            sa.Enum(MarkingStatus, name='markingstatus'),
            nullable=False,
            server_default=MarkingStatus.NOT_STARTED.value
        )
    )
    
    # Drop the default value on payment_method to avoid DatatypeMismatch
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN payment_method
        DROP DEFAULT;
    """)
    
    # Create new paymentmethod enum without CASH
    op.execute("""
        CREATE TYPE paymentmethod_new AS ENUM ('card', 'bank_transfer');
    """)
    
    # Update payment_method column to use new enum
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN payment_method
        TYPE paymentmethod_new
        USING (
            CASE
                WHEN payment_method = 'cash' THEN NULL
                ELSE payment_method::text::paymentmethod_new
            END
        );
    """)
    
    # Drop old paymentmethod enum
    op.execute("DROP TYPE IF EXISTS paymentmethod;")
    
    # Rename new enum to paymentmethod
    op.execute("ALTER TYPE paymentmethod_new RENAME TO paymentmethod;")
    
    # Optionally set a new default value if needed
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN payment_method
        SET DEFAULT NULL;
    """)

def downgrade() -> None:
    """Downgrade schema."""
    # Create old paymentmethod enum with CASH
    op.execute("""
        CREATE TYPE paymentmethod_old AS ENUM ('card', 'bank_transfer', 'cash');
    """)
    
    # Drop the default value on payment_method
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN payment_method
        DROP DEFAULT;
    """)
    
    # Revert payment_method to old enum
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN payment_method
        TYPE paymentmethod_old
        USING (payment_method::text::paymentmethod_old);
    """)
    
    # Drop new paymentmethod enum
    op.execute("DROP TYPE IF EXISTS paymentmethod;")
    
    # Rename old enum to paymentmethod
    op.execute("ALTER TYPE paymentmethod_old RENAME TO paymentmethod;")
    
    # Restore original default value (adjust if different in your schema)
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN payment_method
        SET DEFAULT 'card';
    """)
    
    # Drop marking_status from savings_accounts
    op.drop_column('savings_accounts', 'marking_status')
    
    # Drop markingstatus enum
    op.execute("DROP TYPE IF EXISTS markingstatus;")