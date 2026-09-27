"""Idempotent outbox contract and a strictly read-only XLSX projection verifier."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Protocol

from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalConflict,
    CanonicalReadback,
    TransactionalVehicleStore,
    _Sql,
)
from global_hybrid_v2.workbench_mutation import (
    AI_SHEET,
    _cell,
    _column,
    _header,
    _rows,
    _set_cell,
    _values,
    _Workbook,
)

REVISION_COLUMN = "CANONICAL_REVISION"


@dataclass(frozen=True)
class ProjectionEvent:
    event_id: str
    vehicle_instance_id: str
    canonical_revision: int


class ProjectionSink(Protocol):
    def project(self, event: ProjectionEvent, state: CanonicalReadback) -> None: ...


class ProjectionReadTransport(Protocol):
    def metadata(self, file_id: str) -> dict: ...
    def download(self, file_id: str) -> bytes: ...


class DeterministicXlsxProjectionBuilder:
    """Changes only one resolved row in a projection preimage; never reads vehicle truth from XLSX."""

    def add_revision_schema(self, preimage: bytes) -> bytes:
        """Candidate-only projection schema addition after DB authority cutover."""
        book = _Workbook.parse(preimage)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        if REVISION_COLUMN in header:
            if header[REVISION_COLUMN] != max(header.values()):
                raise CanonicalConflict("HOLD_PROJECTION_REVISION_HEADER_CONFLICT")
            return preimage
        rows = _rows(ai)
        if not rows:
            raise CanonicalConflict("HOLD_PROJECTION_SCHEMA_MISSING")
        max_col = max(_column(cell.get("r") or "") for cell in rows[0].findall("{*}c"))
        _set_cell(_cell(rows[0], max_col + 1, create=True), REVISION_COLUMN)
        output = book.render({book.sheets[AI_SHEET]: ai})
        self._verify_schema_locality(preimage, output)
        return output

    @staticmethod
    def _verify_schema_locality(preimage: bytes, output: bytes) -> None:
        before, after = _Workbook.parse(preimage), _Workbook.parse(output)
        if list(before.entries) != list(after.entries) or before.sheets != after.sheets:
            raise CanonicalConflict("HOLD_PROJECTION_TOPOLOGY_CHANGED")
        ai_path = before.sheets[AI_SHEET]
        if any(before.entries[name] != after.entries[name] for name in before.entries if name != ai_path):
            raise CanonicalConflict("HOLD_PROJECTION_UNRELATED_ENTRY_CHANGED")
        old_rows, new_rows = _rows(before.root(AI_SHEET)), _rows(after.root(AI_SHEET))
        if [row.get("r") for row in old_rows] != [row.get("r") for row in new_rows]:
            raise CanonicalConflict("HOLD_PROJECTION_ROW_TOPOLOGY_CHANGED")
        if any(ET.tostring(left) != ET.tostring(right)
               for left, right in zip(old_rows[1:], new_rows[1:], strict=True)):
            raise CanonicalConflict("HOLD_PROJECTION_UNRELATED_ROW_CHANGED")
        old_header, new_header = old_rows[0], new_rows[0]
        old_cells, new_cells = old_header.findall("{*}c"), new_header.findall("{*}c")
        if len(new_cells) != len(old_cells) + 1 or any(
            ET.tostring(left) != ET.tostring(right)
            for left, right in zip(old_cells, new_cells[:-1], strict=True)
        ):
            raise CanonicalConflict("HOLD_PROJECTION_HEADER_ONLY_MUTATION_REQUIRED")

    def build(self, preimage: bytes, event: ProjectionEvent, state: CanonicalReadback) -> bytes:
        if (event.vehicle_instance_id != state.vehicle_instance_id
            or event.canonical_revision != state.revision):
            raise CanonicalConflict("HOLD_PROJECTION_SOURCE_IDENTITY_MISMATCH")
        book = _Workbook.parse(preimage)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        if "VEHICLE_INSTANCE_ID" not in header or REVISION_COLUMN not in header:
            raise CanonicalConflict("HOLD_PROJECTION_SCHEMA_MISSING")
        if any(field not in header for field in state.current_state):
            raise CanonicalConflict("HOLD_PROJECTION_FIELD_COLUMN_MISSING")
        matching = [row for row in _rows(ai)[1:]
                    if _values(row, book.shared).get(header["VEHICLE_INSTANCE_ID"])
                    == event.vehicle_instance_id]
        if len(matching) != 1:
            raise CanonicalConflict("HOLD_PROJECTION_IDENTITY_MISMATCH")
        target = matching[0]
        for field, value in state.current_state.items():
            column = header[field]
            current = _values(target, book.shared).get(column, "")
            if current != str(value):
                _set_cell(_cell(target, column, create=True), value)
        revision = _values(target, book.shared).get(header[REVISION_COLUMN], "")
        if revision != str(event.canonical_revision):
            _set_cell(_cell(target, header[REVISION_COLUMN], create=True), str(event.canonical_revision))
        output = book.render({book.sheets[AI_SHEET]: ai})
        self.verify_locality(preimage, output, event)
        return output

    def verify_locality(self, preimage: bytes, output: bytes, event: ProjectionEvent) -> None:
        before, after = _Workbook.parse(preimage), _Workbook.parse(output)
        if list(before.entries) != list(after.entries) or before.sheets != after.sheets:
            raise CanonicalConflict("HOLD_PROJECTION_TOPOLOGY_CHANGED")
        ai_path = before.sheets[AI_SHEET]
        if any(before.entries[name] != after.entries[name] for name in before.entries if name != ai_path):
            raise CanonicalConflict("HOLD_PROJECTION_UNRELATED_ENTRY_CHANGED")
        old_ai, new_ai = before.root(AI_SHEET), after.root(AI_SHEET)
        old_rows, new_rows = _rows(old_ai), _rows(new_ai)
        if [row.get("r") for row in old_rows] != [row.get("r") for row in new_rows]:
            raise CanonicalConflict("HOLD_PROJECTION_ROW_TOPOLOGY_CHANGED")
        identity_col = _header(old_ai, before.shared)["VEHICLE_INSTANCE_ID"]
        for old_row, new_row in zip(old_rows, new_rows, strict=True):
            old_id = _values(old_row, before.shared).get(identity_col)
            if old_id != event.vehicle_instance_id and ET.tostring(old_row) != ET.tostring(new_row):
                raise CanonicalConflict("HOLD_PROJECTION_UNRELATED_ROW_CHANGED")


class XlsxProjectionVerifier:
    """No write method is accepted or called at this boundary."""

    def __init__(self, read: ProjectionReadTransport, *, file_id: str = CANONICAL_WORKBENCH_FILE_ID):
        if file_id != CANONICAL_WORKBENCH_FILE_ID:
            raise CanonicalConflict("HOLD_PROJECTION_TARGET_MISMATCH")
        self.read, self.file_id = read, file_id

    def verify(self, event: ProjectionEvent, state: CanonicalReadback) -> str:
        before = self.read.metadata(self.file_id)
        payload = self.read.download(self.file_id)
        after = self.read.metadata(self.file_id)
        if before.get("version") is None or before.get("version") != after.get("version"):
            raise CanonicalConflict("HOLD_PROJECTION_READ_DRIFT")
        book = _Workbook.parse(payload)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        if "VEHICLE_INSTANCE_ID" not in header or REVISION_COLUMN not in header:
            raise CanonicalConflict("HOLD_PROJECTION_SCHEMA_MISSING")
        matching = []
        for row in _rows(ai)[1:]:
            values = _values(row, book.shared)
            if values.get(header["VEHICLE_INSTANCE_ID"]) == event.vehicle_instance_id:
                matching.append(values)
        if len(matching) != 1:
            raise CanonicalConflict("HOLD_PROJECTION_IDENTITY_MISMATCH")
        values = matching[0]
        if values.get(header[REVISION_COLUMN]) != str(event.canonical_revision):
            raise CanonicalConflict("HOLD_PROJECTION_REVISION_MISMATCH")
        if state.revision != event.canonical_revision:
            raise CanonicalConflict("HOLD_CANONICAL_REVISION_MISMATCH")
        if any(field not in header or values.get(header[field], "") != str(value)
               for field, value in state.current_state.items()):
            raise CanonicalConflict("HOLD_PROJECTION_FIELD_MISMATCH")
        return hashlib.sha256(payload).hexdigest()


class ProjectionOutboxWorker:
    def __init__(self, store: TransactionalVehicleStore, sink: ProjectionSink,
                 verifier: XlsxProjectionVerifier):
        self.store, self.sink, self.verifier = store, sink, verifier

    def run(self, event_id: str) -> str:
        connection = self.store._open()
        try:
            db = _Sql(connection, self.store.dialect)
            row = db.execute(
                "SELECT vehicle_instance_id, canonical_revision, state FROM projection_outbox "
                "WHERE event_id = ?", (event_id,),
            ).fetchone()
            if row is None:
                raise CanonicalConflict("HOLD_PROJECTION_EVENT_MISSING")
            if row[2] == "PROJECTED":
                return "PROJECTED"
            event = ProjectionEvent(event_id, str(row[0]), int(row[1]))
        finally:
            connection.close()
        state = self.store.read_vehicle(event.vehicle_instance_id)
        if state is None or state.revision < event.canonical_revision:
            raise CanonicalConflict("HOLD_CANONICAL_PROJECTION_SOURCE_MISSING")
        try:
            self.sink.project(event, state)
            digest = self.verifier.verify(event, state)
            disposition = "PROJECTED"
            error = None
        except Exception as exc:
            disposition = "PROJECTION_FAILED"
            digest = None
            error = type(exc).__name__
        connection = self.store._open()
        try:
            db = _Sql(connection, self.store.dialect)
            db.execute(
                "UPDATE projection_outbox SET state = ?, attempts = attempts + 1, "
                "last_error = ?, projected_sha256 = ? WHERE event_id = ? AND state != 'PROJECTED'",
                (disposition, error, digest, event_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return disposition
