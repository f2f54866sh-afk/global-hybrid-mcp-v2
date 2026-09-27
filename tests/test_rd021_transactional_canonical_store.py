from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from global_hybrid_v2.canonical_completion import CanonicalCompanyCommercialCompletionHandler
from global_hybrid_v2.canonical_cutover import (
    compile_import,
    declare_db_canonical,
    import_fixed_preimage,
    mark_prewrite_rollback,
    rollback_eligibility,
    verify_import,
)
from global_hybrid_v2.canonical_projection import (
    DeterministicXlsxProjectionBuilder,
    ProjectionEvent,
    ProjectionOutboxWorker,
    XlsxProjectionVerifier,
)
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import PersistenceDisposition, WorkbenchSyncIntent
from global_hybrid_v2.media_deployment_sequence import DeploymentReceiptAuthority
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalCapabilityDebt,
    CanonicalConflict,
    CanonicalMutation,
    CreativeAdmission,
    FieldEvidence,
    TransactionalVehicleStore,
    _digest,
    sqlite_contract_schema,
)
from tests.test_rd021_completion_fence import q
from tests.test_rd021_creative_schema_migration import edit_sheet
from tests.test_rd021_media_admission import creative_workbook


@pytest.fixture
def candidate(tmp_path):
    path = tmp_path / "candidate.sqlite"
    connection = sqlite3.connect(path)
    sqlite_contract_schema(connection)
    connection.close()
    store = TransactionalVehicleStore(
        lambda: sqlite3.connect(path, timeout=10), dialect="sqlite_test",
        evidence_admission=FixtureEvidenceAdmission(),
    )
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert import_fixed_preimage(store, raw, manifest).state == "IMPORT_READBACK_PASS"
    declare_db_canonical(store, manifest)
    return store, path, raw, manifest


def mutation(*, mutation_id="m1", revision=0, value="sport", asset="media:1",
             root="root:1", truth="LIMITED", provenance="FIRST_OBSERVED_EXTERNAL"):
    field = "實際配備狀態"
    return CanonicalMutation(
        mutation_id, "8891:S4806251", revision, {field: value},
        (FieldEvidence(field, _digest(value), asset, root, "VERIFIED", (field,), truth,
                       provenance, "UNKNOWN", "extractor:1", "verifier:1"),),
        "request:1", "task:1",
    )


class FixtureEvidenceAdmission:
    def resolve(self, *, vehicle_instance_id, field_name, value_digest, evidence_asset_id):
        if vehicle_instance_id != "8891:S4806251" or evidence_asset_id not in {
            "media:1", "media:resized",
        }:
            return None
        provenance = ("FIRST_OBSERVED_EXTERNAL" if evidence_asset_id == "media:1"
                      else "DERIVATIVE_RESIZE")
        return FieldEvidence(field_name, value_digest, evidence_asset_id, "root:1", "VERIFIED",
                             (field_name,), "LIMITED", provenance, "UNKNOWN",
                             "extractor:1", "verifier:1")


def counts(path):
    with sqlite3.connect(path) as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("vehicle_mutation", "vehicle_field_evidence", "projection_outbox"))


def test_revision_cas_atomic_receipt_evidence_and_outbox(candidate):
    store, path, _, _ = candidate
    receipt = store.commit_verified(mutation())
    assert receipt.state is PersistenceDisposition.WRITE_AND_READBACK_PASS
    assert receipt.postwrite_version == "1"
    assert store.read_vehicle("8891:S4806251").verified_state["實際配備狀態"] == "sport"
    evidence = store.field_evidence("8891:S4806251", "實際配備狀態")
    assert evidence[0].provenance_class == "FIRST_OBSERVED_EXTERNAL"
    assert evidence[0].provenance_confidence == "UNKNOWN"
    assert evidence[0].truth_eligibility == "LIMITED"
    assert counts(path) == (1, 1, 1)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT state FROM projection_outbox").fetchone()[0] == (
            "PROJECTION_PENDING"
        )


