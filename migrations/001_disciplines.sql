-- Per-division disciplines master list.
-- Runs on every division DB. Must NOT inject any predefined list here (that would add it
-- to Flame & Gas too). It only creates the table and seeds it from the disciplines this
-- division already uses, so existing divisions (F&G) keep their exact names.
CREATE TABLE IF NOT EXISTS disciplines (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    sort_order INTEGER DEFAULT 100,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Seed the master list from disciplines already assigned in this division's owner map.
INSERT OR IGNORE INTO disciplines (name)
  SELECT DISTINCT TRIM(team_name) FROM resource_teams
  WHERE team_name IS NOT NULL AND TRIM(team_name) != '';
