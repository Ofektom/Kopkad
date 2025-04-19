"""Add CREATE_CUSTOMER to permission enum

Revision ID: 9b904b1e7f74
Revises: eb7ce62356d5
Create Date: 2025-03-19 08:35:09.368741

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b904b1e7f74"
down_revision: Union[str, None] = "eb7ce62356d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding 'create_customer' to the 'permission' ENUM type."""
    # Add the new value to the existing 'permission' ENUM type
    op.execute("ALTER TYPE permission ADD VALUE 'create_customer'")


def downgrade() -> None:
    """Downgrade schema by removing 'create_customer' from the 'permission' ENUM type."""
    # PostgreSQL doesn't allow direct removal of ENUM values, so we:
    # 1. Create a temporary ENUM with all values (including create_customer)
    # 2. Convert the column to the temporary type
    # 3. Drop the original ENUM
    # 4. Create a new ENUM without create_customer
    # 5. Convert the column back
    # 6. Drop the temporary ENUM
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'permission_old'
            ) THEN
                RAISE NOTICE 'Type permission_old already exists, skipping creation';
            ELSE
                CREATE TYPE permission_old AS ENUM (
                    'create_admin', 'create_agent', 'create_sub_agent', 'assign_business', 'create_customer'
                );
            END IF;

            ALTER TABLE user_permissions
                ALTER COLUMN permission TYPE permission_old USING permission::text::permission_old;

            DROP TYPE permission;

            CREATE TYPE permission AS ENUM (
                'create_admin', 'create_agent', 'create_sub_agent', 'assign_business'
            );

            ALTER TABLE user_permissions
                ALTER COLUMN permission TYPE permission USING permission::text::permission;

            DROP TYPE permission_old;
        END
        $$;
    """
    )
