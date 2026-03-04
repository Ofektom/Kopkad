-- Consolidate cooperative_interest + cooperative_approved into a single cooperative_status enum

-- 1. Create the enum type
CREATE TYPE cooperative_status AS ENUM ('none', 'requested', 'approved');

-- 2. Add the new column with default 'none'
ALTER TABLE users ADD COLUMN cooperative_status cooperative_status NOT NULL DEFAULT 'none';

-- 3. Migrate existing data
UPDATE users SET cooperative_status = 'approved'   WHERE cooperative_approved = true;
UPDATE users SET cooperative_status = 'requested'  WHERE cooperative_interest = true AND cooperative_approved = false;

-- 4. Drop old columns
ALTER TABLE users DROP COLUMN IF EXISTS cooperative_interest;
ALTER TABLE users DROP COLUMN IF EXISTS cooperative_approved;
