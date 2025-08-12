"""Add payment_accounts, account_details, payment_requests tables and paymentrequeststatus enum

Revision ID: 3c50fb742cea
Revises: 0de71857359e
Create Date: 2025-08-12 02:35:22.705332

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c50fb742cea'
down_revision: Union[str, None] = '0de71857359e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Check if paymentrequeststatus enum exists
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'paymentrequeststatus')")).scalar()
    if not result:
        op.execute("CREATE TYPE paymentrequeststatus AS ENUM ('pending', 'approved', 'rejected')")
    else:
        # Verify enum values
        existing_values = conn.execute(
            sa.text("SELECT enumlabel FROM pg_enum WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymentrequeststatus')")
        ).fetchall()
        existing_values = [row[0] for row in existing_values]
        expected_values = ['pending', 'approved', 'rejected']
        if set(existing_values) != set(expected_values):
            op.execute("DROP TYPE paymentrequeststatus CASCADE")
            op.execute("CREATE TYPE paymentrequeststatus AS ENUM ('pending', 'approved', 'rejected')")

    # Create payment_accounts table if it doesn't exist
    if 'payment_accounts' not in existing_tables:
        op.create_table('payment_accounts',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['customer_id'], ['users.id'], name='payment_accounts_customer_id_fkey'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='payment_accounts_created_by_fkey'),
            sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='payment_accounts_updated_by_fkey'),
            sa.PrimaryKeyConstraint('id', name='payment_accounts_pkey')
        )

    # Create account_details table if it doesn't exist
    if 'account_details' not in existing_tables:
        op.create_table('account_details',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('payment_account_id', sa.Integer(), nullable=False),
            sa.Column('account_name', sa.String(length=100), nullable=False),
            sa.Column('account_number', sa.String(length=20), nullable=False),
            sa.Column('bank_name', sa.String(length=100), nullable=False),
            sa.Column('bank_code', sa.String(length=10), nullable=True),
            sa.Column('account_type', sa.String(length=50), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['payment_account_id'], ['payment_accounts.id'], name='account_details_payment_account_id_fkey', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='account_details_created_by_fkey'),
            sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='account_details_updated_by_fkey'),
            sa.PrimaryKeyConstraint('id', name='account_details_pkey')
        )

    # Create payment_requests table if it doesn't exist
    if 'payment_requests' not in existing_tables:
        op.create_table('payment_requests',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('payment_account_id', sa.Integer(), nullable=False),
            sa.Column('account_details_id', sa.Integer(), nullable=False),
            sa.Column('savings_account_id', sa.Integer(), nullable=False),
            sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='paymentrequeststatus'), nullable=False, server_default='pending'),
            sa.Column('request_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('approval_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['payment_account_id'], ['payment_accounts.id'], name='payment_requests_payment_account_id_fkey', ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['account_details_id'], ['account_details.id'], name='payment_requests_account_details_id_fkey'),
            sa.ForeignKeyConstraint(['savings_account_id'], ['savings_accounts.id'], name='payment_requests_savings_account_id_fkey'),
            sa.ForeignKeyConstraint(['created_by'], ['users.id'], name='payment_requests_created_by_fkey'),
            sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name='payment_requests_updated_by_fkey'),
            sa.PrimaryKeyConstraint('id', name='payment_requests_pkey')
        )

def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Drop payment_requests table if it exists
    if 'payment_requests' in existing_tables:
        op.drop_table('payment_requests')

    # Drop account_details table if it exists
    if 'account_details' in existing_tables:
        op.drop_table('account_details')

    # Drop payment_accounts table if it exists
    if 'payment_accounts' in existing_tables:
        op.drop_table('payment_accounts')

    # Drop paymentrequeststatus enum if it exists
    op.execute("DROP TYPE IF EXISTS paymentrequeststatus")