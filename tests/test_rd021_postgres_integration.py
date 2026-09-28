"""Real PostgreSQL contract lane; never connects to a non-local database."""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import psycopg
import pytest
from psycopg.types.json import Jsonb

from global_hybrid_v2.canonical_cutover import (
    compile_import,
    declare_db_canonical,
    import_fixed_preimage,
    mark_prewrite_rollback,
    rollback_eligibility,
    verify_import,
)
from global_hybrid_v2.canonical_projection import ProjectionOutboxWorker, XlsxProjectionVerifier
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import PersistenceDisposition
from global_hybrid_v2.inventory_identity import (
    AuthoritativeInventoryResolver,
    BindingState,
    SqlInventoryBindingStore,
    read_current_snapshot,
)
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalConflict,
    CanonicalMutation,
    CreativeAdmission,
    FieldEvidence,
    TransactionalVehicleStore,
    _digest,
)
from tests._rd021_projection_fixture import AtomicProjectionFixture
from tests.rd021_postgres_qualification import (
    PostgresTestTargetBlocked,
    guarded_dsn,
    introspect_schema,
    reset_and_migrate,
)
from tests.test_rd021_completion_fence import q
from tests.test_rd021_creative_schema_migration import edit_sheet
from tests.test_rd021_inventory_identity import TURN, EvidenceFixture, SourceFixture, evidence
from tests.test_rd021_media_admission import creative_workbook
from tests.test_rd021_source_observation import observation_workbook

VEHICLE = "8891:S4806251"


def test_inventory_identity_admission_reuses_observation_table_on_real_postgres(pg):
    dsn, _, _ = pg
    with psycopg.connect(dsn) as connection:
        connection.execute(
            "INSERT INTO vehicle_record (vehicle_instance_id, revision, durable_identity, "
            "source_snapshot, verified_state, source_row) "
            "VALUES (%s, 0, %s, '{}', '{}', 2)",
            ("vehicle-1", Jsonb({"VIN/車身號碼": "VIN-1"})),
        )
    binding = SqlInventoryBindingStore(lambda: psycopg.connect(dsn), dialect="postgres")
    snapshot = read_current_snapshot(SourceFixture())
    candidate = AuthoritativeInventoryResolver(binding, EvidenceFixture()).resolve(TURN, snapshot)
    assert candidate.binding_state is BindingState.INSTANCE_CANDIDATE
    assert candidate.vehicle_instance_id is None
    resolver = AuthoritativeInventoryResolver(binding, EvidenceFixture((evidence(),)))
    bound = resolver.resolve(TURN, snapshot)
    assert bound.binding_state is BindingState.INSTANCE_BOUND
    assert resolver.resolve(TURN, snapshot).vehicle_instance_id == "vehicle-1"
    with psycopg.connect(dsn) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_record").fetchone() == (1,)
        assert connection.execute(
            "SELECT binding_state, vehicle_instance_id FROM vehicle_source_observation "
            "WHERE source_observation_id = %s", (bound.source_observation_id,),
        ).fetchone() == ("INSTANCE_BOUND", "vehicle-1")


def full_observation_contract():
    from global_hybrid_v2.workbench_mutation import _cell, _set_cell

    def add_bound_rows(root):
        sheet = root.find(q("sheetData"))
        existing = {int(row.get("r")) for row in sheet}
        for number in range(2, 16):
            if number in existing:
                continue
            row = ET.SubElement(sheet, q("row"), {"r": str(number)})
            _set_cell(_cell(row, 1, create=True), f"contract-vehicle:{number}")
            _set_cell(_cell(row, 6, create=True), f"source:{number}")
        sheet[:] = sorted(sheet, key=lambda row: int(row.get("r")))

    return edit_sheet(observation_workbook(), add_bound_rows)


