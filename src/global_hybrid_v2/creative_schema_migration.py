"""Exact-preimage canonical XLSX schema migration and bounded rollback candidate."""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import StrEnum

from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    DriveXlsxWorkbenchPort,
    WorkbenchCapabilityDebt,
    WorkbenchConflict,
    WorkbenchPostwriteMismatch,
)
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.creative_media import CREATIVE_REFS_COLUMN
from global_hybrid_v2.workbench_mutation import (
    AI_SHEET,
    _cell,
    _cell_value,
    _column,
    _q,
    _rows,
    _set_cell,
    _Workbook,
)


class SchemaMigrationState(StrEnum):
    WRITE_AND_READBACK_PASS = "WRITE_AND_READBACK_PASS"
    NO_DELTA = "NO_DELTA"
    HOLD_CONFLICT = "HOLD_CONFLICT"
    PERSISTENCE_CAPABILITY_DEBT = "PERSISTENCE_CAPABILITY_DEBT"
    ROLLBACK_ELIGIBLE = "ROLLBACK_ELIGIBLE"
    ROLLBACK_BLOCKED_DATA_PRESENT = "ROLLBACK_BLOCKED_DATA_PRESENT"


@dataclass(frozen=True)
class CreativeSchemaMigrationReceipt:
    state: SchemaMigrationState
    file_id: str
    preimage_sha256: str | None = None
    postwrite_sha256: str | None = None
    preimage_version: str | None = None
    postwrite_version: str | None = None
    vehicle_row_count: int | None = None
    blocker: str | None = None


