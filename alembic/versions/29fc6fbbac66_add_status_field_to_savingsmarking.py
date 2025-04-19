"""add status field to savings_markings table

Revision ID: 29fc6fbbac66
Revises: f2ab33e395a8
Create Date: 2025-03-30 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# Define ENUM before using it
savingsmarkingstatus = sa.Enum("pending", "active", "completed", name="savingsmarkingstatus")

# Revision identifiers, used by Alembic
revision = "29fc6fbbac66"
down_revision = "f2ab33e395a8"
branch_labels = None
depends_on = None

def upgrade():
    # Create ENUM type before using it
    savingsmarkingstatus.create(op.get_bind(), checkfirst=True)

    # Add new column with ENUM type
    op.add_column(
        "savings_markings",
        sa.Column(
            "status",
            savingsmarkingstatus,
            server_default="pending",
            nullable=False,
        ),
    )

def downgrade():
    # Drop the column first
    op.drop_column("savings_markings", "status")

    # Drop ENUM type after removing the column
    savingsmarkingstatus.drop(op.get_bind(), checkfirst=True)