@pytest.mark.parametrize("tampered_column", ["source_file_id", "source_sha256"])
def test_full_observation_import_and_provenance_falsifier(pg, tampered_column):
    dsn, store, _ = pg
    raw = full_observation_contract()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert (manifest.observation_count, manifest.vehicle_count,
            manifest.unbound_observation_count) == (14, 11, 3)
    receipt = import_fixed_preimage(store, raw, manifest)
    assert verify_import(store, manifest) == receipt
    assert query(dsn, "SELECT count(*) FROM vehicle_record") == [(11,)]
    assert query(dsn, "SELECT source_row FROM vehicle_source_observation "
                      "WHERE vehicle_instance_id IS NULL ORDER BY source_row") == [(3,), (8,), (15,)]
    assert query(dsn, "SELECT count(*) FROM vehicle_record WHERE source_row IN (3,8,15)") == [(0,)]
    rows = query(dsn, "SELECT source_observation_id, source_row, source_file_id, source_sha256, "
                     "source_snapshot, vehicle_instance_id FROM vehicle_source_observation "
                     "ORDER BY source_row")
    assert rows == [(o.source_observation_id, o.source_row, manifest.source_file_id,
                     manifest.source_sha256, o.state, o.vehicle_instance_id)
                    for o in manifest.observations]
    with psycopg.connect(dsn) as connection:
        connection.execute(f"UPDATE vehicle_source_observation SET {tampered_column} = %s "
                           "WHERE source_row = 3", ("tampered",))
    assert query(dsn, "SELECT source_file_id, source_sha256 FROM canonical_cutover") == [
        (manifest.source_file_id, manifest.source_sha256)]
    with pytest.raises(CanonicalConflict, match="^HOLD_MIGRATION_MISMATCH$"):
        verify_import(store, manifest)


def test_observation_insert_failure_rolls_back_import(pg):
    dsn, store, _ = pg
    raw = full_observation_contract()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    with psycopg.connect(dsn) as connection:
        connection.execute("CREATE FUNCTION fail_observation() RETURNS trigger LANGUAGE plpgsql AS $$ "
                           "BEGIN IF NEW.source_row = 15 THEN RAISE EXCEPTION 'injected observation'; "
                           "END IF; RETURN NEW; END; $$")
        connection.execute("CREATE TRIGGER fail_observation BEFORE INSERT ON vehicle_source_observation "
                           "FOR EACH ROW EXECUTE FUNCTION fail_observation()")
    with pytest.raises(psycopg.Error, match="injected observation"):
        import_fixed_preimage(store, raw, manifest)
    for table in ("vehicle_record", "vehicle_source_observation", "canonical_cutover"):
        assert query(dsn, f"SELECT count(*) FROM {table}") == [(0,)]


class ServerAdmission:
    def __init__(self):
        self.known: dict[tuple[str, str, str, str], FieldEvidence] = {}

    def add(self, vehicle: str, evidence: FieldEvidence) -> None:
        self.known[(vehicle, evidence.field_name, evidence.value_digest,
                    evidence.evidence_asset_id)] = evidence

    def resolve(self, *, vehicle_instance_id, field_name, value_digest, evidence_asset_id):
        return self.known.get((vehicle_instance_id, field_name, value_digest, evidence_asset_id))


def mutation(*, vehicle=VEHICLE, mid="m1", revision=0, field="實際配備狀態",
             value="sport", asset="media:1", root="root:1", truth="LIMITED",
             provenance="FIRST_OBSERVED_EXTERNAL", scope=None):
    evidence = FieldEvidence(field, _digest(value), asset, root, "VERIFIED",
                             scope or (field,), truth, provenance,
                             "UNKNOWN" if provenance == "FIRST_OBSERVED_EXTERNAL" else "VERIFIED",
                             "extractor:1", "verifier:1")
    return CanonicalMutation(mid, vehicle, revision, {field: value}, (evidence,),
                             "request:1", "task:1")


def creative(*, mid="creative:m1", revision=0, asset="media:generated", channels=("FB", "8891")):
    return CreativeAdmission(mid, VEHICLE, revision, asset, "root:generated", "AI_GENERATED",
                             "FORBIDDEN", channels, "request:creative", "task:creative")


