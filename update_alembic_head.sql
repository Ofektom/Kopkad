-- Update Alembic version table to mark the financial advisor migration as applied
-- This should be run AFTER successfully running migrate_financial_advisor.sql

-- Check current Alembic version
SELECT version_num FROM alembic_version;

-- Update to the new migration version (financial advisor migration)
UPDATE alembic_version SET version_num = '10d827d2f5ba';

-- Verify the update
SELECT 'Alembic head updated to' as status, version_num FROM alembic_version;

