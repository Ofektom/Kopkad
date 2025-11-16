"""add_missing_notification_type_enum_values

Revision ID: 216d41782eac
Revises: 10d827d2f5ba
Create Date: 2025-11-16 11:45:33.437389

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '216d41782eac'
down_revision: Union[str, None] = '10d827d2f5ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing notification type enum values."""
    # Add all missing notification type enum values
    # Existing values: 'overspending', 'goal_progress', 'spending_anomaly', 'savings_opportunity', 'monthly_summary', 'health_score'
    # Use DO block to safely add values only if they don't exist
    
    enum_values = [
        # Payment related
        'payment_request_pending', 'payment_approved', 'payment_rejected', 
        'payment_cancelled', 'payment_request_reminder',
        # Savings related
        'savings_account_created', 'savings_account_updated', 'savings_account_deleted',
        'savings_account_completed', 'savings_payment_marked', 'savings_bulk_marked',
        'savings_account_extended', 'savings_nearing_completion', 'savings_payment_overdue',
        'savings_completion_reminder',
        # Business related
        'business_created', 'business_updated', 'business_deleted',
        'business_invitation_sent', 'business_invitation_accepted', 'business_invitation_rejected',
        'business_without_admin', 'business_switched',
        # Unit related
        'unit_created', 'unit_updated', 'unit_deleted',
        # User related
        'user_created', 'user_status_changed', 'user_deactivated', 'user_deleted',
        'admin_assigned', 'admin_credentials_generated', 'inactive_user_reminder',
        # Commission related
        'commission_earned', 'commission_paid',
        # System related
        'new_business_registered', 'new_admin_created', 'system_alert',
        'system_summary', 'weekly_analytics', 'low_balance_alert',
    ]
    
    for value in enum_values:
        op.execute(f"""
            DO $$ 
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_enum 
                    WHERE enumlabel = '{value}' 
                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')
                ) THEN
                    ALTER TYPE notificationtype ADD VALUE '{value}';
                END IF;
            END $$;
        """)


def downgrade() -> None:
    """Note: PostgreSQL does not support removing enum values directly."""
    # PostgreSQL doesn't support removing enum values, so we can't downgrade this
    # If needed, the enum would need to be recreated
    pass