@pytest.fixture
def pg():
    if not os.environ.get("RD021_TEST_POSTGRES_DSN") and os.environ.get("RD021_REQUIRE_POSTGRES") != "1":
        pytest.skip("real PostgreSQL is exclusively required in postgres-contract")
    dsn = guarded_dsn()
    reset_and_migrate(dsn)
    admission = ServerAdmission()
    store = TransactionalVehicleStore.postgres_candidate(dsn, evidence_admission=admission)
    return dsn, store, admission


@pytest.fixture
def imported(pg):
    dsn, store, admission = pg
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert import_fixed_preimage(store, raw, manifest).state == "IMPORT_READBACK_PASS"
    declare_db_canonical(store, manifest)
    return dsn, store, admission, raw, manifest


def query(dsn, sql, params=()):
    guarded_dsn(dsn)
    with psycopg.connect(dsn, autocommit=False) as connection:
        return connection.execute(sql, params).fetchall()


def counts(dsn):
    return tuple(query(dsn, f"SELECT count(*) FROM {name}")[0][0] for name in (
        "vehicle_field_evidence", "vehicle_mutation", "projection_outbox"))


def admitted(store, admission, item):
    admission.add(item.vehicle_instance_id, item.evidence[0])
    return store.commit_verified(item)


@pytest.mark.parametrize("dsn", [None, "postgresql://u:p@render.example.com:5432/rd021_test",
                                    "postgresql://postgres:postgres@localhost:5432/prod",
                                    "postgresql://postgres:postgres@localhost:5432/rd021_test?hostaddr=1.2.3.4"])
def test_target_guard_rejects_non_ephemeral(dsn):
    with pytest.raises(PostgresTestTargetBlocked, match="POSTGRES_TEST_TARGET_NOT_EPHEMERAL"):
        guarded_dsn(dsn or "")


def test_migration_chain_catalog_introspection_and_real_psycopg(pg):
    dsn, store, _ = pg
    assert store.dialect == "postgres"
    introspect_schema(dsn)
    assert query(dsn, "SELECT current_database()")[0][0] == "rd021_test"
    assert query(dsn, "SHOW server_version")[0][0].startswith("18.")


def test_import_parity_and_cutover_fresh_connection(pg):
    dsn, store, _ = pg
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert import_fixed_preimage(store, raw, manifest).state == "IMPORT_READBACK_PASS"
    assert verify_import(store, manifest).imported_state_digest == manifest.state_digest
    assert query(dsn, "SELECT source_sha256, source_state_digest, source_vehicle_count, state "
                      "FROM canonical_cutover")[0] == (
        manifest.source_sha256, manifest.state_digest, 2, "IMPORTED")
    imported_ids = [row[0] for row in query(
        dsn, "SELECT vehicle_instance_id FROM vehicle_record ORDER BY source_row"
    )]
    assert imported_ids == [v.vehicle_instance_id for v in manifest.vehicles]
    assert rollback_eligibility(store) == "ROLLBACK_TO_FROZEN_XLSX_PREIMAGE_ELIGIBLE"
    declare_db_canonical(store, manifest)
    assert query(dsn, "SELECT state FROM canonical_cutover")[0][0] == "DB_CANONICAL"
    with pytest.raises(CanonicalConflict, match="CUTOVER_STATE_CONFLICT"):
        declare_db_canonical(store, manifest)


def test_import_negative_cases_are_atomic(pg):
    dsn, store, _ = pg
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    with pytest.raises(CanonicalConflict, match="MIGRATION_MISMATCH"):
        import_fixed_preimage(store, raw + b"changed", manifest)
    assert query(dsn, "SELECT count(*) FROM vehicle_record")[0][0] == 0
    assert import_fixed_preimage(store, raw, manifest).state == "IMPORT_READBACK_PASS"
    with pytest.raises(CanonicalConflict, match="TARGET_NOT_EMPTY"):
        import_fixed_preimage(store, raw, manifest)
    with psycopg.connect(dsn) as connection:
        connection.execute("DELETE FROM vehicle_source_observation WHERE "
                           "vehicle_instance_id = 'gran-turismo'")
        connection.execute("DELETE FROM vehicle_record WHERE vehicle_instance_id = 'gran-turismo'")
    with pytest.raises(CanonicalConflict, match="MIGRATION_MISMATCH"):
        verify_import(store, manifest)