def test_stale_and_concurrent_writers_one_wins(candidate):
    store, path, _, _ = candidate
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store.commit_verified, mutation(mutation_id=f"m{i}", value=f"v{i}"))
                   for i in range(2)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except CanonicalConflict as exc:
                outcomes.append(str(exc))
    assert sum(not isinstance(result, str) for result in outcomes) == 1
    assert "STALE_CANONICAL_REVISION" in outcomes
    assert counts(path) == (1, 1, 1)
    with pytest.raises(CanonicalConflict, match="STALE_CANONICAL_REVISION"):
        store.commit_verified(mutation(mutation_id="stale"))


def test_idempotent_replay_and_semantic_collision(candidate):
    store, path, _, _ = candidate
    first = store.commit_verified(mutation())
    assert store.commit_verified(mutation()) == first
    assert counts(path) == (1, 1, 1)
    with pytest.raises(CanonicalConflict, match="HOLD_IDEMPOTENCY_COLLISION"):
        store.commit_verified(mutation(value="other"))
    assert counts(path) == (1, 1, 1)


@pytest.mark.parametrize("failed_table", ["vehicle_field_evidence", "vehicle_mutation", "projection_outbox"])
def test_any_transaction_step_failure_rolls_back(candidate, failed_table):
    store, path, _, _ = candidate
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TRIGGER fail_step BEFORE INSERT ON {failed_table} "
                           "BEGIN SELECT RAISE(FAIL, 'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        store.commit_verified(mutation())
    assert store.read_vehicle("8891:S4806251").revision == 0
    assert counts(path) == (0, 0, 0)


def test_no_delta_and_creative_truth_forbidden(candidate):
    store, path, _, _ = candidate
    zero = replace(mutation(), verified_delta={}, evidence=())
    assert store.commit_verified(zero).state is PersistenceDisposition.NO_DELTA
    assert counts(path) == (0, 0, 0)
    with pytest.raises(CanonicalConflict, match="CREATIVE_CANNOT_UPDATE_TRUTH|TRUTH_FORBIDDEN"):
        store.commit_verified(mutation(truth="FORBIDDEN", provenance="AI_GENERATED"))
    assert counts(path) == (0, 0, 0)


def test_limited_first_observed_and_derivative_evidence_root(candidate):
    store, path, _, _ = candidate
    store.commit_verified(mutation())
    store.commit_verified(mutation(mutation_id="m2", revision=1, value="sport plus",
                                   asset="media:resized", root="root:1",
                                   provenance="DERIVATIVE_RESIZE"))
    with sqlite3.connect(path) as connection:
        roots = connection.execute(
            "SELECT independent_evidence_root FROM vehicle_field_evidence"
        ).fetchall()
    assert roots == [("root:1",), ("root:1",)]
    assert len(set(roots)) == 1
    assert store.independent_evidence_count("8891:S4806251") == 1


def test_evidence_claim_is_checked_against_independent_server_readback(candidate):
    store, path, _, _ = candidate
    with pytest.raises(CanonicalConflict, match="EVIDENCE_READBACK_MISMATCH"):
        store.commit_verified(mutation(root="caller:invented"))
    with pytest.raises(CanonicalConflict, match="EVIDENCE_READBACK_MISMATCH"):
        store.commit_verified(mutation(asset="media:unknown"))
    assert counts(path) == (0, 0, 0)


def test_missing_evidence_admission_fails_closed(candidate):
    store, path, _, _ = candidate
    store.evidence_admission = None
    with pytest.raises(CanonicalCapabilityDebt, match="EVIDENCE_ADMISSION_UNAVAILABLE"):
        store.commit_verified(mutation())
    assert counts(path) == (0, 0, 0)