class CreativeRefsSchemaMigration:
    @staticmethod
    def _header_state(payload: bytes) -> tuple[_Workbook, ET.Element, int, int | None, int]:
        book = _Workbook.parse(payload)
        ai = book.root(AI_SHEET)
        rows = _rows(ai)
        if not rows or rows[0].get("r") != "1":
            raise WorkbenchConflict("HOLD_CREATIVE_HEADER_MISSING")
        names: dict[str, list[int]] = {}
        for cell in rows[0].findall(_q("c")):
            names.setdefault(_cell_value(cell, book.shared), []).append(_column(cell.get("r") or ""))
        if len(names.get("VEHICLE_INSTANCE_ID", [])) != 1 or len(names.get("原始媒體Refs", [])) != 1:
            raise WorkbenchConflict("HOLD_CREATIVE_SCHEMA_PREIMAGE_INVALID")
        identities = []
        identity_col = names["VEHICLE_INSTANCE_ID"][0]
        for row in rows[1:]:
            value = _cell(row, identity_col)
            if value is None or not (identity := _cell_value(value, book.shared)).strip():
                raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_MISSING")
            identities.append(identity)
        if len(set(identities)) != len(identities):
            raise WorkbenchConflict("HOLD_VEHICLE_IDENTITY_AMBIGUOUS")
        creative = names.get(CREATIVE_REFS_COLUMN, [])
        if len(creative) > 1:
            raise WorkbenchConflict("HOLD_CREATIVE_HEADER_CONFLICT")
        max_col = max(_column(cell.get("r") or "") for cell in rows[0].findall(_q("c")))
        return book, ai, identity_col, creative[0] if creative else None, max_col

    def inspect(self, payload: bytes, *, file_id: str) -> SchemaMigrationState:
        if file_id != CANONICAL_WORKBENCH_FILE_ID:
            raise WorkbenchConflict("HOLD_TARGET_FILE_ID_MISMATCH")
        book, ai, _, creative_col, max_col = self._header_state(payload)
        if creative_col is None:
            return SchemaMigrationState.WRITE_AND_READBACK_PASS
        if creative_col != max_col:
            raise WorkbenchConflict("HOLD_CREATIVE_HEADER_POSITION_CONFLICT")
        # Valid creative refs may already exist after the original migration.
        for row in _rows(ai)[1:]:
            cell = _cell(row, creative_col)
            value = "" if cell is None else _cell_value(cell, book.shared)
            if value:
                try:
                    refs = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise WorkbenchConflict("HOLD_CREATIVE_HEADER_CONTENT_CONFLICT") from exc
                if not isinstance(refs, list) or any(
                    not isinstance(ref, str) or not ref.startswith("creative:") for ref in refs
                ):
                    raise WorkbenchConflict("HOLD_CREATIVE_HEADER_CONTENT_CONFLICT")
        return SchemaMigrationState.NO_DELTA

    def build(self, preimage: bytes, *, file_id: str) -> bytes:
        state = self.inspect(preimage, file_id=file_id)
        if state is SchemaMigrationState.NO_DELTA:
            return preimage
        book, ai, _, _, max_col = self._header_state(preimage)
        header = _rows(ai)[0]
        _set_cell(_cell(header, max_col + 1, create=True), CREATIVE_REFS_COLUMN)
        output = book.render({book.sheets[AI_SHEET]: ai})
        self.verify(preimage, output, file_id=file_id)
        return output

    def verify(self, preimage: bytes, output: bytes, *, file_id: str) -> None:
        if file_id != CANONICAL_WORKBENCH_FILE_ID:
            raise WorkbenchConflict("HOLD_TARGET_FILE_ID_MISMATCH")
        before, old_ai, _, creative, max_col = self._header_state(preimage)
        after, new_ai, _, added, new_max = self._header_state(output)
        if creative is not None or added != max_col + 1 or new_max != added:
            raise WorkbenchConflict("HOLD_CREATIVE_SCHEMA_READBACK_MISMATCH")
        if list(before.entries) != list(after.entries) or before.sheets != after.sheets:
            raise WorkbenchConflict("HOLD_WORKBOOK_TOPOLOGY_CHANGED")
        ai_path = before.sheets[AI_SHEET]
        if any(before.entries[name] != after.entries[name] for name in before.entries if name != ai_path):
            raise WorkbenchConflict("HOLD_UNRELATED_WORKBOOK_ENTRY_CHANGED")
        old_rows, new_rows = _rows(old_ai), _rows(new_ai)
        if [r.get("r") for r in old_rows] != [r.get("r") for r in new_rows]:
            raise WorkbenchConflict("HOLD_VEHICLE_ROW_TOPOLOGY_CHANGED")
        for old_row, new_row in zip(old_rows[1:], new_rows[1:], strict=True):
            if ET.tostring(old_row) != ET.tostring(new_row):
                raise WorkbenchConflict("HOLD_EXISTING_VEHICLE_CELL_CHANGED")
        old_header, new_header = old_rows[0], new_rows[0]
        old_cells = old_header.findall(_q("c"))
        new_cells = new_header.findall(_q("c"))
        if len(new_cells) != len(old_cells) + 1 or any(
            ET.tostring(left) != ET.tostring(right)
            for left, right in zip(old_cells, new_cells[:-1], strict=True)
        ) or _cell_value(new_cells[-1], after.shared) != CREATIVE_REFS_COLUMN:
            raise WorkbenchConflict("HOLD_CREATIVE_HEADER_ONLY_MUTATION_REQUIRED")

    def rollback_eligibility(self, payload: bytes, *, file_id: str) -> SchemaMigrationState:
        if file_id != CANONICAL_WORKBENCH_FILE_ID:
            raise WorkbenchConflict("HOLD_TARGET_FILE_ID_MISMATCH")
        book, ai, _, creative_col, max_col = self._header_state(payload)
        if creative_col is None or creative_col != max_col:
            raise WorkbenchConflict("HOLD_CREATIVE_SCHEMA_ROLLBACK_CONFLICT")
        for row in _rows(ai)[1:]:
            cell = _cell(row, creative_col)
            if cell is not None and _cell_value(cell, book.shared).strip():
                return SchemaMigrationState.ROLLBACK_BLOCKED_DATA_PRESENT
        return SchemaMigrationState.ROLLBACK_ELIGIBLE

    def build_rollback(self, preimage: bytes, *, file_id: str) -> bytes:
        state = self.rollback_eligibility(preimage, file_id=file_id)
        if state is SchemaMigrationState.ROLLBACK_BLOCKED_DATA_PRESENT:
            raise WorkbenchConflict("ROLLBACK_BLOCKED_DATA_PRESENT")
        book, ai, _, creative_col, _ = self._header_state(preimage)
        header = _rows(ai)[0]
        cell = _cell(header, creative_col)
        header.remove(cell)
        output = book.render({book.sheets[AI_SHEET]: ai})
        self.verify(output, preimage, file_id=file_id)
        return output


