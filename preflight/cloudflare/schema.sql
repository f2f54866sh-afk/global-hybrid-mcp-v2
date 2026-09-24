CREATE TABLE IF NOT EXISTS preflight_tx (
  id TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preflight_dispatch (
  event_id TEXT PRIMARY KEY,
  dispatched_at TEXT NOT NULL,
  github_status INTEGER,
  github_request_id TEXT
);
