-- Migration: Add business_id to expense_cards table
-- Date: 2025-02-11
-- Description: Add business_id column to make expense cards business-centric

-- Add the column (nullable first to allow backfill)
ALTER TABLE expense_cards 
ADD COLUMN IF NOT EXISTS business_id INTEGER REFERENCES businesses(id);

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_expense_cards_business_id ON expense_cards(business_id);

-- Backfill existing records with business_id
-- Strategy 1: Get business_id from linked savings account if exists
UPDATE expense_cards ec
SET business_id = (
    SELECT sa.business_id 
    FROM savings_accounts sa 
    WHERE sa.id = ec.savings_id
)
WHERE ec.business_id IS NULL 
AND ec.savings_id IS NOT NULL;

-- Strategy 2: For remaining records, get user's first/default business
UPDATE expense_cards ec
SET business_id = (
    SELECT ub.business_id 
    FROM user_business ub
    JOIN businesses b ON b.id = ub.business_id
    WHERE ub.user_id = ec.customer_id 
    ORDER BY b.is_default DESC, b.created_at ASC
    LIMIT 1
)
WHERE ec.business_id IS NULL;

-- Strategy 3: Last resort - get user's active_business_id
UPDATE expense_cards ec
SET business_id = (
    SELECT u.active_business_id
    FROM users u
    WHERE u.id = ec.customer_id
    AND u.active_business_id IS NOT NULL
)
WHERE ec.business_id IS NULL;

-- Now make the column NOT NULL (all records should have business_id now)
ALTER TABLE expense_cards 
ALTER COLUMN business_id SET NOT NULL;

-- Add comment
COMMENT ON COLUMN expense_cards.business_id IS 'Business context for this expense card';

-- Verify the migration
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count 
    FROM expense_cards 
    WHERE business_id IS NULL;
    
    IF null_count > 0 THEN
        RAISE WARNING 'Warning: % expense_cards records still have NULL business_id', null_count;
    ELSE
        RAISE NOTICE 'Success: All expense_cards have business_id assigned';
    END IF;
END $$;

