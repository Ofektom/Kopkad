"""Add CREATE_BUSINESS to permission enum and update savings_markings status enum

Revision ID: 527297a63e4b
Revises: abf7c09d8809
Create Date: 2025-04-21 11:17:45.300925
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '527297a63e4b'
down_revision: Union[str, None] = 'abf7c09d8809'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Add CREATE_BUSINESS to the permission enum
    op.execute("ALTER TYPE permission ADD VALUE 'create_business'")

    # Remove the default value to avoid casting issues
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status DROP DEFAULT")

    # Create the new savingsstatus enum
    savingsstatus = postgresql.ENUM('pending', 'paid', name='savingsstatus', create_type=False)
    savingsstatus.create(op.get_bind(), checkfirst=True)

    # Temporarily change the column type to TEXT to update values
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status TYPE TEXT USING (status::TEXT)")

    # Update existing data to the new enum values
    op.execute("UPDATE savings_markings SET status = 'pending' WHERE status = 'PENDING'")
    op.execute("UPDATE savings_markings SET status = 'paid' WHERE status = 'PAID'")

    # Alter the column to use the new enum type
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status TYPE savingsstatus USING (status::savingsstatus)")

    # Set the new default value
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status SET DEFAULT 'pending'")

    # Drop the old savingsmarkingstatus enum
    op.execute("DROP TYPE savingsmarkingstatus")

def downgrade() -> None:
    """Downgrade schema."""
    # Create the old savingsmarkingstatus enum
    savingsmarkingstatus = postgresql.ENUM('PENDING', 'PAID', name='savingsmarkingstatus', create_type=False)
    savingsmarkingstatus.create(op.get_bind(), checkfirst=True)

    # Remove the default value
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status DROP DEFAULT")

    # Temporarily change the column type to TEXT to update values
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status TYPE TEXT USING (status::TEXT)")

    # Update data back to the old enum values
    op.execute("UPDATE savings_markings SET status = 'PENDING' WHERE status = 'pending'")
    op.execute("UPDATE savings_markings SET status = 'PAID' WHERE status = 'paid'")

    # Alter the column back to the old enum type
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status TYPE savingsmarkingstatus USING (status::savingsmarkingstatus)")

    # Set the old default value
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status SET DEFAULT 'PENDING'")

    # Drop the new savingsstatus enum
    op.execute("DROP TYPE savingsstatus")

    # Delete rows with create_business permission
    op.execute("DELETE FROM user_permissions WHERE permission = 'create_business'")
    print("Warning: 'create_business' was removed from user_permissions, but the permission enum still contains the value.")