class CreativeSchemaMigrationRunner:
    def __init__(self, writer: DriveXlsxWorkbenchPort | None) -> None:
        self.writer = writer
        self.migration = CreativeRefsSchemaMigration()

    def run(self, *, task_id: str) -> CreativeSchemaMigrationReceipt:
        file_id = CANONICAL_WORKBENCH_FILE_ID
        if self.writer is None:
            return CreativeSchemaMigrationReceipt(
                SchemaMigrationState.PERSISTENCE_CAPABILITY_DEBT, file_id,
                blocker="DRIVE_WRITER_UNAVAILABLE",
            )
        if self.writer.file_id != file_id:
            return CreativeSchemaMigrationReceipt(
                SchemaMigrationState.HOLD_CONFLICT, file_id, blocker="HOLD_TARGET_FILE_ID_MISMATCH",
            )
        captured: dict[str, bytes] = {}

        def build(preimage: bytes) -> bytes:
            captured["preimage"] = preimage
            output = self.migration.build(preimage, file_id=file_id)
            captured["output"] = output
            return output

        try:
            write = self.writer.mutate(
                task_id=task_id, intent_sha256=hashlib.sha256(b"CREATIVE_REFS_SCHEMA_V1").hexdigest(),
                build_new_bytes=build,
            )
            if write.state == "NO_DELTA":
                return CreativeSchemaMigrationReceipt(
                    SchemaMigrationState.NO_DELTA, file_id,
                    preimage_sha256=write.preimage_sha256,
                    preimage_version=write.preimage_version,
                    vehicle_row_count=len(_rows(_Workbook.parse(captured["preimage"]).root(AI_SHEET))) - 1,
                )
            fresh_meta = self.writer.drive.metadata(file_id)
            fresh = self.writer.drive.download(file_id)
            if (str(fresh_meta.get("version")) != write.postwrite_version
                or hashlib.sha256(fresh).hexdigest() != write.postwrite_sha256):
                raise WorkbenchConflict("HOLD_CREATIVE_SCHEMA_POSTWRITE_MISMATCH")
            self.migration.verify(captured["preimage"], fresh, file_id=file_id)
            return CreativeSchemaMigrationReceipt(
                SchemaMigrationState.WRITE_AND_READBACK_PASS, file_id,
                preimage_sha256=write.preimage_sha256, postwrite_sha256=write.postwrite_sha256,
                preimage_version=write.preimage_version, postwrite_version=write.postwrite_version,
                vehicle_row_count=len(_rows(_Workbook.parse(fresh).root(AI_SHEET))) - 1,
            )
        except (WorkbenchConflict, WorkbenchPostwriteMismatch) as exc:
            return CreativeSchemaMigrationReceipt(
                SchemaMigrationState.HOLD_CONFLICT, file_id, blocker=str(exc),
            )
        except (WorkbenchCapabilityDebt, OSError, TimeoutError) as exc:
            return CreativeSchemaMigrationReceipt(
                SchemaMigrationState.PERSISTENCE_CAPABILITY_DEBT, file_id,
                blocker=type(exc).__name__,
            )
