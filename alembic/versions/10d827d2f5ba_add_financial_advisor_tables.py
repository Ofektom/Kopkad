"""add_financial_advisor_tables

Revision ID: 10d827d2f5ba
Revises: 457ae9e9cb5c
Create Date: 2025-10-19 01:06:41.028156

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '10d827d2f5ba'
down_revision: Union[str, None] = '457ae9e9cb5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enums (only if they don't exist)
    op.execute("DO $$ BEGIN CREATE TYPE goalpriority AS ENUM ('high', 'medium', 'low'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE goalstatus AS ENUM ('active', 'achieved', 'abandoned'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE patterntype AS ENUM ('recurring', 'seasonal', 'anomaly'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE notificationtype AS ENUM ('overspending', 'goal_progress', 'spending_anomaly', 'savings_opportunity', 'monthly_summary', 'health_score'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE notificationpriority AS ENUM ('high', 'medium', 'low'); EXCEPTION WHEN duplicate_object THEN null; END $$;")
    
    # Create savings_goals table (check if exists first)
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    if 'savings_goals' not in existing_tables:
        op.create_table(
            'savings_goals',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('target_amount', sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column('current_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
            sa.Column('deadline', sa.Date(), nullable=True),
            sa.Column('priority', sa.Enum('high', 'medium', 'low', name='goalpriority'), nullable=False, server_default='medium'),
            sa.Column('category', sa.String(length=50), nullable=True),
            sa.Column('status', sa.Enum('active', 'achieved', 'abandoned', name='goalstatus'), nullable=False, server_default='active'),
            sa.Column('is_ai_recommended', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_savings_goals_customer_id', 'savings_goals', ['customer_id'])
        op.create_index('ix_savings_goals_status', 'savings_goals', ['status'])
    
    # Create financial_health_scores table
    if 'financial_health_scores' not in existing_tables:
        op.create_table(
            'financial_health_scores',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('score', sa.Integer(), nullable=False),
            sa.Column('score_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('factors_breakdown', sa.JSON(), nullable=False),
            sa.Column('recommendations', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_health_scores_customer_id', 'financial_health_scores', ['customer_id'])
        op.create_index('ix_health_scores_score_date', 'financial_health_scores', ['score_date'])
    
    # Create spending_patterns table
    if 'spending_patterns' not in existing_tables:
        op.create_table(
            'spending_patterns',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('customer_id', sa.Integer(), nullable=False),
            sa.Column('pattern_type', sa.Enum('recurring', 'seasonal', 'anomaly', name='patterntype'), nullable=False),
            sa.Column('description', sa.Text(), nullable=False),
            sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column('frequency', sa.String(length=50), nullable=True),
            sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
            sa.Column('last_occurrence', sa.Date(), nullable=True),
            sa.Column('metadata', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['customer_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_spending_patterns_customer_id', 'spending_patterns', ['customer_id'])
        op.create_index('ix_spending_patterns_type', 'spending_patterns', ['pattern_type'])
    
    # Create user_notifications table
    if 'user_notifications' not in existing_tables:
        op.create_table(
            'user_notifications',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('notification_type', sa.Enum('overspending', 'goal_progress', 'spending_anomaly', 'savings_opportunity', 'monthly_summary', 'health_score', name='notificationtype'), nullable=False),
            sa.Column('title', sa.String(length=200), nullable=False),
            sa.Column('message', sa.Text(), nullable=False),
            sa.Column('priority', sa.Enum('high', 'medium', 'low', name='notificationpriority'), nullable=False, server_default='medium'),
            sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('related_entity_id', sa.Integer(), nullable=True),
            sa.Column('related_entity_type', sa.String(length=50), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('updated_by', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_user_notifications_user_id', 'user_notifications', ['user_id'])
        op.create_index('ix_user_notifications_is_read', 'user_notifications', ['is_read'])
        op.create_index('ix_user_notifications_created_at', 'user_notifications', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Check which tables exist before dropping
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    # Drop tables (if they exist)
    if 'user_notifications' in existing_tables:
        op.drop_index('ix_user_notifications_created_at', 'user_notifications')
        op.drop_index('ix_user_notifications_is_read', 'user_notifications')
        op.drop_index('ix_user_notifications_user_id', 'user_notifications')
        op.drop_table('user_notifications')
    
    if 'spending_patterns' in existing_tables:
        op.drop_index('ix_spending_patterns_type', 'spending_patterns')
        op.drop_index('ix_spending_patterns_customer_id', 'spending_patterns')
        op.drop_table('spending_patterns')
    
    if 'financial_health_scores' in existing_tables:
        op.drop_index('ix_health_scores_score_date', 'financial_health_scores')
        op.drop_index('ix_health_scores_customer_id', 'financial_health_scores')
        op.drop_table('financial_health_scores')
    
    if 'savings_goals' in existing_tables:
        op.drop_index('ix_savings_goals_status', 'savings_goals')
        op.drop_index('ix_savings_goals_customer_id', 'savings_goals')
        op.drop_table('savings_goals')
    
    # Drop enums (only if no other tables are using them)
    op.execute("DROP TYPE IF EXISTS notificationpriority")
    op.execute("DROP TYPE IF EXISTS notificationtype")
    op.execute("DROP TYPE IF EXISTS patterntype")
    op.execute("DROP TYPE IF EXISTS goalstatus")
    op.execute("DROP TYPE IF EXISTS goalpriority")
