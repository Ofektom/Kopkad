-- KYC Migration
-- Adds kyc_status to users and creates kyc_verifications table for pre-signup agent/sub-agent tokens

-- 1. Add kyc_status column to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS kyc_status VARCHAR(20) NOT NULL DEFAULT 'none';

-- 2. KYC verification sessions (used for pre-signup biometric verification)
CREATE TABLE IF NOT EXISTS kyc_verifications (
    id               SERIAL PRIMARY KEY,
    phone_number     VARCHAR(20),
    id_type          VARCHAR(10) NOT NULL,
    id_number        VARCHAR(20) NOT NULL,
    full_name        VARCHAR(100),
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',
    smile_reference  VARCHAR(100),
    result_text      TEXT,
    reference_token  VARCHAR(64) UNIQUE NOT NULL,
    used             BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMP DEFAULT NOW(),
    expires_at       TIMESTAMP DEFAULT (NOW() + INTERVAL '30 minutes')
);

CREATE INDEX IF NOT EXISTS idx_kyc_reference_token ON kyc_verifications(reference_token);
