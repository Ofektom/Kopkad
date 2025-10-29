-- Rollback: Remove active_business_id from users table
-- Date: 2025-01-29

-- Drop index
DROP INDEX IF EXISTS idx_users_active_business_id;

-- Drop column
ALTER TABLE users 
DROP COLUMN IF EXISTS active_business_id;

