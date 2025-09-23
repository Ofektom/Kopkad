from alembic import op
import sqlalchemy as sa

revision = 'b9e343f1cd4e'
down_revision = 'f05c76f93734'  # Change to 'aead30d5e3d0' if applied
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('expense_cards', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('expenses', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('commissions', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('payment_accounts', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('account_details', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('payment_requests', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('businesses', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('users', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('units', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('pending_business_requests', 'created_at', nullable=False, server_default=sa.text('now()'))
    op.alter_column('user_settings', 'created_at', nullable=False, server_default=sa.text('now()'))

def downgrade() -> None:
    op.alter_column('expense_cards', 'created_at', nullable=True, server_default=None)
    op.alter_column('expenses', 'created_at', nullable=True, server_default=None)
    op.alter_column('commissions', 'created_at', nullable=True, server_default=None)
    op.alter_column('payment_accounts', 'created_at', nullable=True, server_default=None)
    op.alter_column('account_details', 'created_at', nullable=True, server_default=None)
    op.alter_column('payment_requests', 'created_at', nullable=True, server_default=None)
    op.alter_column('businesses', 'created_at', nullable=True, server_default=None)
    op.alter_column('users', 'created_at', nullable=True, server_default=None)
    op.alter_column('units', 'created_at', nullable=True, server_default=None)
    op.alter_column('pending_business_requests', 'created_at', nullable=True, server_default=None)
    op.alter_column('user_settings', 'created_at', nullable=True, server_default=None)