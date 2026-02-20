-- Migration: Rename metadata to payment_metadata in payment_initiations
-- Date: 2026-02-20 (follow-up)

ALTER TABLE payment_initiations
RENAME COLUMN metadata TO payment_metadata;