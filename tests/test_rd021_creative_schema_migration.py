from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from global_hybrid_v2.adapters.drive_xlsx_workbench import DriveXlsxWorkbenchPort, WorkbenchConflict
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.creative_schema_migration import (
    CreativeRefsSchemaMigration,
    CreativeSchemaMigrationRunner,
    SchemaMigrationState,
)
from tests.test_rd021_completion_fence import Claims, Drive, q
from tests.test_rd021_media_admission import creative_workbook


def edit_sheet(payload: bytes, edit):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload)) as original, zipfile.ZipFile(output, "w") as changed:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(data)
                edit(root)
                data = ET.tostring(root)
            changed.writestr(info, data)
    return output.getvalue()


def preimage():
    def remove_creative(root):
        header = root.find(q("sheetData")).find(q("row"))
        header.remove(next(cell for cell in header.findall(q("c")) if cell.get("r") == "F1"))

    return edit_sheet(creative_workbook(), remove_creative)


def test_clean_migration_readback_and_second_run_no_delta():
    migration = CreativeRefsSchemaMigration()
    before = preimage()
    after = migration.build(before, file_id=CANONICAL_WORKBENCH_FILE_ID)
    migration.verify(before, after, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert after != before
    assert migration.build(after, file_id=CANONICAL_WORKBENCH_FILE_ID) == after
    with zipfile.ZipFile(io.BytesIO(after)) as archive:
        ai = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        header = ai.find(q("sheetData")).find(q("row"))
        cells = header.findall(q("c"))
        assert len([cell for cell in cells if "銷售素材Refs" in ET.tostring(cell, encoding="unicode")]) == 1
        assert "original:1" in archive.read("xl/worksheets/sheet1.xml").decode()


def test_migration_requires_canonical_file_id_and_original_media_column():
    migration = CreativeRefsSchemaMigration()
    with pytest.raises(WorkbenchConflict, match="TARGET_FILE_ID"):
        migration.build(preimage(), file_id="other")
    def remove_original(root):
        header = root.find(q("sheetData")).find(q("row"))
        header.remove(next(cell for cell in header.findall(q("c")) if cell.get("r") == "E1"))
    with pytest.raises(WorkbenchConflict, match="PREIMAGE_INVALID"):
        migration.build(edit_sheet(preimage(), remove_original), file_id=CANONICAL_WORKBENCH_FILE_ID)


def test_existing_conflicting_header_or_content_holds():
    migration = CreativeRefsSchemaMigration()
    existing = edit_sheet(creative_workbook(), lambda root: ET.SubElement(
        root.find(q("sheetData")).find(q("row")), q("c"), {"r": "G1", "t": "inlineStr"},
    ))  # creative header is no longer last
    with pytest.raises(WorkbenchConflict, match="POSITION_CONFLICT"):
        migration.build(existing, file_id=CANONICAL_WORKBENCH_FILE_ID)
    migrated = migration.build(preimage(), file_id=CANONICAL_WORKBENCH_FILE_ID)
    def add_bad_content(root):
        row = next(row for row in root.find(q("sheetData")).findall(q("row")) if row.get("r") == "13")
        cell = ET.SubElement(row, q("c"), {"r": "F13", "t": "inlineStr"})
        ET.SubElement(ET.SubElement(cell, q("is")), q("t")).text = "not a creative ref"
    with pytest.raises(WorkbenchConflict, match="CONTENT_CONFLICT"):
        migration.build(edit_sheet(migrated, add_bad_content), file_id=CANONICAL_WORKBENCH_FILE_ID)


def test_verifier_rejects_unrelated_cell_change_and_rollback_preserves_data():
    migration = CreativeRefsSchemaMigration()
    before = preimage()
    after = migration.build(before, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert migration.rollback_eligibility(after, file_id=CANONICAL_WORKBENCH_FILE_ID) is (
        SchemaMigrationState.ROLLBACK_ELIGIBLE
    )
    rolled = migration.build_rollback(after, file_id=CANONICAL_WORKBENCH_FILE_ID)
    assert migration.inspect(rolled, file_id=CANONICAL_WORKBENCH_FILE_ID) is (
        SchemaMigrationState.WRITE_AND_READBACK_PASS
    )
    def mutate_unrelated(root):
        row = next(row for row in root.find(q("sheetData")).findall(q("row")) if row.get("r") == "13")
        cell = next(cell for cell in row.findall(q("c")) if cell.get("r") == "B13")
        cell.find(f"{q('is')}/{q('t')}").text = "tampered"
    with pytest.raises(WorkbenchConflict, match="EXISTING_VEHICLE_CELL_CHANGED"):
        migration.verify(before, edit_sheet(after, mutate_unrelated), file_id=CANONICAL_WORKBENCH_FILE_ID)
    def add_creative_ref(root):
        row = next(row for row in root.find(q("sheetData")).findall(q("row")) if row.get("r") == "13")
        cell = ET.SubElement(row, q("c"), {"r": "F13", "t": "inlineStr"})
        ET.SubElement(ET.SubElement(cell, q("is")), q("t")).text = '["creative:1"]'
    populated = edit_sheet(after, add_creative_ref)
    assert migration.rollback_eligibility(populated, file_id=CANONICAL_WORKBENCH_FILE_ID) is (
        SchemaMigrationState.ROLLBACK_BLOCKED_DATA_PRESENT
    )
    with pytest.raises(WorkbenchConflict, match="ROLLBACK_BLOCKED_DATA_PRESENT"):
        migration.build_rollback(populated, file_id=CANONICAL_WORKBENCH_FILE_ID)


def test_runner_uses_exact_drive_transaction_and_fresh_postwrite_readback():
    drive = Drive(preimage())
    writer = DriveXlsxWorkbenchPort(
        file_id=CANONICAL_WORKBENCH_FILE_ID, drive=drive, claims=Claims(),
    )
    runner = CreativeSchemaMigrationRunner(writer)
    first = runner.run(task_id="schema")
    assert first.state is SchemaMigrationState.WRITE_AND_READBACK_PASS
    assert first.preimage_sha256 and first.postwrite_sha256
    assert drive.writes == 1
    second = runner.run(task_id="schema")
    assert second.state is SchemaMigrationState.NO_DELTA
    assert drive.writes == 1
    assert CreativeSchemaMigrationRunner(None).run(task_id="schema").state is (
        SchemaMigrationState.PERSISTENCE_CAPABILITY_DEBT
    )
