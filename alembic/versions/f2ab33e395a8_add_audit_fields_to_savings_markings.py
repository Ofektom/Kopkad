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
    # Add audit columns
    op.add_column(
        "savings_markings",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.add_column(
        "savings_markings",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.func.now(),
            nullable=True,
        ),
    )
    op.add_column(
        "savings_markings",
        sa.Column("created_by", sa.Integer(), nullable=True),
    )
    op.add_column(
        "savings_markings",
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )

    # Add foreign key constraints
    op.create_foreign_key(
        "fk_savings_markings_created_by",
        "savings_markings",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_savings_markings_updated_by",
        "savings_markings",
        "users",
        ["updated_by"],
        ["id"],
        ondelete="SET NULL",
    )

def downgrade():
    # Drop foreign key constraints if they exist
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
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_savings_markings_created_by'
            ) THEN
                ALTER TABLE savings_markings
                DROP CONSTRAINT fk_savings_markings_created_by;
            END IF;
        END $$;
    """)

    # Drop columns if they exist
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'updated_by'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN updated_by;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'created_by'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN created_by;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN updated_at;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'savings_markings' AND column_name = 'created_at'
            ) THEN
                ALTER TABLE savings_markings DROP COLUMN created_at;
            END IF;
        END $$;
    """)