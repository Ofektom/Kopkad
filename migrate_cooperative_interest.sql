-- migrate_cooperative_interest.sql
-- Adds cooperative_interest flag to users so Central Business customers
-- can signal they want to join a thrift/cooperative group.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'cooperative_interest'
    ) THEN
        ALTER TABLE users
            ADD COLUMN cooperative_interest BOOLEAN NOT NULL DEFAULT FALSE;
        RAISE NOTICE 'Column cooperative_interest added to users.';
    ELSE
        RAISE NOTICE 'Column cooperative_interest already exists, skipping.';
    END IF;
END $$;
