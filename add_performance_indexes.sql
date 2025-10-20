-- ============================================================================
-- Performance Indexes for Ofektom Savings System
-- ============================================================================
-- Purpose: Add indexes to frequently queried columns for improved performance
-- Expected Impact: 50-70% faster query execution
-- Date: October 19, 2025
-- ============================================================================

-- Start transaction
BEGIN;

-- ============================================================================
-- USERS TABLE INDEXES
-- ============================================================================
-- Used for authentication, user lookups, and filtering

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_phone_number ON users(phone_number);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_token_version ON users(token_version);

-- Composite index for authentication queries (very common)
CREATE INDEX IF NOT EXISTS idx_users_username_active ON users(username, is_active);

-- ============================================================================
-- BUSINESSES TABLE INDEXES
-- ============================================================================
-- Used for agent lookups and business code searches

CREATE INDEX IF NOT EXISTS idx_businesses_agent_id ON businesses(agent_id);
CREATE INDEX IF NOT EXISTS idx_businesses_unique_code ON businesses(unique_code);

-- ============================================================================
-- SAVINGS ACCOUNTS TABLE INDEXES
-- ============================================================================
-- Used for customer savings lookups, tracking numbers, and status filtering

CREATE INDEX IF NOT EXISTS idx_savings_customer_id ON savings_accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_savings_business_id ON savings_accounts(business_id);
CREATE INDEX IF NOT EXISTS idx_savings_tracking_number ON savings_accounts(tracking_number);
CREATE INDEX IF NOT EXISTS idx_savings_marking_status ON savings_accounts(marking_status);
CREATE INDEX IF NOT EXISTS idx_savings_created_at ON savings_accounts(created_at);

-- Composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_savings_customer_status ON savings_accounts(customer_id, marking_status);
CREATE INDEX IF NOT EXISTS idx_savings_business_created ON savings_accounts(business_id, created_at);

-- ============================================================================
-- SAVINGS MARKINGS TABLE INDEXES
-- ============================================================================
-- Used for payment verification, status checks, and date queries

CREATE INDEX IF NOT EXISTS idx_markings_savings_account ON savings_markings(savings_account_id);
CREATE INDEX IF NOT EXISTS idx_markings_status ON savings_markings(status);
CREATE INDEX IF NOT EXISTS idx_markings_marked_date ON savings_markings(marked_date);
CREATE INDEX IF NOT EXISTS idx_markings_payment_reference ON savings_markings(payment_reference);

-- Composite indexes for payment verification (very important for performance)
CREATE INDEX IF NOT EXISTS idx_markings_ref_status ON savings_markings(payment_reference, status);
CREATE INDEX IF NOT EXISTS idx_markings_account_date ON savings_markings(savings_account_id, marked_date);

-- ============================================================================
-- PAYMENT ACCOUNTS TABLE INDEXES
-- ============================================================================
-- Used for customer payment account lookups

CREATE INDEX IF NOT EXISTS idx_payment_accounts_customer ON payment_accounts(customer_id);

-- ============================================================================
-- ACCOUNT DETAILS TABLE INDEXES
-- ============================================================================
-- Used for payment account details lookups

CREATE INDEX IF NOT EXISTS idx_account_details_payment_account ON account_details(payment_account_id);

-- ============================================================================
-- PAYMENT REQUESTS TABLE INDEXES
-- ============================================================================
-- Used for payment request filtering, status checks, and agent queries

CREATE INDEX IF NOT EXISTS idx_payment_requests_payment_account ON payment_requests(payment_account_id);
CREATE INDEX IF NOT EXISTS idx_payment_requests_savings_account ON payment_requests(savings_account_id);
CREATE INDEX IF NOT EXISTS idx_payment_requests_status ON payment_requests(status);
CREATE INDEX IF NOT EXISTS idx_payment_requests_created_at ON payment_requests(created_at);

-- Composite index for agent/admin queries
CREATE INDEX IF NOT EXISTS idx_payment_requests_status_created ON payment_requests(status, created_at);

-- ============================================================================
-- COMMISSIONS TABLE INDEXES
-- ============================================================================
-- Used for agent commission calculations and reporting

CREATE INDEX IF NOT EXISTS idx_commissions_agent ON commissions(agent_id);
CREATE INDEX IF NOT EXISTS idx_commissions_savings_account ON commissions(savings_account_id);
CREATE INDEX IF NOT EXISTS idx_commissions_date ON commissions(commission_date);

-- Composite index for agent commission queries
CREATE INDEX IF NOT EXISTS idx_commissions_agent_date ON commissions(agent_id, commission_date);

