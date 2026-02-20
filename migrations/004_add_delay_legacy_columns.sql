-- 004_add_delay_legacy_columns.sql
-- Restores delay_snapshots legacy columns expected by dashboard/app.py.

BEGIN TRANSACTION;

ALTER TABLE delay_snapshots ADD COLUMN window_from_utc TEXT;
ALTER TABLE delay_snapshots ADD COLUMN window_to_utc TEXT;
ALTER TABLE delay_snapshots ADD COLUMN dep_total INTEGER;
ALTER TABLE delay_snapshots ADD COLUMN dep_qualified_total INTEGER;
ALTER TABLE delay_snapshots ADD COLUMN dep_cancelled INTEGER;
ALTER TABLE delay_snapshots ADD COLUMN dep_median_delay_minutes REAL;
ALTER TABLE delay_snapshots ADD COLUMN dep_delay_index REAL;
ALTER TABLE delay_snapshots ADD COLUMN arr_total INTEGER;
ALTER TABLE delay_snapshots ADD COLUMN arr_qualified_total INTEGER;
ALTER TABLE delay_snapshots ADD COLUMN arr_cancelled INTEGER;
ALTER TABLE delay_snapshots ADD COLUMN arr_median_delay_minutes REAL;
ALTER TABLE delay_snapshots ADD COLUMN arr_delay_index REAL;

COMMIT;
