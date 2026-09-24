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

CREATE TABLE IF NOT EXISTS scheduler_probe_receipt (
  probe_id TEXT PRIMARY KEY,
  scheduled_at TEXT NOT NULL,
  target_id TEXT NOT NULL CHECK (target_id = 'GLOBAL_HYBRID_RENDER_HEALTH'),
  http_status INTEGER NOT NULL,
  health_ok INTEGER NOT NULL CHECK (health_ok IN (0, 1)),
  attempt_count INTEGER NOT NULL CHECK (attempt_count > 0),
  observed_at TEXT NOT NULL
);