def test_import_rejects_changed_cell_duplicate_identity_and_creative_baseline(pg):
    dsn, store, _ = pg
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)

    def changed(root):
        row = next(item for item in root.find(q("sheetData")).findall(q("row"))
                   if item.get("r") == "13")
        cell = next(item for item in row.findall(q("c")) if item.get("r") == "B13")
        cell.find(f"{q('is')}/{q('t')}").text = "changed"

    with pytest.raises(CanonicalConflict, match="MIGRATION_MISMATCH"):
        import_fixed_preimage(store, edit_sheet(raw, changed), manifest)
    with pytest.raises(CanonicalConflict, match="MIGRATION_MISMATCH"):
        import_fixed_preimage(store, raw, replace(manifest, state_digest="0" * 64))

    def duplicate(root):
        row = next(item for item in root.find(q("sheetData")).findall(q("row"))
                   if item.get("r") == "11")
        cell = next(item for item in row.findall(q("c")) if item.get("r") == "A11")
        cell.find(f"{q('is')}/{q('t')}").text = VEHICLE

    with pytest.raises(CanonicalConflict, match="IDENTITY_DUPLICATE"):
        compile_import(edit_sheet(raw, duplicate), file_id=CANONICAL_WORKBENCH_FILE_ID)

    def unresolved_creative(root):
        row = next(item for item in root.find(q("sheetData")).findall(q("row"))
                   if item.get("r") == "13")
        from global_hybrid_v2.workbench_mutation import _cell, _set_cell

        _set_cell(_cell(row, 6, create=True), "creative:unresolved")

    with pytest.raises(CanonicalConflict, match="CREATIVE_LINKAGE_REQUIRED"):
        compile_import(edit_sheet(raw, unresolved_creative), file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert query(dsn, "SELECT count(*) FROM vehicle_record")[0][0] == 0


def test_transaction_commit_and_fresh_durability(imported):
    dsn, store, admission, _, _ = imported
    receipt = admitted(store, admission, mutation())
    assert receipt.state is PersistenceDisposition.WRITE_AND_READBACK_PASS
    assert receipt.postwrite_version == "1"
    assert query(dsn, "SELECT revision, verified_state FROM vehicle_record WHERE vehicle_instance_id = %s",
                 (VEHICLE,))[0] == (1, {"實際配備狀態": "sport"})
    assert counts(dsn) == (1, 1, 1)
    assert query(dsn, "SELECT state FROM projection_outbox")[0][0] == "PROJECTION_PENDING"


@pytest.mark.parametrize("table", ["vehicle_field_evidence", "vehicle_mutation", "projection_outbox"])
def test_intermediate_failure_rolls_back_every_component(imported, table):
    dsn, store, admission, _, _ = imported
    with psycopg.connect(dsn) as connection:
        connection.execute("CREATE FUNCTION rd021_fail() RETURNS trigger LANGUAGE plpgsql AS $$ "
                           "BEGIN RAISE EXCEPTION 'injected'; END; $$")
        connection.execute(f"CREATE TRIGGER rd021_fail BEFORE INSERT ON {table} "
                           "FOR EACH ROW EXECUTE FUNCTION rd021_fail()")
    admission.add(VEHICLE, mutation().evidence[0])
    with pytest.raises(psycopg.Error, match="injected"):
        store.commit_verified(mutation())
    assert query(dsn, "SELECT revision, verified_state FROM vehicle_record "
                      "WHERE vehicle_instance_id = %s", (VEHICLE,))[0] == (0, {})
    assert counts(dsn) == (0, 0, 0)


def test_stale_cas_and_idempotency(imported):
    dsn, store, admission, _, _ = imported
    first = mutation()
    receipt = admitted(store, admission, first)
    assert store.commit_verified(first) == receipt
    collision = mutation(value="other")
    admission.add(VEHICLE, collision.evidence[0])
    with pytest.raises(CanonicalConflict, match="HOLD_IDEMPOTENCY_COLLISION"):
        store.commit_verified(collision)
    stale = mutation(mid="stale", value="other")
    admission.add(VEHICLE, stale.evidence[0])
    with pytest.raises(CanonicalConflict, match="STALE_CANONICAL_REVISION"):
        store.commit_verified(stale)
    assert query(dsn, "SELECT revision FROM vehicle_record WHERE vehicle_instance_id = %s",
                 (VEHICLE,))[0][0] == 1
    assert counts(dsn) == (1, 1, 1)


def test_concurrent_cas_exactly_one_winner(imported):
    dsn, store, admission, _, _ = imported
    for round_number in range(10):
        revision = round_number
        items = [mutation(mid=f"race:{round_number}:{i}", revision=revision,
                          value=f"winner:{round_number}:{i}", asset=f"media:{round_number}:{i}",
                          root=f"root:{round_number}:{i}") for i in range(2)]
        for item in items:
            admission.add(VEHICLE, item.evidence[0])
        barrier = Barrier(2)

        def write(item, ready=barrier):
            ready.wait(timeout=10)
            try:
                return store.commit_verified(item).state.value
            except CanonicalConflict as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, items))
        assert results.count("WRITE_AND_READBACK_PASS") == 1
        assert results.count("STALE_CANONICAL_REVISION") == 1
        assert query(dsn, "SELECT revision FROM vehicle_record WHERE vehicle_instance_id = %s",
                     (VEHICLE,))[0][0] == revision + 1
        assert counts(dsn) == (revision + 1,) * 3


