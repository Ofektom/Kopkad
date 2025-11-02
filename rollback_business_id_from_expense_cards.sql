-- Rollback: Remove business_id from expense_cards table
-- Date: 2025-02-11
-- Description: Rollback the business_id column addition

-- Drop the index
DROP INDEX IF EXISTS idx_expense_cards_business_id;

-- Drop the column
ALTER TABLE expense_cards 
DROP COLUMN IF EXISTS business_id;

-- Confirm rollback
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'expense_cards' 
        AND column_name = 'business_id'
    ) THEN
        RAISE NOTICE 'Success: business_id column removed from expense_cards';
    ELSE
        RAISE WARNING 'Warning: business_id column still exists in expense_cards';
    END IF;
END $$;

