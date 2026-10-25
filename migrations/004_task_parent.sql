-- Sub-tasks: a task may reference a parent task (one level deep). NULL parent_id = top-level
-- task (all existing tasks remain top-level). This column was already applied out-of-band to
-- flame_gas.db / measurement_solutions.db / test.db on 2026-06-16 under this exact filename
-- (already recorded in their schema_migrations tables, so this file is a no-op there). This
-- commit only fills the gap on dashboards.db and any future new division. Runs on every
-- division DB.
ALTER TABLE tasks ADD COLUMN parent_id INTEGER DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_parent_id ON tasks(parent_id);
