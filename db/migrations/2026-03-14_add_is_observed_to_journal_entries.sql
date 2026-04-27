-- Migration: add is_observed flag to journal_entries
-- Date: 2026-03-14
-- Description: Allows quick-observe checkboxes to be toggled without deleting
--              journal entries. Unchecking now sets is_observed=FALSE instead of
--              deleting the record. Existing entries default to TRUE (observed).

ALTER TABLE public.journal_entries
  ADD COLUMN IF NOT EXISTS is_observed BOOLEAN NOT NULL DEFAULT TRUE;

-- Verify the column was added successfully
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'journal_entries'
  AND column_name  = 'is_observed';
