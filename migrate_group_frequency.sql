-- Migration script to add 'bi-weekly' to groupfrequency enum
-- Run with: psql -h <host> -U <user> -d <dbname> -f migrate_group_frequency.sql

BEGIN;

-- Check if 'bi-weekly' exists in the enum, if not add it
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid  
                   WHERE t.typname = 'groupfrequency' AND e.enumlabel = 'bi-weekly') THEN
        ALTER TYPE groupfrequency ADD VALUE 'bi-weekly' AFTER 'weekly';
    END IF;
END$$;

COMMIT;
