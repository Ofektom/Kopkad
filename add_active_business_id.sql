-- Migration: Add active_business_id to users table
-- Date: 2025-01-29
-- Description: Add column to track user's currently active business context

-- Add the column
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS active_business_id INTEGER REFERENCES businesses(id);

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_users_active_business_id ON users(active_business_id);

-- Optional: Set default active_business_id for existing users (first business they belong to)
UPDATE users u
SET active_business_id = (
    SELECT business_id 
    FROM user_business 
    WHERE user_id = u.id 
    LIMIT 1
)
WHERE active_business_id IS NULL 
AND EXISTS (
    SELECT 1 FROM user_business WHERE user_id = u.id
);

-- Add comment
COMMENT ON COLUMN users.active_business_id IS 'Currently active business context for the user';

