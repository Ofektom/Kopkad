-- ============================================================================
-- Add cancelled status to PaymentRequestStatus enum
-- ============================================================================
-- Purpose: Allow customers to cancel their pending payment requests
-- Date: October 20, 2025
-- ============================================================================

BEGIN;

-- Add 'cancelled' to the paymentrequeststatus enum if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'paymentrequeststatus' AND e.enumlabel = 'cancelled'
    ) THEN
        ALTER TYPE paymentrequeststatus ADD VALUE 'cancelled';
        RAISE NOTICE 'Added cancelled status to paymentrequeststatus enum';
    ELSE
        RAISE NOTICE 'cancelled status already exists in paymentrequeststatus enum';
    END IF;
END $$;

COMMIT;

SELECT 'Payment request status enum updated successfully!' AS result;

