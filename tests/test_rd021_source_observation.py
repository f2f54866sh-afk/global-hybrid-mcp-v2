"""Source rows remain durable observations even without a vehicle identity."""
from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET

import pytest

from global_hybrid_v2.canonical_cutover import compile_import, import_fixed_preimage, verify_import
from global_hybrid_v2.canonical_projection import DeterministicXlsxProjectionBuilder
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalConflict,
    TransactionalVehicleStore,
    sqlite_contract_schema,
)
from global_hybrid_v2.workbench_mutation import AI_SHEET, _cell, _header, _rows, _set_cell, _Workbook
from tests.test_rd021_completion_fence import q
from tests.test_rd021_creative_schema_migration import edit_sheet
from tests.test_rd021_media_admission import creative_workbook


def observation_workbook():
    def edit(root):
        sheet = root.find(q("sheetData"))
        header = sheet.findall(q("row"))[0]
        header.remove(next(cell for cell in header.findall(q("c")) if cell.get("r") == "F1"))
        for column, name in ((6, "來源觀測ID"), (7, "AI使用狀態"),
                             (8, "COMPANY_SOURCE_STATE")):
            _set_cell(_cell(header, column, create=True), name)
        for row in sheet.findall(q("row"))[1:]:
            _set_cell(_cell(row, 6, create=True), f"source:{row.get('r')}")
        for number, company in ((3, "NOT_IN_CURRENT_SOURCE"),
                                (8, "NOT_IN_CURRENT_SOURCE"),
                                (15, "NEW_CURRENT_UNBOUND")):
            row = ET.Element(q("row"), {"r": str(number)})
            _set_cell(_cell(row, 6, create=True), f"source:{number}")
            _set_cell(_cell(row, 7, create=True),
                      "SOURCE_OBSERVATION_ONLY / NOT_INSTANCE_READY")
            _set_cell(_cell(row, 8, create=True), company)
            sheet.append(row)
        sheet[:] = sorted(sheet, key=lambda row: int(row.get("r")))

    return edit_sheet(creative_workbook(), edit)


def change(payload, row_number, column, value):
    def edit(root):
        row = next(row for row in root.find(q("sheetData")).findall(q("row"))
                   if row.get("r") == str(row_number))
        _set_cell(_cell(row, column, create=True), value)

    return edit_sheet(payload, edit)


def test_observation_only_rows_import_without_fake_vehicles(tmp_path):
    raw = observation_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert manifest.source_schema == "PRE_CREATIVE_REFS"
    assert (manifest.observation_count, manifest.vehicle_count,
            manifest.unbound_observation_count) == (5, 2, 3)
    assert [item.source_row for item in manifest.observations
            if item.vehicle_instance_id is None] == [3, 8, 15]
    path = tmp_path / "observation.sqlite"
    with sqlite3.connect(path) as connection:
        sqlite_contract_schema(connection)
    store = TransactionalVehicleStore(lambda: sqlite3.connect(path), dialect="sqlite_test")
    receipt = import_fixed_preimage(store, raw, manifest)
    assert receipt.state == "IMPORT_READBACK_PASS"
    assert (receipt.source_observation_count, receipt.bound_vehicle_count,
            receipt.unbound_observation_count) == (5, 2, 3)
    assert verify_import(store, manifest) == receipt
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_source_observation").fetchone() == (5,)
        assert connection.execute("SELECT COUNT(*) FROM vehicle_record").fetchone() == (2,)
        assert connection.execute("SELECT source_row FROM vehicle_source_observation "
                                  "WHERE vehicle_instance_id IS NULL ORDER BY source_row").fetchall() == [
            (3,), (8,), (15,),
        ]
        assert connection.execute("SELECT source_observation_count, bound_vehicle_count, "
                                  "unbound_observation_count FROM canonical_cutover").fetchone() == (5, 2, 3)


@pytest.mark.parametrize("column,forged", [
    ("source_file_id", "wrong-source-file"),
    ("source_sha256", "0" * 64),
])
def test_observation_provenance_tamper_holds_with_correct_cutover(tmp_path, column, forged):
    raw = observation_workbook()
    manifest = compile_import(raw, file_id=CANONICAL_WORKBENCH_FILE_ID)
    path = tmp_path / "provenance.sqlite"
    with sqlite3.connect(path) as connection:
        sqlite_contract_schema(connection)
    store = TransactionalVehicleStore(lambda: sqlite3.connect(path), dialect="sqlite_test")
    receipt = import_fixed_preimage(store, raw, manifest)
    assert verify_import(store, manifest) == receipt
    with sqlite3.connect(path) as connection:
        changed = connection.execute(
            f"UPDATE vehicle_source_observation SET {column} = ? WHERE source_row = ?",
            (forged, 3),
        ).rowcount
        assert changed == 1
        assert connection.execute(
            "SELECT source_file_id, source_sha256 FROM canonical_cutover"
        ).fetchone() == (manifest.source_file_id, manifest.source_sha256)
    with pytest.raises(CanonicalConflict, match="^HOLD_MIGRATION_MISMATCH$"):
        verify_import(store, manifest)


def test_identity_and_creative_contradictions_fail_closed():
    raw = observation_workbook()
    for altered, blocker in (
        (change(raw, 15, 7, "INSTANCE_READY"), "IDENTITY_CONTRADICTION"),
        (change(raw, 15, 6, "source:3"), "OBSERVATION_ID_DUPLICATE"),
        (change(raw, 13, 1, "gran-turismo"), "IDENTITY_DUPLICATE"),
    ):
        with pytest.raises(CanonicalConflict, match=blocker):
            compile_import(altered, file_id=CANONICAL_WORKBENCH_FILE_ID)

    def unresolved_creative(root):
        header = root.find(q("sheetData")).findall(q("row"))[0]
        _set_cell(_cell(header, 9, create=True), "銷售素材Refs")
        row = next(row for row in root.find(q("sheetData")).findall(q("row"))
                   if row.get("r") == "13")
        _set_cell(_cell(row, 9, create=True), '["creative:unresolved"]')

    with pytest.raises(CanonicalConflict, match="CREATIVE_LINKAGE_REQUIRED"):
        compile_import(edit_sheet(raw, unresolved_creative), file_id=CANONICAL_WORKBENCH_FILE_ID)


def test_projection_copy_schema_upgrade_preserves_all_source_rows():
    raw = observation_workbook()
    builder = DeterministicXlsxProjectionBuilder()
    creative_added = builder.add_creative_schema(raw)
    builder._verify_schema_locality(raw, creative_added)
    before, after = _Workbook.parse(raw), _Workbook.parse(creative_added)
    assert [row.get("r") for row in _rows(before.root(AI_SHEET))] == [
        row.get("r") for row in _rows(after.root(AI_SHEET))]
    assert _header(after.root(AI_SHEET), after.shared)["銷售素材Refs"] == 9
    assert builder.add_creative_schema(creative_added) == creative_added
    revision_added = builder.add_revision_schema(creative_added)
    assert _header(_Workbook.parse(revision_added).root(AI_SHEET),
                   _Workbook.parse(revision_added).shared)["CANONICAL_REVISION"] == 10
