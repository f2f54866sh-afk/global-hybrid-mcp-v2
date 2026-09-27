-- Candidate only. Apply separately after D1 schema admission; never run by this branch.
CREATE TABLE media_asset(
  media_asset_id TEXT PRIMARY KEY,
  raw_sha256 TEXT NOT NULL UNIQUE,
  normalized_pixel_hash TEXT NOT NULL,
  perceptual_fingerprint TEXT NOT NULL,
  width INTEGER NOT NULL CHECK(width > 0),
  height INTEGER NOT NULL CHECK(height > 0),
  mime TEXT NOT NULL,
  provenance_class TEXT NOT NULL,
  parent_asset_id TEXT REFERENCES media_asset(media_asset_id),
  producing_activity TEXT NOT NULL,
  truth_eligibility TEXT NOT NULL CHECK(truth_eligibility IN ('TRUTH_ELIGIBLE','TRUTH_FORBIDDEN','TRUTH_UNRESOLVED')),
  first_seen_at TEXT NOT NULL,
  source_lineage TEXT NOT NULL,
  task_lineage TEXT NOT NULL,
  independent_evidence_id TEXT,
  raw_capture_base64 TEXT NOT NULL,
  CHECK(parent_asset_id IS NULL OR parent_asset_id <> media_asset_id)
);
CREATE INDEX media_asset_source_lineage_idx ON media_asset(source_lineage);
