-- Set search_path to public
SET search_path TO public;

-- Add VIEW_OWN_CONTRIBUTIONS to permission enum
ALTER TYPE permission ADD VALUE IF NOT EXISTS 'view_own_contributions';
