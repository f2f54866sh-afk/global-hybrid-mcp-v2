-- Candidate-only incremental migration. 0001_transactional_vehicle.sql is unchanged.
ALTER TABLE projection_outbox DROP CONSTRAINT projection_outbox_state_check;
ALTER TABLE projection_outbox ADD CONSTRAINT projection_outbox_state_check
    CHECK (state IN ('PROJECTION_PENDING', 'PROJECTION_FAILED', 'PROJECTED',
                    'SUPERSEDED_BY_LATER_REVISION', 'HOLD_CONFLICT'));
ALTER TABLE projection_outbox ADD COLUMN satisfied_by_revision bigint;
CREATE INDEX projection_outbox_vehicle_revision_idx
    ON projection_outbox (vehicle_instance_id, canonical_revision);
CREATE TABLE vehicle_projection_cursor (
    vehicle_instance_id text PRIMARY KEY REFERENCES vehicle_record(vehicle_instance_id),
    projected_revision bigint NOT NULL CHECK (projected_revision >= 0),
    projected_row_digest text NOT NULL,
    projected_sha256 text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