def test_first_observed_and_server_admission_mismatch(imported):
    dsn, store, admission, _, _ = imported
    trusted = mutation()
    admission.add(VEHICLE, trusted.evidence[0])
    for altered in (replace(trusted.evidence[0], independent_evidence_root="caller:root"),
                    replace(trusted.evidence[0], evidence_asset_id="caller:asset")):
        with pytest.raises(CanonicalConflict, match="EVIDENCE_READBACK_MISMATCH"):
            store.commit_verified(replace(trusted, evidence=(altered,)))
    changed = mutation(value="caller:value")
    with pytest.raises(CanonicalConflict, match="EVIDENCE_READBACK_MISMATCH"):
        store.commit_verified(changed)
    assert counts(dsn) == (0, 0, 0)
    assert admitted(store, admission, trusted).state is PersistenceDisposition.WRITE_AND_READBACK_PASS
    second = mutation(mid="m2", revision=1, value="sport plus", asset="media:resize")
    second = replace(second, evidence=(replace(second.evidence[0],
                      provenance_class="DERIVATIVE_RESIZE", provenance_confidence="VERIFIED"),))
    admission.add(VEHICLE, second.evidence[0])
    store.commit_verified(second)
    assert store.independent_evidence_count(VEHICLE) == 1
    assert all(e.truth_eligibility == "LIMITED" for e in store.field_evidence(VEHICLE, "實際配備狀態"))


def test_field_scoped_visible_evidence_admits_only_supported_field(imported):
    dsn, store, admission, _, _ = imported
    item = mutation(truth="FIELD_SCOPED")
    admitted(store, admission, item)
    assert store.read_vehicle(VEHICLE).verified_state == {"實際配備狀態": "sport"}
    assert store.field_evidence(VEHICLE, "實際配備狀態")[0].support_scope == ("實際配備狀態",)
    assert counts(dsn) == (1, 1, 1)


def test_limited_identity_field_and_creative_truth_are_forbidden(imported):
    dsn, store, admission, _, _ = imported
    for field in ("VIN/車身號碼", "車牌"):
        item = mutation(mid=f"limited:{field}", field=field, value="X")
        admission.add(VEHICLE, item.evidence[0])
        with pytest.raises(CanonicalConflict):
            store.commit_verified(item)
    for provenance in ("AI_GENERATED", "AI_EDITED", "COMPOSITED"):
        item = mutation(mid=f"creative:{provenance}", provenance=provenance, truth="FORBIDDEN")
        admission.add(VEHICLE, item.evidence[0])
        with pytest.raises(CanonicalConflict):
            store.commit_verified(item)
    assert counts(dsn) == (0, 0, 0)


