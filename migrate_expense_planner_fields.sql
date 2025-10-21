-- Migration: Add Expense Planner Fields
-- Date: 2025-10-21
-- Description: Add PLANNER income type, card status, and expense tracking fields

-- Step 1: Add PLANNER to income_type enum
ALTER TYPE income_type ADD VALUE IF NOT EXISTS 'PLANNER';

-- Step 2: Create card_status enum type
DO $$ BEGIN
    CREATE TYPE card_status AS ENUM ('DRAFT', 'ACTIVE', 'ARCHIVED');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Step 3: Add new columns to expense_cards table
ALTER TABLE expense_cards 
ADD COLUMN IF NOT EXISTS status card_status NOT NULL DEFAULT 'ACTIVE',
ADD COLUMN IF NOT EXISTS is_plan BOOLEAN NOT NULL DEFAULT FALSE;

-- Step 4: Add new columns to expenses table
ALTER TABLE expenses
ADD COLUMN IF NOT EXISTS is_planned BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS is_completed BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS planned_amount NUMERIC(10, 2),
ADD COLUMN IF NOT EXISTS purpose VARCHAR(255);

-- Step 5: Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_expense_cards_status ON expense_cards(status);
CREATE INDEX IF NOT EXISTS idx_expense_cards_is_plan ON expense_cards(is_plan);
CREATE INDEX IF NOT EXISTS idx_expenses_is_planned ON expenses(is_planned);
CREATE INDEX IF NOT EXISTS idx_expenses_is_completed ON expenses(is_completed);

-- Step 6: Add comments for documentation
COMMENT ON COLUMN expense_cards.status IS 'Card status: DRAFT (planning), ACTIVE (tracking), ARCHIVED (completed)';
COMMENT ON COLUMN expense_cards.is_plan IS 'Quick flag to identify planner/draft cards';
COMMENT ON COLUMN expenses.is_planned IS 'True if this is a planned expense (not yet actually spent)';
COMMENT ON COLUMN expenses.is_completed IS 'True if user checked off this planned item';
COMMENT ON COLUMN expenses.planned_amount IS 'Original planned amount for comparison with actual';
COMMENT ON COLUMN expenses.purpose IS 'Purpose/reason for this expense (from planner)';

-- Step 7: Update existing expense cards to set status (already defaults to ACTIVE)
UPDATE expense_cards SET status = 'ACTIVE' WHERE status IS NULL;

-- Step 8: Set is_plan flag for any existing PLANNER type cards (if any)
UPDATE expense_cards SET is_plan = TRUE WHERE income_type = 'PLANNER';

-- Verification queries (run these after migration)
-- SELECT DISTINCT income_type FROM expense_cards;
-- SELECT DISTINCT status FROM expense_cards;
-- SELECT COUNT(*) FROM expense_cards WHERE is_plan = TRUE;
-- SELECT COUNT(*) FROM expenses WHERE is_planned = TRUE;

