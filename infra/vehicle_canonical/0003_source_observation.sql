-- Preserve every source row independently of durable vehicle identity.
CREATE TABLE vehicle_source_observation (
    source_observation_id text PRIMARY KEY,
    source_file_id text NOT NULL,
    source_sha256 text NOT NULL,
    source_row integer NOT NULL UNIQUE CHECK (source_row >= 2),
    source_snapshot jsonb NOT NULL,
    vehicle_instance_id text REFERENCES vehicle_record(vehicle_instance_id),
    company_source_state text NOT NULL,
    ai_usage_state text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_observation_id <> ''),
    CHECK (vehicle_instance_id IS NULL OR vehicle_instance_id <> '')
);
CREATE UNIQUE INDEX vehicle_source_observation_bound_vehicle_unique
    ON vehicle_source_observation (vehicle_instance_id)
    WHERE vehicle_instance_id IS NOT NULL;
ALTER TABLE canonical_cutover ADD COLUMN source_observation_count integer
    NOT NULL DEFAULT 0 CHECK (source_observation_count >= 0);
ALTER TABLE canonical_cutover ADD COLUMN bound_vehicle_count integer
    NOT NULL DEFAULT 0 CHECK (bound_vehicle_count >= 0);
ALTER TABLE canonical_cutover ADD COLUMN unbound_observation_count integer
    NOT NULL DEFAULT 0 CHECK (unbound_observation_count >= 0);
