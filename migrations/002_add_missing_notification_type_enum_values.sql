-- Migration: Add Missing Notification Type Enum Values
-- Date: 2025-11-16
-- Description: Adds all missing notification type enum values to support payment, savings, business, user, commission, and system notifications
-- Rollback: 002_rollback_add_missing_notification_type_enum_values.sql

BEGIN;

-- Add all missing notification type enum values
-- Existing values: 'overspending', 'goal_progress', 'spending_anomaly', 'savings_opportunity', 'monthly_summary', 'health_score'

-- Payment related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'payment_request_pending' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'payment_request_pending';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'payment_approved' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'payment_approved';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'payment_rejected' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'payment_rejected';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'payment_cancelled' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'payment_cancelled';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'payment_request_reminder' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'payment_request_reminder';
    END IF;
END $$;

-- Savings related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_account_created' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_account_created';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_account_updated' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_account_updated';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_account_deleted' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_account_deleted';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_account_completed' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_account_completed';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_payment_marked' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_payment_marked';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_bulk_marked' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_bulk_marked';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_account_extended' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_account_extended';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_nearing_completion' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_nearing_completion';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_payment_overdue' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_payment_overdue';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'savings_completion_reminder' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'savings_completion_reminder';
    END IF;
END $$;

-- Business related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_created' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_created';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_updated' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_updated';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_deleted' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_deleted';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_invitation_sent' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_invitation_sent';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_invitation_accepted' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_invitation_accepted';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_invitation_rejected' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_invitation_rejected';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_without_admin' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_without_admin';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'business_switched' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'business_switched';
    END IF;
END $$;

-- Unit related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'unit_created' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'unit_created';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'unit_updated' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'unit_updated';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'unit_deleted' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'unit_deleted';
    END IF;
END $$;

-- User related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'user_created' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'user_created';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'user_status_changed' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'user_status_changed';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'user_deactivated' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'user_deactivated';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'user_deleted' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'user_deleted';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'admin_assigned' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'admin_assigned';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'admin_credentials_generated' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'admin_credentials_generated';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'inactive_user_reminder' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'inactive_user_reminder';
    END IF;
END $$;

-- Commission related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'commission_earned' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'commission_earned';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'commission_paid' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'commission_paid';
    END IF;
END $$;

-- System related
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'new_business_registered' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'new_business_registered';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'new_admin_created' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'new_admin_created';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'system_alert' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'system_alert';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'system_summary' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'system_summary';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'weekly_analytics' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'weekly_analytics';
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'low_balance_alert' AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')) THEN
        ALTER TYPE notificationtype ADD VALUE 'low_balance_alert';
    END IF;
END $$;

COMMIT;

-- Verification: List all notification type enum values
SELECT enumlabel as notification_type 
FROM pg_enum 
WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = 'notificationtype')
ORDER BY enumlabel;

