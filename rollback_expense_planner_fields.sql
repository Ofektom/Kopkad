-- Rollback: Remove Expense Planner Fields
-- Date: 2025-10-21
-- WARNING: This will remove data! Backup first!

-- Step 1: Drop indexes
DROP INDEX IF EXISTS idx_expenses_is_completed;
DROP INDEX IF EXISTS idx_expenses_is_planned;
DROP INDEX IF EXISTS idx_expense_cards_is_plan;
DROP INDEX IF EXISTS idx_expense_cards_status;

-- Step 2: Remove new columns from expenses table
ALTER TABLE expenses
DROP COLUMN IF EXISTS purpose,
DROP COLUMN IF EXISTS planned_amount,
DROP COLUMN IF EXISTS is_completed,
DROP COLUMN IF EXISTS is_planned;

-- Step 3: Remove new columns from expense_cards table
ALTER TABLE expense_cards
DROP COLUMN IF EXISTS is_plan,
DROP COLUMN IF EXISTS status;

-- Step 4: Drop card_status enum type
DROP TYPE IF EXISTS card_status;

-- NOTE: Cannot remove 'PLANNER' from income_type enum easily in PostgreSQL
-- If needed, you must:
-- 1. Create new enum without 'PLANNER'
-- 2. Alter column to use new enum
-- 3. Drop old enum
-- This requires no existing cards with income_type='PLANNER'