@pytest.mark.parametrize("field", ["VIN/車身號碼", "車牌"])
def test_identity_unique_constraint_maps_to_product_hold(imported, field):
    dsn, store, admission, _, _ = imported
    first = mutation(vehicle="gran-turismo", mid="identity:first", field=field,
                     value="SAME123", truth="FULL", provenance="ORIGINAL_EVIDENCE")
    second = mutation(mid="identity:second", field=field, value="SAME123", asset="media:2",
                      root="root:2", truth="FULL", provenance="ORIGINAL_EVIDENCE")
    admission.add(first.vehicle_instance_id, first.evidence[0])
    admission.add(second.vehicle_instance_id, second.evidence[0])
    store.commit_verified(first)
    with pytest.raises(CanonicalConflict, match="HOLD_VEHICLE_IDENTITY_CONFLICT"):
        store.commit_verified(second)
    assert query(dsn, "SELECT revision, verified_state FROM vehicle_record "
                      "WHERE vehicle_instance_id = %s", (VEHICLE,))[0] == (0, {})
    assert counts(dsn) == (1, 1, 1)


def test_actual_database_constraints_reject_bad_rows(imported):
    dsn, _, _, _, _ = imported
    cases = [
        ("INSERT INTO vehicle_record (vehicle_instance_id, revision, durable_identity, "
         "source_snapshot, verified_state, source_row) VALUES "
         "('gran-turismo', 0, '{}', '{}', '{}', 99)", psycopg.errors.UniqueViolation),
        ("INSERT INTO vehicle_field_evidence (vehicle_instance_id) VALUES ('missing')",
         psycopg.errors.NotNullViolation),
        ("INSERT INTO vehicle_media_link (vehicle_instance_id, media_asset_id, usage_class, "
         "truth_eligibility, provenance_class, provenance_confidence, independent_evidence_root, "
         "creative_classification, channels) VALUES "
         "('missing', 'x', 'CREATIVE', 'FORBIDDEN', 'AI_GENERATED', 'VERIFIED', 'r', 'CREATIVE', '[]')",
         psycopg.errors.ForeignKeyViolation),
        ("UPDATE vehicle_record SET revision = -1 WHERE vehicle_instance_id = 'gran-turismo'",
         psycopg.errors.CheckViolation),
    ]
    for sql, error in cases:
        with pytest.raises(error), psycopg.connect(dsn) as connection:
            connection.execute(sql)


def test_creative_admission_idempotency_and_projection_materialization(imported):
    dsn, store, _, _, _ = imported
    first = creative()
    assert store.admit_creative(first).postwrite_version == "1"
    assert store.admit_creative(first).postwrite_version == "1"
    assert store.admit_creative(creative(mid="creative:duplicate")).state is PersistenceDisposition.NO_DELTA
    with pytest.raises(CanonicalConflict, match="HOLD_IDEMPOTENCY_COLLISION"):
        store.admit_creative(replace(first, media_asset_id="media:other"))
    with pytest.raises(CanonicalConflict, match="TRUTH_ELIGIBILITY_MISMATCH"):
        store.admit_creative(replace(first, truth_eligibility="FULL"))
    state = store.read_projection_state(VEHICLE)
    assert state.verified_state == {}
    assert state.original_media_refs == ("original:1",)
    assert len(state.creative_media_refs) == 1
    assert state.creative_media_refs[0].channels == ("8891", "FB")
    assert json.loads(state.current_state["銷售素材Refs"]) == [state.creative_media_refs[0].creative_ref_id]
    assert store.independent_evidence_count(VEHICLE) == 0
    assert query(dsn, "SELECT truth_eligibility, creative_classification FROM vehicle_media_link") == [
        ("FORBIDDEN", "CREATIVE")]
    assert counts(dsn) == (0, 1, 1)


