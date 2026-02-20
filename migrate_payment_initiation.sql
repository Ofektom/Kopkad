-- Migration: Create payment_initiations Table
-- Date: 2026-02-20

DO $$ BEGIN
    CREATE TYPE payment_initiation_status AS ENUM (
        'pending',
        'completed',
        'failed',
        'cancelled'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS payment_initiations (
    id                  BIGSERIAL PRIMARY KEY,
    idempotency_key     VARCHAR(255) NOT NULL UNIQUE,
    reference           VARCHAR(100) NOT NULL,
    status              payment_initiation_status NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    savings_account_id  BIGINT REFERENCES savings_accounts(id) ON DELETE SET NULL,
    savings_marking_id  BIGINT REFERENCES savings_markings(id) ON DELETE SET NULL,
    
    payment_method      VARCHAR(50),
    metadata            JSONB
);

CREATE INDEX IF NOT EXISTS idx_payment_initiations_idempotency_key 
    ON payment_initiations (idempotency_key);

CREATE INDEX IF NOT EXISTS idx_payment_initiations_reference 
    ON payment_initiations (reference);

CREATE INDEX IF NOT EXISTS idx_payment_initiations_status 
    ON payment_initiations (status);

CREATE INDEX IF NOT EXISTS idx_payment_initiations_user_id 
    ON payment_initiations (user_id);

CREATE INDEX IF NOT EXISTS idx_payment_initiations_savings_account_id 
    ON payment_initiations (savings_account_id);

CREATE INDEX IF NOT EXISTS idx_payment_initiations_savings_marking_id 
    ON payment_initiations (savings_marking_id);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM pg_trigger 
        WHERE tgname = 'update_payment_initiations_updated_at'
    ) THEN
        CREATE TRIGGER update_payment_initiations_updated_at
        BEFORE UPDATE ON payment_initiations
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- Verification (optional, run manually after execution)
SELECT 'Table exists' AS check, 
       EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'payment_initiations') AS result;

SELECT 'Columns' AS check, 
       column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'payment_initiations' 
ORDER BY ordinal_position;

SELECT 'Foreign keys' AS check, 
       constraint_name 
FROM information_schema.table_constraints 
WHERE table_name = 'payment_initiations' 
AND constraint_type = 'FOREIGN KEY';

SELECT 'Indexes count' AS check, 
       COUNT(*) 
FROM pg_indexes 
WHERE tablename = 'payment_initiations';