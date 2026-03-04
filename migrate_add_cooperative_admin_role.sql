-- Migration: Add cooperative_admin to the role enum
-- Run once on the database before deploying the cooperative_admin feature.

ALTER TYPE role ADD VALUE IF NOT EXISTS 'cooperative_admin';
