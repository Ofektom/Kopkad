from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Revision identifiers, used by Alembic.
revision: str = "5959197f3902"
down_revision: Union[str, None] = "29fc6fbbac66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a given table."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Upgrade schema: Add AuditMixin fields and foreign keys."""

    # Add new AuditMixin fields if they don't exist
    if not column_exists("savings_markings", "updated_at"):
        op.add_column(
            "savings_markings",
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not column_exists("savings_markings", "created_by"):
        op.add_column(
            "savings_markings",
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )

    if not column_exists("savings_markings", "updated_by"):
        op.add_column(
            "savings_markings",
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        )

    # Ensure all existing rows have a valid 'created_at' before making it NOT NULL
    op.execute("UPDATE savings_markings SET created_at = NOW() WHERE created_at IS NULL;")

    # Update created_at to be NOT NULL with default value
    op.alter_column(
        "savings_markings",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        existing_server_default=sa.text("now()"),
    )

    # Add foreign key constraints if they do not exist
    fk_constraints = {
        "fk_savings_markings_created_by": ("created_by", "users", "id"),
        "fk_savings_markings_updated_by": ("updated_by", "users", "id"),
    }

    for fk_name, (col, ref_table, ref_col) in fk_constraints.items():
        if not column_exists("savings_markings", col):
            op.create_foreign_key(
                fk_name,
                "savings_markings",
                ref_table,
                [col],
                [ref_col],
            )

def downgrade() -> None:
    """Downgrade schema: Remove AuditMixin fields and foreign keys."""

    # Drop foreign keys safely
    op.drop_constraint("fk_savings_markings_created_by", "savings_markings", type_="foreignkey")
    op.drop_constraint("fk_savings_markings_updated_by", "savings_markings", type_="foreignkey")

    # Revert created_at changes
    op.alter_column(
        "savings_markings",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Remove added columns only if they exist
    for column in ["updated_at", "created_by", "updated_by"]:
        if column_exists("savings_markings", column):
            op.drop_column("savings_markings", column)
