"""Fix savings_markings status enum

Revision ID: abf7c09d8809
Revises: 5959197f3902
Create Date: 2025-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = "abf7c09d8809"
down_revision = "5959197f3902"
branch_labels = None
depends_on = None

def upgrade():
    # Step 1: Drop the existing server_default on the status column
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status DROP DEFAULT")

    # Step 2: Create the new enum with the correct values
    op.execute("CREATE TYPE savingsmarkingstatus_new AS ENUM ('PENDING', 'PAID')")

    # Step 3: Alter the column to use the new enum, mapping old values to new ones
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN status
        TYPE savingsmarkingstatus_new
        USING (
            CASE
                WHEN status = 'pending' THEN 'PENDING'
                WHEN status = 'active' THEN 'PAID'
                WHEN status = 'completed' THEN 'PAID'
                ELSE 'PENDING'
            END
        )::savingsmarkingstatus_new
    """)

    # Step 4: Drop the old enum
    op.execute("DROP TYPE savingsmarkingstatus")

    # Step 5: Rename the new enum to the original name
    op.execute("ALTER TYPE savingsmarkingstatus_new RENAME TO savingsmarkingstatus")

    # Step 6: Set the new server_default to match the new enum
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status SET DEFAULT 'PENDING'")

def downgrade():
    # Step 1: Drop the existing server_default on the status column
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status DROP DEFAULT")

    # Step 2: Create the old enum
    op.execute("CREATE TYPE savingsmarkingstatus_old AS ENUM ('pending', 'active', 'completed')")

    # Step 3: Alter the column back to the old enum
    op.execute("""
        ALTER TABLE savings_markings
        ALTER COLUMN status
        TYPE savingsmarkingstatus_old
        USING (
            CASE
                WHEN status = 'PENDING' THEN 'pending'
                WHEN status = 'PAID' THEN 'completed'
                ELSE 'pending'
            END
        )::savingsmarkingstatus_old
    """)

    # Step 4: Drop the new enum
    op.execute("DROP TYPE savingsmarkingstatus")

    # Step 5: Rename the old enum to the original name
    op.execute("ALTER TYPE savingsmarkingstatus_old RENAME TO savingsmarkingstatus")

    # Step 6: Set the original server_default
    op.execute("ALTER TABLE savings_markings ALTER COLUMN status SET DEFAULT 'pending'")