def test_latest_state_projection_supersedes_failed_event(imported):
    dsn, store, admission, raw, _ = imported
    first = mutation()
    admitted(store, admission, first)
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    sink.fail_writes = True
    assert worker.run("m1") == "PROJECTION_FAILED"
    second = mutation(mid="m2", revision=1, value="sport plus", asset="media:2")
    admitted(store, admission, second)
    sink.fail_writes = False
    assert worker.run("m1") == "SUPERSEDED_BY_LATER_REVISION"
    assert query(dsn, "SELECT event_id, state, satisfied_by_revision FROM projection_outbox "
                      "ORDER BY canonical_revision") == [
        ("m1", "SUPERSEDED_BY_LATER_REVISION", 2), ("m2", "PROJECTED", 2)]
    assert query(dsn, "SELECT projected_revision FROM vehicle_projection_cursor")[0][0] == 2
    assert worker.run("m2") == "PROJECTED"
    assert sink.write_calls == 2


def test_concurrent_projection_workers_coordinate_for_update(imported):
    dsn, store, admission, raw, _ = imported
    admitted(store, admission, mutation())
    admitted(store, admission, mutation(mid="m2", revision=1, value="sport plus", asset="media:2"))
    sink = AtomicProjectionFixture(raw)
    barrier = Barrier(2)

    def project(event):
        barrier.wait(timeout=10)
        return ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink)).run(event)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(project, ("m1", "m2")))
    assert set(results) == {"PROJECTED", "SUPERSEDED_BY_LATER_REVISION"}
    assert sink.write_calls == 1
    assert query(dsn, "SELECT projected_revision FROM vehicle_projection_cursor")[0][0] == 2


def test_durable_hold_blocks_later_projection(imported):
    dsn, store, admission, raw, _ = imported
    admitted(store, admission, mutation())
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    assert worker.run("m1") == "PROJECTED"
    admitted(store, admission, mutation(mid="m2", revision=1, value="sport plus", asset="media:2"))
    def tamper(root):
        row = next(item for item in root.find(q("sheetData")).findall(q("row"))
                   if item.get("r") == "13")
        cell = next(item for item in row.findall(q("c")) if item.get("r") == "E13")
        cell.find(f"{q('is')}/{q('t')}").text = "external"

    sink.external_edit(tamper)
    assert worker.run("m2") == "HOLD_CONFLICT"
    admitted(store, admission, mutation(mid="m3", revision=2, value="sport max", asset="media:3"))
    assert worker.run("m3") == "HOLD_CONFLICT"
    assert query(dsn, "SELECT state FROM projection_outbox WHERE event_id = 'm2'")[0][0] == "HOLD_CONFLICT"
    assert sink.write_calls == 1


def test_cutover_rollback_boundary(imported):
    dsn, store, admission, _, _ = imported
    assert rollback_eligibility(store) == "ROLLBACK_TO_FROZEN_XLSX_PREIMAGE_ELIGIBLE"
    admitted(store, admission, mutation())
    assert rollback_eligibility(store) == "ROLLBACK_BLOCKED_NEW_CANONICAL_WRITES_PRESENT"
    with pytest.raises(CanonicalConflict, match="ROLLBACK_BLOCKED"):
        mark_prewrite_rollback(store)
    assert query(dsn, "SELECT state FROM canonical_cutover")[0][0] == "DB_CANONICAL"


def test_prewrite_cutover_can_roll_back_but_cannot_write_afterward(imported):
    dsn, store, admission, _, _ = imported
    mark_prewrite_rollback(store)
    assert query(dsn, "SELECT state FROM canonical_cutover")[0][0] == "ROLLED_BACK"
    item = mutation()
    admission.add(VEHICLE, item.evidence[0])
    with pytest.raises(CanonicalConflict, match="HOLD_DB_NOT_CANONICAL"):
        store.commit_verified(item)
    assert counts(dsn) == (0, 0, 0)
