-- Candidate only. Apply separately after D1 schema admission; never run by this branch.
CREATE TABLE media_asset(
  media_asset_id TEXT PRIMARY KEY,
  raw_sha256 TEXT NOT NULL UNIQUE,
  object_key TEXT NOT NULL UNIQUE,
  object_size INTEGER NOT NULL CHECK(object_size > 0),
  normalized_pixel_hash TEXT NOT NULL,
  perceptual_fingerprint TEXT NOT NULL,
  width INTEGER NOT NULL CHECK(width > 0),
  height INTEGER NOT NULL CHECK(height > 0),
  mime TEXT NOT NULL,
  provenance_class TEXT NOT NULL,
  provenance_confidence TEXT NOT NULL CHECK(provenance_confidence IN ('VERIFIED','PARTIAL','UNKNOWN')),
  earlier_source_status TEXT NOT NULL,
  parent_asset_id TEXT REFERENCES media_asset(media_asset_id),
  producing_activity TEXT NOT NULL,
  truth_eligibility TEXT NOT NULL CHECK(truth_eligibility IN ('FULL','FIELD_SCOPED','LIMITED','FORBIDDEN','TRUTH_UNRESOLVED')),
  first_seen_at TEXT NOT NULL,
  source_lineage TEXT NOT NULL,
  task_lineage TEXT NOT NULL,
  independent_evidence_id TEXT,
  CHECK(parent_asset_id IS NULL OR parent_asset_id <> media_asset_id)
);
CREATE INDEX media_asset_source_lineage_idx ON media_asset(source_lineage);
CREATE TABLE creative_media_ref(
  creative_ref_id TEXT PRIMARY KEY,
  media_asset_id TEXT NOT NULL REFERENCES media_asset(media_asset_id),
  vehicle_instance_id TEXT NOT NULL,
  target_column TEXT NOT NULL,
  channels_json TEXT NOT NULL,
  admitted_at TEXT NOT NULL,
  UNIQUE(media_asset_id, vehicle_instance_id)
);
