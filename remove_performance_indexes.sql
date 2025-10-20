-- ============================================================================
-- Remove Performance Indexes from Ofektom Savings System
-- ============================================================================
-- Purpose: Rollback script to remove all performance indexes
-- Use this if you need to remove the indexes for any reason
-- Date: October 19, 2025
-- ============================================================================

-- Start transaction
BEGIN;

-- ============================================================================
-- DROP USERS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_users_username;
DROP INDEX IF EXISTS idx_users_phone_number;
DROP INDEX IF EXISTS idx_users_email;
DROP INDEX IF EXISTS idx_users_role;
DROP INDEX IF EXISTS idx_users_is_active;
DROP INDEX IF EXISTS idx_users_token_version;
DROP INDEX IF EXISTS idx_users_username_active;

-- ============================================================================
-- DROP BUSINESSES TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_businesses_agent_id;
DROP INDEX IF EXISTS idx_businesses_unique_code;

-- ============================================================================
-- DROP SAVINGS ACCOUNTS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_savings_customer_id;
DROP INDEX IF EXISTS idx_savings_business_id;
DROP INDEX IF EXISTS idx_savings_tracking_number;
DROP INDEX IF EXISTS idx_savings_marking_status;
DROP INDEX IF EXISTS idx_savings_created_at;
DROP INDEX IF EXISTS idx_savings_customer_status;
DROP INDEX IF EXISTS idx_savings_business_created;

-- ============================================================================
-- DROP SAVINGS MARKINGS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_markings_savings_account;
DROP INDEX IF EXISTS idx_markings_status;
DROP INDEX IF EXISTS idx_markings_marked_date;
DROP INDEX IF EXISTS idx_markings_payment_reference;
DROP INDEX IF EXISTS idx_markings_ref_status;
DROP INDEX IF EXISTS idx_markings_account_date;

-- ============================================================================
-- DROP PAYMENT ACCOUNTS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_payment_accounts_customer;

-- ============================================================================
-- DROP ACCOUNT DETAILS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_account_details_payment_account;

-- ============================================================================
-- DROP PAYMENT REQUESTS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_payment_requests_payment_account;
DROP INDEX IF EXISTS idx_payment_requests_savings_account;
DROP INDEX IF EXISTS idx_payment_requests_status;
DROP INDEX IF EXISTS idx_payment_requests_created_at;
DROP INDEX IF EXISTS idx_payment_requests_status_created;

-- ============================================================================
-- DROP COMMISSIONS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_commissions_agent;
DROP INDEX IF EXISTS idx_commissions_savings_account;
DROP INDEX IF EXISTS idx_commissions_date;
DROP INDEX IF EXISTS idx_commissions_agent_date;

-- ============================================================================
-- DROP SETTINGS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_settings_user_id;

-- ============================================================================
-- DROP EXPENSE CARDS TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_expense_cards_customer;
DROP INDEX IF EXISTS idx_expense_cards_savings_account;

-- ============================================================================
-- DROP EXPENSES TABLE INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_expenses_card;
DROP INDEX IF EXISTS idx_expenses_date;
DROP INDEX IF EXISTS idx_expenses_category;

-- ============================================================================
-- DROP RELATIONSHIP TABLES INDEXES
-- ============================================================================

DROP INDEX IF EXISTS idx_user_business_user;
DROP INDEX IF EXISTS idx_user_business_business;
DROP INDEX IF EXISTS idx_user_units_user;
DROP INDEX IF EXISTS idx_user_units_unit;

-- ============================================================================
-- COMMIT TRANSACTION
-- ============================================================================

COMMIT;

-- Success message
SELECT 'Performance indexes removed successfully!' AS result;

