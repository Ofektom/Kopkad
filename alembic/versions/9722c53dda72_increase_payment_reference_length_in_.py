"""Increase payment_reference length in savings_markings

Revision ID: 9722c53dda72
Revises: 1c7b2060417e
Create Date: 2025-08-08 23:20:45.034593

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9722c53dda72'
down_revision: Union[str, None] = '1c7b2060417e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.alter_column(
        'savings_markings',
        'payment_reference',
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        nullable=True
    )

def downgrade():
    op.alter_column(
        'savings_markings',
        'payment_reference',
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        nullable=True
    )
