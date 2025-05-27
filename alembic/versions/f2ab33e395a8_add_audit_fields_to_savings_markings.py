"""Add audit fields to savings_markings

Revision ID: f2ab33e395a8
Revises: 18a4b300ade4
Create Date: [Original Creation Date]
"""
from alembic import op
import sqlalchemy as sa

revision = "f2ab33e395a8"
down_revision = "18a4b300ade4"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'created_at'
            ) THEN
                ALTER TABLE savings_markings
                ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT now();
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE savings_markings
                ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT now();
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'created_by'
            ) THEN
                ALTER TABLE savings_markings
                ADD COLUMN created_by INTEGER;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'updated_by'
            ) THEN
                ALTER TABLE savings_markings
                ADD COLUMN updated_by INTEGER;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_savings_markings_created_by'
            ) THEN
                ALTER TABLE savings_markings
                ADD CONSTRAINT fk_savings_markings_created_by
                FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_savings_markings_updated_by'
            ) THEN
                ALTER TABLE savings_markings
                ADD CONSTRAINT fk_savings_markings_updated_by
                FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)

def downgrade():
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_savings_markings_updated_by'
            ) THEN
                ALTER TABLE savings_markings
                DROP CONSTRAINT fk_savings_markings_updated_by;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_savings_markings_created_by'
            ) THEN
                ALTER TABLE savings_markings
                DROP CONSTRAINT fk_savings_markings_created_by;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'updated_by'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN updated_by;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'created_by'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN created_by;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN updated_at;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'created_at'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN created_at;
            END IF;
        END $$;
    """)