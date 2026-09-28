-- Candidate only. Reuse source observations for Google inventory snapshots.
ALTER TABLE vehicle_source_observation
    ADD COLUMN source_sheet_id integer,
    ADD COLUMN source_sheet_name text,
    ADD COLUMN source_range text,
    ADD COLUMN source_currentness_digest text,
    ADD COLUMN binding_state text NOT NULL DEFAULT 'UNBOUND_OBSERVATION',
    ADD COLUMN is_current boolean NOT NULL DEFAULT true;

UPDATE vehicle_source_observation SET binding_state = 'INSTANCE_BOUND'
    WHERE vehicle_instance_id IS NOT NULL;

ALTER TABLE vehicle_source_observation
    DROP CONSTRAINT vehicle_source_observation_source_row_key;
DROP INDEX vehicle_source_observation_bound_vehicle_unique;

CREATE UNIQUE INDEX vehicle_source_observation_legacy_row_unique
    ON vehicle_source_observation (source_file_id, source_row)
    WHERE source_sheet_id IS NULL;
CREATE UNIQUE INDEX vehicle_source_observation_bound_vehicle_unique
    ON vehicle_source_observation (vehicle_instance_id)
    WHERE vehicle_instance_id IS NOT NULL AND source_sheet_id IS NULL;
CREATE UNIQUE INDEX vehicle_source_observation_snapshot_row_unique
    ON vehicle_source_observation (source_file_id, source_sheet_id, source_row,
                                   source_currentness_digest)
    WHERE source_sheet_id IS NOT NULL;
CREATE UNIQUE INDEX vehicle_source_observation_current_row_unique
    ON vehicle_source_observation (source_file_id, source_sheet_id, source_row)
    WHERE is_current AND source_sheet_id IS NOT NULL;
CREATE UNIQUE INDEX vehicle_source_observation_current_vehicle_unique
    ON vehicle_source_observation (source_file_id, vehicle_instance_id)
    WHERE is_current AND vehicle_instance_id IS NOT NULL;
ALTER TABLE vehicle_source_observation ADD CONSTRAINT vehicle_source_observation_binding_check
    CHECK ((vehicle_instance_id IS NULL AND binding_state <> 'INSTANCE_BOUND')
        OR (vehicle_instance_id IS NOT NULL AND binding_state = 'INSTANCE_BOUND'));