-- ============================================================================
-- SETTINGS TABLE INDEXES
-- ============================================================================
-- Used for user settings lookups
-- Note: Only create if table exists

DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'settings') THEN
        CREATE INDEX IF NOT EXISTS idx_settings_user_id ON settings(user_id);
    END IF;
END $$;

-- ============================================================================
-- EXPENSE CARDS TABLE INDEXES
-- ============================================================================
-- Used for customer expense card lookups
-- Note: Only create if table and columns exist

DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'expense_cards') THEN
        -- Check if customer_id column exists
        IF EXISTS (SELECT FROM information_schema.columns 
                   WHERE table_name = 'expense_cards' AND column_name = 'customer_id') THEN
            CREATE INDEX IF NOT EXISTS idx_expense_cards_customer ON expense_cards(customer_id);
        END IF;
        
        -- Check if savings_account_id column exists
        IF EXISTS (SELECT FROM information_schema.columns 
                   WHERE table_name = 'expense_cards' AND column_name = 'savings_account_id') THEN
            CREATE INDEX IF NOT EXISTS idx_expense_cards_savings_account ON expense_cards(savings_account_id);
        END IF;
    END IF;
END $$;

-- ============================================================================
-- EXPENSES TABLE INDEXES
-- ============================================================================
-- Used for expense tracking and reporting
-- Note: Only create if table and columns exist

DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'expenses') THEN
        -- Check if expense_card_id column exists
        IF EXISTS (SELECT FROM information_schema.columns 
                   WHERE table_name = 'expenses' AND column_name = 'expense_card_id') THEN
            CREATE INDEX IF NOT EXISTS idx_expenses_card ON expenses(expense_card_id);
        END IF;
        
        -- Check if date column exists
        IF EXISTS (SELECT FROM information_schema.columns 
                   WHERE table_name = 'expenses' AND column_name = 'date') THEN
            CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
        END IF;
        
        -- Check if category column exists
        IF EXISTS (SELECT FROM information_schema.columns 
                   WHERE table_name = 'expenses' AND column_name = 'category') THEN
            CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
        END IF;
    END IF;
END $$;

-- ============================================================================
-- RELATIONSHIP TABLES INDEXES
-- ============================================================================
-- Used for user-business and user-unit relationship queries

-- User-Business relationships
CREATE INDEX IF NOT EXISTS idx_user_business_user ON user_business(user_id);
CREATE INDEX IF NOT EXISTS idx_user_business_business ON user_business(business_id);

-- User-Units relationships
CREATE INDEX IF NOT EXISTS idx_user_units_user ON user_units(user_id);
CREATE INDEX IF NOT EXISTS idx_user_units_unit ON user_units(unit_id);

-- ============================================================================
-- COMMIT TRANSACTION
-- ============================================================================

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these queries to verify indexes were created successfully

-- Show all indexes in the database
-- SELECT schemaname, tablename, indexname, indexdef 
-- FROM pg_indexes 
-- WHERE schemaname = 'public' 
-- ORDER BY tablename, indexname;

-- Check index usage statistics (run after system has been running for a while)
-- SELECT schemaname, tablename, indexname, idx_scan, idx_tup_read, idx_tup_fetch
-- FROM pg_stat_user_indexes
-- WHERE schemaname = 'public'
-- ORDER BY idx_scan DESC;

-- ============================================================================
-- NOTES
-- ============================================================================
-- 1. These indexes are designed for read-heavy workloads
-- 2. Indexes will slightly slow down INSERT/UPDATE operations (trade-off)
-- 3. Monitor index usage with pg_stat_user_indexes
-- 4. Consider dropping unused indexes after monitoring
-- 5. Rebuild indexes periodically: REINDEX TABLE table_name;
-- 6. Analyze tables after creating indexes: ANALYZE;
-- ============================================================================

-- Run ANALYZE to update query planner statistics
DO $$
BEGIN
    ANALYZE users;
    ANALYZE businesses;
    ANALYZE savings_accounts;
    ANALYZE savings_markings;
    ANALYZE payment_accounts;
    ANALYZE account_details;
    ANALYZE payment_requests;
    ANALYZE commissions;
    
    -- Only analyze settings if it exists
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'settings') THEN
        ANALYZE settings;
    END IF;
    
    -- Only analyze expense tables if they exist
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'expense_cards') THEN
        ANALYZE expense_cards;
    END IF;
    
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'expenses') THEN
        ANALYZE expenses;
    END IF;
    
    ANALYZE user_business;
    ANALYZE user_units;
END $$;

-- Success message
SELECT 'Performance indexes created successfully! Total indexes: 40+' AS result;

