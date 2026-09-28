"""Candidate inventory identity tests use only isolated SQLite and source fixtures."""
from __future__ import annotations

import json
import sqlite3
import xml.etree.ElementTree as ET

import pytest

from global_hybrid_v2.adapters.google_vehicle_control import COMPANY_INVENTORY_SPREADSHEET_ID
from global_hybrid_v2.canonical_cutover import compile_import, import_fixed_preimage, verify_import
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.inventory_identity import (
    AdmittedDurableIdentity,
    AuthoritativeInventoryResolver,
    BindingState,
    GoogleInventorySource,
    InventoryIdentityHold,
    SourceMetadata,
    SqlInventoryBindingStore,
    TrustedTurnReferent,
    read_current_snapshot,
)
from global_hybrid_v2.transactional_vehicle_store import TransactionalVehicleStore, sqlite_contract_schema
from global_hybrid_v2.workbench_mutation import _cell, _set_cell
from tests.test_rd021_completion_fence import q
from tests.test_rd021_creative_schema_migration import edit_sheet
from tests.test_rd021_source_observation import observation_workbook

META = SourceMetadata(COMPANY_INVENTORY_SPREADSHEET_ID, "2026-09-28T00:00:00Z", 13, "車源")
HEADER = ["", "登記", "驗車", "品牌", "年分", "車型"]
VW = ["11", "", "", "VW", "2021", "TIGUAN R"]
TURN = TrustedTurnReferent("conversation-1", "turn-1", "VW", "2021", "TIGUAN R", "LIBRARY")


def full_observation_contract():
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


class SourceFixture:
    def __init__(self, rows=None, *, after=META):
        self.rows = rows if rows is not None else [HEADER, VW]
        self.after = after
        self.calls = 0

    def metadata(self):
        self.calls += 1
        return META if self.calls == 1 else self.after

    def values(self):
        return self.rows


class EvidenceFixture:
    def __init__(self, evidence=()):
        self.evidence = evidence

    def resolve(self, observation):
        return self.evidence


def evidence(vehicle="vehicle-1", *, key="VIN-1"):
    return AdmittedDurableIdentity("VIN", key, vehicle, "registration-1", "a" * 64,
                                    "CONTROLLED_TEST_VERIFIER")


def store(tmp_path, *, vehicles=(("vehicle-1", "VIN-1"),)):
    path = tmp_path / "inventory.sqlite"
    with sqlite3.connect(path) as connection:
        sqlite_contract_schema(connection)
        for number, (vehicle, vin) in enumerate(vehicles, 2):
            connection.execute(
                "INSERT INTO vehicle_record VALUES (?, 0, ?, '{}', '{}', ?, 'now', 'now')",
                (vehicle, json.dumps({"VIN/車身號碼": vin}), number),
            )
    return SqlInventoryBindingStore(lambda: sqlite3.connect(path), dialect="sqlite_test"), path


def test_observation_identity_changes_with_position_content_and_currentness():
    initial = read_current_snapshot(SourceFixture())
    shifted = read_current_snapshot(SourceFixture([HEADER, ["", "", "", "", "", ""], VW]))
    altered = read_current_snapshot(SourceFixture([HEADER, VW + ["new"]]))
    newer = read_current_snapshot(SourceFixture(after=META))
    assert len(initial.observations) == 1
    assert initial.observations[0].source_row == 2
    assert initial.observations[0].observation_id != shifted.observations[0].observation_id
    assert initial.observations[0].observation_id != altered.observations[0].observation_id
    assert initial.currentness_token == newer.currentness_token
    assert initial.observations[0].observation_id != "vehicle-1"


def test_exact_google_read_contract_uses_drive_and_sheet_metadata(monkeypatch):
    source = GoogleInventorySource(lambda: "test-token")
    calls = []

    def read(url):
        calls.append(url)
        if "/drive/v3/" in url:
            return {"id": META.file_id, "mimeType": "application/vnd.google-apps.spreadsheet",
                    "modifiedTime": META.modified_time}
        if "/values/" in url:
            return {"values": [HEADER, VW]}
        return {"spreadsheetId": META.file_id,
                "sheets": [{"properties": {"sheetId": META.sheet_id, "title": "車源"}}]}

    monkeypatch.setattr(source, "_get", read)
    snapshot = read_current_snapshot(source)
    assert len(snapshot.observations) == 1
    assert len(calls) == 5
    assert calls[0] == calls[3]
    assert calls[1] == calls[4]
    assert "/values/" in calls[2]


def test_google_source_requires_both_read_only_scopes():
    assert GoogleInventorySource.required_scopes == (
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    )


def test_source_advanced_between_metadata_reads_holds():
    newer = SourceMetadata(META.file_id, "2026-09-28T00:01:00Z", META.sheet_id, META.sheet_name)
    with pytest.raises(InventoryIdentityHold, match="HOLD_INVENTORY_SOURCE_ADVANCED"):
        read_current_snapshot(SourceFixture(after=newer))


def test_source_unavailable_fails_closed():
    source = SourceFixture()
    source.metadata = lambda: (_ for _ in ()).throw(OSError("unavailable"))
    with pytest.raises(InventoryIdentityHold, match="HOLD_INVENTORY_SOURCE_UNAVAILABLE"):
        read_current_snapshot(source)


def test_unique_source_row_without_durable_key_stays_candidate(tmp_path):
    binding, path = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture())
    result = AuthoritativeInventoryResolver(binding, EvidenceFixture()).resolve(TURN, snapshot)
    assert result.binding_state is BindingState.INSTANCE_CANDIDATE
    assert result.vehicle_instance_id is None
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_record").fetchone() == (1,)
        row = connection.execute("SELECT vehicle_instance_id FROM vehicle_source_observation").fetchone()
        assert row == (None,)


