-- Migration script to add the 'reference' column to the payment_requests table
DO $$
BEGIN
    -- Check if the 'reference' column already exists
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'payment_requests'
        AND column_name = 'reference'
    ) THEN
        -- Add the reference column as VARCHAR(50) NOT NULL
        ALTER TABLE payment_requests
        ADD COLUMN reference VARCHAR(50) NOT NULL;

        -- Update existing rows with a default reference value (e.g., 'PR-<id>-<timestamp>')
        UPDATE payment_requests
        SET reference = CONCAT('PR-', id, '-', EXTRACT(EPOCH FROM created_at)::INTEGER)
        WHERE reference IS NULL;
    ELSE
        RAISE NOTICE 'Column reference already exists in payment_requests table';
    END IF;
END $$;