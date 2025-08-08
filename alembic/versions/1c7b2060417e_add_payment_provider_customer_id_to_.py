"""Add payment_provider_customer_id to users

Revision ID: 1c7b2060417e
Revises: c9bb9c12f04c
Create Date: 2025-08-08 18:39:29.613455

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1c7b2060417e'
down_revision: Union[str, None] = 'c9bb9c12f04c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('users', sa.Column('payment_provider_customer_id', sa.String(length=255), nullable=True))

def downgrade():
    op.drop_column('users', 'payment_provider_customer_id')
