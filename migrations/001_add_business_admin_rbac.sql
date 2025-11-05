-- ===================================================================
-- MIGRATION: Business Admin RBAC System
-- Description: Add admin_id to businesses, create admin_credentials 
--              and business_permissions tables for business-scoped RBAC
-- Date: 2025-11-04
-- Author: System Migration
-- ===================================================================

\echo '=================================================='
\echo 'Starting Business Admin RBAC Migration...'
\echo '=================================================='

BEGIN;

-- ===========================================
-- STEP 1: Add admin_id to businesses
-- ===========================================
\echo 'Step 1: Adding admin_id column to businesses table...'

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'businesses' AND column_name = 'admin_id'
    ) THEN
        ALTER TABLE businesses ADD COLUMN admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
        RAISE NOTICE 'Added admin_id column to businesses table';
    ELSE
        RAISE NOTICE 'admin_id column already exists in businesses table';
    END IF;
END $$;

COMMENT ON COLUMN businesses.admin_id IS 'Auto-created admin user ID for this business';

-- ===========================================
-- STEP 2: Create admin_credentials table
-- ===========================================
\echo 'Step 2: Creating admin_credentials table...'

CREATE TABLE IF NOT EXISTS admin_credentials (
    id SERIAL PRIMARY KEY,
    business_id INTEGER UNIQUE NOT NULL,
    admin_user_id INTEGER NOT NULL,
    temp_password VARCHAR(255) NOT NULL,
    is_password_changed BOOLEAN DEFAULT FALSE NOT NULL,
    is_assigned BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    
    CONSTRAINT fk_admin_creds_business FOREIGN KEY (business_id) 
        REFERENCES businesses(id) ON DELETE CASCADE,
    CONSTRAINT fk_admin_creds_user FOREIGN KEY (admin_user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

COMMENT ON TABLE admin_credentials IS 
'Stores temporary credentials for auto-created business admin accounts visible to super_admin';

COMMENT ON COLUMN admin_credentials.temp_password IS 
'Encrypted temporary password shown to super_admin once';

COMMENT ON COLUMN admin_credentials.is_assigned IS 
'True when super_admin assigns a person to be admin of the business';

-- ===========================================
-- STEP 3: Create business_permissions table
-- ===========================================
\echo 'Step 3: Creating business_permissions table...'

CREATE TABLE IF NOT EXISTS business_permissions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    business_id INTEGER NOT NULL,
    permission VARCHAR(50) NOT NULL,
    granted_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    
    CONSTRAINT fk_biz_perms_user FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_biz_perms_business FOREIGN KEY (business_id) 
        REFERENCES businesses(id) ON DELETE CASCADE,
    CONSTRAINT fk_biz_perms_grantor FOREIGN KEY (granted_by) 
        REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT unique_user_biz_perm UNIQUE (user_id, business_id, permission)
);

COMMENT ON TABLE business_permissions IS 
'Business-scoped permissions for admins - e.g., approve_payments only for their business';

COMMENT ON COLUMN business_permissions.permission IS 
'Permission values: approve_payments, reject_payments, manage_business, view_business_analytics';

-- ===========================================
-- STEP 4: Create indexes for performance
-- ===========================================
\echo 'Step 4: Creating performance indexes...'

CREATE INDEX IF NOT EXISTS idx_business_permissions_user_business 
ON business_permissions(user_id, business_id);

CREATE INDEX IF NOT EXISTS idx_business_permissions_business 
ON business_permissions(business_id);

CREATE INDEX IF NOT EXISTS idx_business_permissions_permission 
ON business_permissions(permission);

CREATE INDEX IF NOT EXISTS idx_admin_credentials_business 
ON admin_credentials(business_id);

CREATE INDEX IF NOT EXISTS idx_admin_credentials_assigned 
ON admin_credentials(is_assigned);

CREATE INDEX IF NOT EXISTS idx_businesses_admin_id 
ON businesses(admin_id) WHERE admin_id IS NOT NULL;

COMMIT;

-- ===========================================
-- VERIFICATION
-- ===========================================
\echo ''
\echo '=================================================='
\echo 'VERIFICATION RESULTS:'
\echo '=================================================='

SELECT 
    'admin_credentials' as table_name,
    COUNT(*) as row_count,
    'CREATED' as status
FROM admin_credentials
UNION ALL
SELECT 
    'business_permissions' as table_name,
    COUNT(*) as row_count,
    'CREATED' as status
FROM business_permissions
UNION ALL
SELECT 
    'businesses (with admin_id)' as table_name,
    COUNT(*) FILTER (WHERE admin_id IS NOT NULL) as admin_assigned_count,
    'COLUMN ADDED' as status
FROM businesses;

\echo ''
\echo 'Checking indexes...'
SELECT 
    tablename, 
    indexname 
FROM pg_indexes 
WHERE tablename IN ('admin_credentials', 'business_permissions', 'businesses')
  AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;

\echo ''
\echo '✅ Migration 001 completed successfully!'
\echo ''
\echo 'Next steps:'
\echo '1. Update SQLAlchemy models in models/business.py'
\echo '2. Create utils/permissions.py and utils/password_utils.py'
\echo '3. Update service/business.py to auto-create admin'
\echo '4. Restart your FastAPI server'
\echo '=================================================='

