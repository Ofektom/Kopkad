-- ============================================================================
-- Add rejection_reason Column to payment_requests Table
-- ============================================================================
-- Purpose: Allow admins to provide reasons when rejecting payment requests
-- Date: October 19, 2025
-- ============================================================================

BEGIN;

-- Add rejection_reason column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT FROM information_schema.columns 
        WHERE table_name = 'payment_requests' 
        AND column_name = 'rejection_reason'
    ) THEN
        ALTER TABLE payment_requests 
        ADD COLUMN rejection_reason TEXT;
        
        RAISE NOTICE 'Added rejection_reason column to payment_requests table';
    ELSE
        RAISE NOTICE 'rejection_reason column already exists in payment_requests table';
    END IF;
END $$;

COMMIT;

SELECT 'rejection_reason column added successfully!' AS result;

