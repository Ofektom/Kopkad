-- ===================================================================
-- ROLLBACK: Business Admin RBAC System
-- Description: Removes admin_credentials, business_permissions tables
--              and admin_id column from businesses
-- Date: 2025-11-04
-- Author: System Migration
-- WARNING: This will delete all admin credentials and business permissions!
-- ===================================================================

\echo '=================================================='
\echo 'Starting ROLLBACK of Business Admin RBAC...'
\echo '=================================================='

BEGIN;

-- ===========================================
-- STEP 1: Drop indexes
-- ===========================================
\echo 'Step 1: Dropping indexes...'

DROP INDEX IF EXISTS idx_businesses_admin_id;
DROP INDEX IF EXISTS idx_admin_credentials_assigned;
DROP INDEX IF EXISTS idx_admin_credentials_business;
DROP INDEX IF EXISTS idx_business_permissions_permission;
DROP INDEX IF EXISTS idx_business_permissions_business;
DROP INDEX IF EXISTS idx_business_permissions_user_business;

-- ===========================================
-- STEP 2: Drop tables
-- ===========================================
\echo 'Step 2: Dropping tables...'

DROP TABLE IF EXISTS business_permissions CASCADE;
DROP TABLE IF EXISTS admin_credentials CASCADE;

-- ===========================================
-- STEP 3: Drop column from businesses
-- ===========================================
\echo 'Step 3: Removing admin_id column from businesses...'

ALTER TABLE businesses DROP COLUMN IF EXISTS admin_id;

COMMIT;

\echo ''
\echo '=================================================='
\echo '✅ Rollback completed successfully!'
\echo 'Business Admin RBAC system has been removed.'
\echo '=================================================='

