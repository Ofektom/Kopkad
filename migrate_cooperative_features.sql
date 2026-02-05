-- Set search_path to public
SET search_path TO public;

-- 1. Add COOPERATIVE_MEMBER to role enum
ALTER TYPE role ADD VALUE IF NOT EXISTS 'cooperative_member';

-- 2. Add COOPERATIVE to savingstype enum
ALTER TYPE savingstype ADD VALUE IF NOT EXISTS 'cooperative';

-- 3. Create BusinessType enum
DROP TYPE IF EXISTS businesstype;
CREATE TYPE businesstype AS ENUM ('standard', 'cooperative');

-- 4. Add business_type column to businesses table
ALTER TABLE businesses 
ADD COLUMN IF NOT EXISTS business_type businesstype NOT NULL DEFAULT 'standard';

-- Optional: Update existing businesses to be standard (though default covers this for new rows, existing rows get default)
-- UPDATE businesses SET business_type = 'standard' WHERE business_type IS NULL;