def test_existing_canonical_observation_binding_is_reused(tmp_path):
    binding, path = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture())
    binding.record_snapshot(snapshot)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE vehicle_source_observation SET vehicle_instance_id = 'vehicle-1', "
                           "binding_state = 'INSTANCE_BOUND' WHERE source_observation_id = ?",
                           (snapshot.observations[0].observation_id,))
    result = AuthoritativeInventoryResolver(binding, EvidenceFixture()).resolve(TURN, snapshot)
    assert (result.binding_state, result.vehicle_instance_id) == (BindingState.INSTANCE_BOUND, "vehicle-1")


def test_admitted_durable_key_promotes_once_and_fresh_reads(tmp_path):
    binding, path = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture())
    resolver = AuthoritativeInventoryResolver(binding, EvidenceFixture((evidence(),)))
    first = resolver.resolve(TURN, snapshot)
    second = resolver.resolve(TURN, snapshot)
    assert first == second
    assert first.binding_state is BindingState.INSTANCE_BOUND
    assert first.vehicle_instance_id == "vehicle-1"
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT vehicle_instance_id, binding_state FROM "
                                  "vehicle_source_observation").fetchall() == [
            ("vehicle-1", "INSTANCE_BOUND")]
        assert connection.execute("SELECT COUNT(*) FROM vehicle_record").fetchone() == (1,)


def test_two_plausible_rows_hold_without_binding(tmp_path):
    binding, path = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture([HEADER, VW, VW]))
    result = AuthoritativeInventoryResolver(binding, EvidenceFixture((evidence(),))).resolve(TURN, snapshot)
    assert (result.binding_state, result.candidate_count) == (BindingState.HOLD_IDENTITY_CONFLICT, 2)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_source_observation "
                                  "WHERE vehicle_instance_id IS NOT NULL").fetchone() == (0,)


def test_conflicting_durable_keys_hold(tmp_path):
    binding, _ = store(tmp_path, vehicles=(("vehicle-1", "VIN-1"), ("vehicle-2", "VIN-2")))
    snapshot = read_current_snapshot(SourceFixture())
    resolver = AuthoritativeInventoryResolver(binding, EvidenceFixture((
        evidence(), evidence("vehicle-2", key="VIN-2"))))
    result = resolver.resolve(TURN, snapshot)
    assert result.binding_state is BindingState.HOLD_IDENTITY_CONFLICT


def test_evidence_key_disagrees_with_existing_canonical_identity(tmp_path):
    binding, _ = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture())
    with pytest.raises(InventoryIdentityHold, match="HOLD_IDENTITY_CONFLICT"):
        AuthoritativeInventoryResolver(binding, EvidenceFixture((
            evidence(key="OTHER-VIN"),))).resolve(TURN, snapshot)


def test_same_vehicle_cannot_bind_two_current_observations(tmp_path):
    binding, _ = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture([HEADER, VW, ["22", "", "", "VW", "2022", "TIGUAN R"]]))
    binding.record_snapshot(snapshot)
    assert binding.promote(snapshot.observations[1], "vehicle-1", (evidence(),)) == "vehicle-1"
    with pytest.raises(InventoryIdentityHold, match="HOLD_IDENTITY_CONFLICT"):
        binding.promote(snapshot.observations[0], "vehicle-1", (evidence(),))


def test_identifier_repoint_after_source_change_holds(tmp_path):
    binding, _ = store(tmp_path)
    first = read_current_snapshot(SourceFixture())
    binding.record_snapshot(first)
    assert binding.promote(first.observations[0], "vehicle-1", (evidence(),)) == "vehicle-1"
    changed = read_current_snapshot(SourceFixture([HEADER, VW + ["changed"]]))
    binding.record_snapshot(changed)
    with pytest.raises(InventoryIdentityHold, match="HOLD_IDENTITY_CONFLICT"):
        binding.promote(changed.observations[0], "vehicle-1", (evidence(),))


def test_unadmitted_target_id_cannot_create_vehicle(tmp_path):
    binding, path = store(tmp_path)
    snapshot = read_current_snapshot(SourceFixture())
    with pytest.raises(InventoryIdentityHold, match="HOLD_CANONICAL_VEHICLE_NOT_ADMITTED"):
        AuthoritativeInventoryResolver(binding, EvidenceFixture((
            evidence("invented-vehicle", key="VIN-X"),))).resolve(TURN, snapshot)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_record").fetchone() == (1,)


def test_stage_f_14_11_3_remains_verifiable_after_inventory_observation(tmp_path):
    path = tmp_path / "stage-f.sqlite"
    with sqlite3.connect(path) as connection:
        sqlite_contract_schema(connection)
    canonical = TransactionalVehicleStore(lambda: sqlite3.connect(path), dialect="sqlite_test")
    raw = full_observation_contract()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    receipt = import_fixed_preimage(canonical, raw, manifest)
    assert (receipt.source_observation_count, receipt.bound_vehicle_count,
            receipt.unbound_observation_count) == (14, 11, 3)
    binding = SqlInventoryBindingStore(lambda: sqlite3.connect(path), dialect="sqlite_test")
    binding.record_snapshot(read_current_snapshot(SourceFixture()))
    assert verify_import(canonical, manifest) == receipt
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_record").fetchone() == (11,)
        count = connection.execute("SELECT COUNT(*) FROM vehicle_source_observation "
                                   "WHERE source_file_id = ?", (CANONICAL_WORKBENCH_FILE_ID,)).fetchone()
        assert count == (14,)
