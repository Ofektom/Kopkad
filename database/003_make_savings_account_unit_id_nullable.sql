-- Migration: make savings_accounts.unit_id nullable
-- Cooperative businesses (e.g. COOPX1) have no units, so unit_id must allow NULL.
-- The SQLAlchemy model already declares nullable=True; this aligns the DB to match.

ALTER TABLE savings_accounts ALTER COLUMN unit_id DROP NOT NULL;
ALTER TABLE savings_markings ALTER COLUMN unit_id DROP NOT NULL;
