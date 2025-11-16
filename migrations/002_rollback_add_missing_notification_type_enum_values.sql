-- Rollback: Add Missing Notification Type Enum Values
-- Date: 2025-11-16
-- Description: Rollback script for adding notification type enum values
-- Note: PostgreSQL does not support removing enum values directly.
--       If rollback is needed, the enum would need to be recreated from scratch.

\echo '=================================================='
\echo 'Rollback: Notification Type Enum Values'
\echo '=================================================='
\echo ''
\echo '⚠️  WARNING: PostgreSQL does not support removing enum values directly.'
\echo '   This migration cannot be fully rolled back without recreating the enum.'
\echo ''
\echo '   If you need to remove these values, you would need to:'
\echo '   1. Create a new enum with only the values you want'
\echo '   2. Migrate all existing data to use the new enum'
\echo '   3. Drop the old enum and rename the new one'
\echo ''
\echo '   This is a complex operation and should be done with extreme caution.'
\echo ''
\echo '   For now, leaving the enum values in place is safe as they do not'
\echo '   affect existing functionality and only add new capabilities.'
\echo ''
\echo '=================================================='

-- No actual rollback operations - enum values remain in database
-- This is intentional as PostgreSQL enum rollback is complex and risky