def test_same_verified_vin_cannot_be_assigned_to_two_vehicles(candidate):
    store, path, _, _ = candidate
    field = "VIN/車身號碼"
    value = "WVWZZZ12345678901"

    class VinEvidence:
        def resolve(self, *, vehicle_instance_id, field_name, value_digest, evidence_asset_id):
            return FieldEvidence(field_name, value_digest, evidence_asset_id, evidence_asset_id,
                                 "VERIFIED", (field_name,), "FULL", "ORIGINAL_EVIDENCE",
                                 "VERIFIED", "extractor:vin", "verifier:vin")

    store.evidence_admission = VinEvidence()

    def vin_mutation(vehicle_id, mutation_id):
        asset = f"media:{vehicle_id}"
        evidence = FieldEvidence(field, _digest(value), asset, asset, "VERIFIED", (field,),
                                 "FULL", "ORIGINAL_EVIDENCE", "VERIFIED",
                                 "extractor:vin", "verifier:vin")
        return CanonicalMutation(mutation_id, vehicle_id, 0, {field: value}, (evidence,),
                                 "request:vin", "task:vin")

    store.commit_verified(vin_mutation("gran-turismo", "vin:m1"))
    with pytest.raises(CanonicalConflict, match="HOLD_VEHICLE_IDENTITY_CONFLICT"):
        store.commit_verified(vin_mutation("8891:S4806251", "vin:m2"))
    assert store.read_vehicle("8891:S4806251").revision == 0
    assert counts(path) == (1, 1, 1)


def test_import_exact_parity_missing_or_changed_vehicle_holds(candidate):
    store, path, raw, manifest = candidate
    assert verify_import(store, manifest).vehicle_count == 2
    with pytest.raises(CanonicalConflict, match="HOLD_MIGRATION_MISMATCH"):
        import_fixed_preimage(store, raw + b"tamper", manifest)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM vehicle_record WHERE vehicle_instance_id = ?", ("gran-turismo",))
    with pytest.raises(CanonicalConflict, match="HOLD_MIGRATION_MISMATCH"):
        verify_import(store, manifest)


def test_prewrite_rollback_and_after_write_blocked(tmp_path, candidate):
    store, _, _, _ = candidate
    assert rollback_eligibility(store) == "ROLLBACK_TO_FROZEN_XLSX_PREIMAGE_ELIGIBLE"
    mark_prewrite_rollback(store)
    with pytest.raises(CanonicalConflict, match="HOLD_DB_NOT_CANONICAL"):
        store.commit_verified(mutation())
    other_path = tmp_path / "other.sqlite"
    with sqlite3.connect(other_path) as connection:
        sqlite_contract_schema(connection)
    other = TransactionalVehicleStore(
        lambda: sqlite3.connect(other_path), dialect="sqlite_test",
        evidence_admission=FixtureEvidenceAdmission(),
    )
    raw = creative_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    import_fixed_preimage(other, raw, manifest)
    declare_db_canonical(other, manifest)
    other.commit_verified(mutation())
    assert rollback_eligibility(other) == "ROLLBACK_BLOCKED_NEW_CANONICAL_WRITES_PRESENT"
    with pytest.raises(CanonicalConflict, match="ROLLBACK_BLOCKED"):
        mark_prewrite_rollback(other)


def test_duplicate_identity_import_holds(candidate):
    _, _, raw, _ = candidate
    # Duplicate identity in the fixed XLSX is rejected before any candidate DB write.
    def duplicate(root):
        row = next(item for item in root.find(q("sheetData")).findall(q("row")) if item.get("r") == "11")
        cell = next(item for item in row.findall(q("c")) if item.get("r") == "A11")
        cell.find(f"{q('is')}/{q('t')}").text = "8891:S4806251"

    with pytest.raises(CanonicalConflict, match="IDENTITY_DUPLICATE"):
        compile_import(edit_sheet(raw, duplicate), file_id=CANONICAL_WORKBENCH_FILE_ID)


