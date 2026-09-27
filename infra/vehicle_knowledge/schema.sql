CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE inventory_source_observation(id TEXT PRIMARY KEY, source_revision TEXT NOT NULL, payload TEXT NOT NULL, observed_at TEXT NOT NULL);
CREATE TABLE inventory_vehicle_row(id TEXT PRIMARY KEY, observation_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_coverage_work(id TEXT PRIMARY KEY, scope_key TEXT NOT NULL, state TEXT NOT NULL);
CREATE TABLE research_evidence_packet(id TEXT PRIMARY KEY, work_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_fact_verification_receipt(id TEXT PRIMARY KEY, work_id TEXT NOT NULL, decision TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_configuration_revision(id TEXT PRIMARY KEY, work_id TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_configuration_fact(id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_fact_source(fact_id TEXT NOT NULL, evidence_id TEXT NOT NULL, PRIMARY KEY(fact_id,evidence_id));
CREATE TABLE vehicle_fact_conflict(id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_snapshot_build(id TEXT PRIMARY KEY, builder_version TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE vehicle_snapshot_promotion(id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, promoted_at TEXT NOT NULL);
CREATE TABLE vehicle_snapshot_active(singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot_id TEXT NOT NULL, promotion_id TEXT NOT NULL);
CREATE TABLE vehicle_reconciliation_run(run_id TEXT PRIMARY KEY, scheduled_at TEXT NOT NULL, body_digest TEXT NOT NULL, state TEXT NOT NULL, claimed_at TEXT NOT NULL, completed_at TEXT NULL, result_state TEXT NULL);
CREATE TABLE workbench_write_claim(
  claim_id TEXT PRIMARY KEY,
  file_id TEXT NOT NULL,
  preimage_version TEXT NOT NULL,
  preimage_sha256 TEXT NOT NULL,
  intent_sha256 TEXT NOT NULL,
  task_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('CLAIMED','COMPLETED','FAILED')),
  claimed_at TEXT NOT NULL,
  completed_at TEXT NULL,
  postwrite_version TEXT NULL,
  postwrite_sha256 TEXT NULL,
  result_state TEXT NULL,
  blocker TEXT NULL,
  UNIQUE(file_id, preimage_version)
);
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
