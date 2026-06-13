-- Per-task threaded comment log. Runs on every division DB.
CREATE TABLE IF NOT EXISTS task_comments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id    INTEGER NOT NULL,
    author     TEXT NOT NULL,
    body       TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'open',   -- 'open' | 'closed'
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at  TEXT,
    closed_by  TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_comments_task_id   ON task_comments(task_id);
CREATE INDEX IF NOT EXISTS idx_task_comments_task_open ON task_comments(task_id, state);