def test_projection_failure_keeps_canonical_commit_and_retry_is_idempotent(candidate):
    store, path, raw, _ = candidate
    store.commit_verified(mutation())
    state = store.read_vehicle("8891:S4806251")
    assert state.revision == 1

    def projected_sheet(root):
        rows = root.find(q("sheetData")).findall(q("row"))
        header = rows[0]
        from global_hybrid_v2.workbench_mutation import _cell, _set_cell

        _set_cell(_cell(header, 7, create=True), "實際配備狀態")
        _set_cell(_cell(header, 8, create=True), "CANONICAL_REVISION")
        row = next(item for item in rows if item.get("r") == "13")
        _set_cell(_cell(row, 7, create=True), "sport")
        _set_cell(_cell(row, 8, create=True), "1")

    payload = edit_sheet(raw, projected_sheet)

    class ReadOnlyDrive:
        def metadata(self, file_id):
            assert file_id == CANONICAL_WORKBENCH_FILE_ID
            return {"version": "fixture:1"}

        def download(self, file_id):
            return payload

        def replace(self, *args):
            raise AssertionError("readback must never write")

    class Sink:
        fail = True
        calls = 0

        def project(self, event, state):
            self.calls += 1
            if self.fail:
                raise OSError("projection unavailable")

    sink = Sink()
    verifier = XlsxProjectionVerifier(ReadOnlyDrive())
    worker = ProjectionOutboxWorker(store, sink, verifier)
    assert worker.run("m1") == "PROJECTION_FAILED"
    assert store.read_vehicle("8891:S4806251").revision == 1
    sink.fail = False
    assert worker.run("m1") == "PROJECTED"
    assert worker.run("m1") == "PROJECTED"
    assert sink.calls == 2
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT attempts FROM projection_outbox").fetchone()[0] == 2


def test_projection_verifier_rejects_missing_revision_without_writing(candidate):
    store, _, raw, _ = candidate
    store.commit_verified(mutation())

    class ReadOnlyDrive:
        def metadata(self, file_id):
            return {"version": "fixture:1"}

        def download(self, file_id):
            return raw

        def replace(self, *args):
            raise AssertionError("readback must never write")

    with pytest.raises(CanonicalConflict, match="PROJECTION_SCHEMA_MISSING"):
        XlsxProjectionVerifier(ReadOnlyDrive()).verify(
            ProjectionEvent("m1", "8891:S4806251", 1), store.read_vehicle("8891:S4806251")
        )


def test_projection_builder_changes_only_resolved_row(candidate):
    store, _, raw, _ = candidate
    store.commit_verified(mutation())
    from global_hybrid_v2.workbench_mutation import _cell, _set_cell

    def add_projection_columns(root):
        header = root.find(q("sheetData")).findall(q("row"))[0]
        _set_cell(_cell(header, 7, create=True), "實際配備狀態")
        _set_cell(_cell(header, 8, create=True), "CANONICAL_REVISION")

    preimage = edit_sheet(raw, add_projection_columns)
    event = ProjectionEvent("m1", "8891:S4806251", 1)
    state = store.read_vehicle("8891:S4806251")
    output = DeterministicXlsxProjectionBuilder().build(preimage, event, state)

    class ReadOnlyDrive:
        def metadata(self, file_id):
            return {"version": "projection:1"}

        def download(self, file_id):
            return output

        def replace(self, *args):
            raise AssertionError("verifier cannot write")

    verifier = XlsxProjectionVerifier(ReadOnlyDrive())
    assert len(verifier.verify(event, state)) == 64
    authority = DeploymentReceiptAuthority(signing_key=b"k" * 32, issuer="server",
                                           execution_owner="operator")
    receipt = authority.from_xlsx_readback(
        verifier, event=event, state=state, deployment_id="candidate-c",
        target="isolated", source_revision="candidate", expected_preimage="a" * 64,
        previous_step_receipt_digest="b" * 64,
    )
    assert authority.verify(receipt)
    assert receipt.result_state == "PROJECTION_READBACK_PASS"


