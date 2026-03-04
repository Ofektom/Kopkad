-- Add cooperative_approved column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS cooperative_approved BOOLEAN NOT NULL DEFAULT FALSE;
