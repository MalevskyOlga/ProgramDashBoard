-- Per-task attachments: links (URL) or uploaded files. Runs on every division DB.
CREATE TABLE IF NOT EXISTS task_attachments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       INTEGER NOT NULL,
    kind          TEXT NOT NULL,                 -- 'link' | 'file'
    label         TEXT,                          -- display name
    url           TEXT,                          -- for kind='link'
    stored_name   TEXT,                          -- server filename for kind='file'
    original_name TEXT,                          -- original upload name for kind='file'
    size_bytes    INTEGER,
    mime          TEXT,
    uploaded_by   TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_attachments_task_id ON task_attachments(task_id);
