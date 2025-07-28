"""update target_amount for daily savings accounts

Revision ID: 3a738fa595d9
Revises: aa0361022c92
Create Date: 2025-07-28 14:53:05.151600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3a738fa595d9'
down_revision: Union[str, None] = 'aa0361022c92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    # Update target_amount for daily savings where it is NULL
    op.execute("""
        UPDATE savings_accounts
        SET target_amount = daily_amount * (
            SELECT (
                CAST((start_date + INTERVAL '1 month' * duration_months - INTERVAL '1 day') AS DATE) 
                - start_date + 1
            )::INTEGER
            WHERE start_date IS NOT NULL AND duration_months > 0
        )
        WHERE savings_type = 'daily' 
        AND target_amount IS NULL 
        AND start_date IS NOT NULL 
        AND duration_months > 0;
    """)

def downgrade() -> None:
    """Downgrade schema."""
    # Revert target_amount to NULL for daily savings
    op.execute("""
        UPDATE savings_accounts
        SET target_amount = NULL
        WHERE savings_type = 'daily';
    """)