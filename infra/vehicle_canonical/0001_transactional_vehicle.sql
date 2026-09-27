-- RD-021 candidate schema. Apply only to a separately admitted PostgreSQL target.
CREATE TABLE vehicle_record (
    vehicle_instance_id text PRIMARY KEY,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    durable_identity jsonb NOT NULL,
    source_snapshot jsonb NOT NULL,
    verified_state jsonb NOT NULL,
    source_row integer NOT NULL CHECK (source_row >= 2),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX vehicle_record_source_row_unique ON vehicle_record (source_row);
CREATE UNIQUE INDEX vehicle_verified_vin_unique ON vehicle_record ((verified_state->>'VIN/車身號碼'))
    WHERE nullif(verified_state->>'VIN/車身號碼', '') IS NOT NULL;
CREATE UNIQUE INDEX vehicle_verified_plate_unique ON vehicle_record ((verified_state->>'車牌'))
    WHERE nullif(verified_state->>'車牌', '') IS NOT NULL;

CREATE TABLE vehicle_field_evidence (
    vehicle_instance_id text NOT NULL REFERENCES vehicle_record(vehicle_instance_id),
    field_name text NOT NULL,
    value_digest text NOT NULL,
    evidence_asset_id text NOT NULL,
    independent_evidence_root text NOT NULL,
    truth_eligibility text NOT NULL,
    provenance_class text NOT NULL,
    provenance_confidence text NOT NULL,
    verification_state text NOT NULL,
    support_scope text NOT NULL,
    extractor_revision text NOT NULL,
    verifier_revision text NOT NULL,
    first_verified_at timestamptz NOT NULL,
    last_verified_at timestamptz NOT NULL,
    PRIMARY KEY (vehicle_instance_id, field_name, evidence_asset_id, value_digest)
);

CREATE TABLE vehicle_mutation (
    mutation_id text PRIMARY KEY,
    payload_digest text NOT NULL,
    resulting_state_digest text NOT NULL,
    vehicle_instance_id text NOT NULL REFERENCES vehicle_record(vehicle_instance_id),
    expected_revision bigint NOT NULL,
    resulting_revision bigint NOT NULL,
    verified_delta jsonb NOT NULL,
    evidence_refs jsonb NOT NULL,
    request_id text NOT NULL,
    task_id text NOT NULL,
    terminal_disposition text NOT NULL CHECK (terminal_disposition = 'COMMITTED'),
    committed_at timestamptz NOT NULL DEFAULT now(),
    CHECK (resulting_revision = expected_revision + 1)
);

CREATE TABLE vehicle_media_link (
    vehicle_instance_id text NOT NULL REFERENCES vehicle_record(vehicle_instance_id),
    media_asset_id text NOT NULL,
    usage_class text NOT NULL,
    truth_eligibility text NOT NULL,
    provenance_class text NOT NULL,
    provenance_confidence text NOT NULL,
    independent_evidence_root text NOT NULL,
    creative_classification text NOT NULL,
    channels jsonb NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (vehicle_instance_id, media_asset_id, usage_class),
    CHECK (NOT (creative_classification = 'CREATIVE' AND usage_class = 'ORIGINAL_EVIDENCE')),
    CHECK (NOT (truth_eligibility = 'FORBIDDEN' AND usage_class = 'ORIGINAL_EVIDENCE'))
);

CREATE TABLE projection_outbox (
    event_id text PRIMARY KEY REFERENCES vehicle_mutation(mutation_id),
    vehicle_instance_id text NOT NULL REFERENCES vehicle_record(vehicle_instance_id),
    canonical_revision bigint NOT NULL,
    state text NOT NULL DEFAULT 'PROJECTION_PENDING'
        CHECK (state IN ('PROJECTION_PENDING', 'PROJECTION_FAILED', 'PROJECTED')),
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    projected_sha256 text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE canonical_cutover (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    source_file_id text NOT NULL,
    source_sha256 text NOT NULL,
    source_topology_digest text NOT NULL,
    source_state_digest text NOT NULL,
    source_vehicle_count integer NOT NULL,
    state text NOT NULL CHECK (state IN ('IMPORTED', 'DB_CANONICAL', 'ROLLED_BACK')),
    declared_at timestamptz
);
