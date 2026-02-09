-- Migration script for Cooperative Savings (SavingsGroup)
-- Run with: psql -h <host> -U <user> -d <dbname> -f migrate_cooperative_savings.sql

BEGIN;

-- 1. Ensure Enums exist and have correct values
DO $$ BEGIN
    CREATE TYPE groupfrequency AS ENUM ('weekly', 'monthly', 'quarterly');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

ALTER TYPE savingstype ADD VALUE IF NOT EXISTS 'cooperative';
ALTER TYPE role ADD VALUE IF NOT EXISTS 'cooperative_member';

DO $$ BEGIN
    CREATE TYPE businesstype AS ENUM ('standard', 'cooperative');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2. Add business_type to businesses if not exists
DO $$ BEGIN
    ALTER TABLE businesses ADD COLUMN business_type businesstype NOT NULL DEFAULT 'standard';
EXCEPTION
    WHEN duplicate_column THEN null;
END $$;

-- 3. Create SavingsGroup table
CREATE TABLE IF NOT EXISTS savings_groups (
    id SERIAL PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES businesses(id),
    name VARCHAR(100) NOT NULL,
    description VARCHAR,
    contribution_amount NUMERIC(10, 2) NOT NULL,
    frequency groupfrequency NOT NULL DEFAULT 'monthly',
    start_date DATE NOT NULL,
    end_date DATE,
    created_by_id INTEGER NOT NULL REFERENCES users(id),
    is_active INTEGER DEFAULT 1,
    
    -- AuditMixin fields
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Indexes for SavingsGroup
CREATE INDEX IF NOT EXISTS ix_savings_groups_business_id ON savings_groups(business_id);
-- ix_savings_groups_id is implicitly created by PRIMARY KEY, but if explicit index is needed:
-- CREATE INDEX IF NOT EXISTS ix_savings_groups_id ON savings_groups(id); 

-- 4. Update SavingsAccount table
ALTER TABLE savings_accounts 
ADD COLUMN IF NOT EXISTS group_id INTEGER REFERENCES savings_groups(id);

COMMIT;