def test_projection_revision_schema_is_bounded_and_idempotent(candidate):
    _, _, raw, _ = candidate
    builder = DeterministicXlsxProjectionBuilder()
    migrated = builder.add_revision_schema(raw)
    assert migrated != raw
    assert builder.add_revision_schema(migrated) == migrated
    from global_hybrid_v2.workbench_mutation import AI_SHEET, _header, _Workbook

    book = _Workbook.parse(migrated)
    assert _header(book.root(AI_SHEET), book.shared)["CANONICAL_REVISION"] == 7


def test_completion_fence_requires_server_verified_mutation_and_db_readback(candidate):
    store, _, _, _ = candidate
    intent = WorkbenchSyncIntent(
        target_file_id=CANONICAL_WORKBENCH_FILE_ID,
        vehicle_instance_id="8891:S4806251", ai_row=13, safe_attribution=True,
        identity_conflict=False, verified_delta={"實際配備狀態": "sport"},
    )

    class Provider:
        def compile(self, *, task_id, intent):
            assert task_id == "task:1"
            return mutation()

    handler = CanonicalCompanyCommercialCompletionHandler(store=store, verified_mutations=Provider())
    assert handler.consume(task_id="task:1", intent=intent).state is (
        PersistenceDisposition.WRITE_AND_READBACK_PASS
    )
    assert CanonicalCompanyCommercialCompletionHandler(
        store=store, verified_mutations=None
    ).consume(task_id="task:1", intent=intent).state is PersistenceDisposition.PERSISTENCE_CAPABILITY_DEBT


def test_postcommit_readback_mismatch_blocks_normal_completion(candidate, monkeypatch):
    store, _, _, _ = candidate
    original = store.read_vehicle

    def wrong_readback(vehicle_instance_id):
        found = original(vehicle_instance_id)
        if found.revision == 1:
            return replace(found, revision=999)
        return found

    monkeypatch.setattr(store, "read_vehicle", wrong_readback)
    with pytest.raises(CanonicalConflict, match="POSTCOMMIT_READBACK_MISMATCH"):
        store.commit_verified(mutation())


def test_canonical_mode_fails_closed_without_database_or_verified_provider():
    from global_hybrid_v2.application import create_application
    from global_hybrid_v2.settings import Settings

    with pytest.raises(RuntimeError, match="CANONICAL_STORE_BINDING_INCOMPLETE"):
        create_application(settings=Settings(canonical_vehicle_store_mode="postgres"))


def test_creative_admission_is_canonical_link_but_never_vehicle_truth(candidate):
    store, path, _, _ = candidate
    prior = store.read_vehicle("8891:S4806251")
    admission = CreativeAdmission(
        "creative:m1", "8891:S4806251", 0, "media:generated", "root:generated",
        "AI_GENERATED", "FORBIDDEN", ("FB", "8891"), "request:creative", "task:creative",
    )
    assert store.admit_creative(admission).state is PersistenceDisposition.WRITE_AND_READBACK_PASS
    after = store.read_vehicle("8891:S4806251")
    assert after.revision == 1 and after.verified_state == prior.verified_state
    with sqlite3.connect(path) as connection:
        link = connection.execute(
            "SELECT usage_class, truth_eligibility, creative_classification "
            "FROM vehicle_media_link"
        ).fetchone()
    assert link == ("CREATIVE", "FORBIDDEN", "CREATIVE")
    assert store.admit_creative(admission).postwrite_version == "1"
    assert store.admit_creative(replace(admission, admission_id="creative:m2")).state is (
        PersistenceDisposition.NO_DELTA
    )
    assert counts(path) == (1, 0, 1)
    with pytest.raises(CanonicalConflict, match="TRUTH_ELIGIBILITY_MISMATCH"):
        store.admit_creative(replace(admission, truth_eligibility="FULL"))
