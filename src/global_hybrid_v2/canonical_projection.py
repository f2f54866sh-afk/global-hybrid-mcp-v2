"""Idempotent outbox contract and a strictly read-only XLSX projection verifier."""
from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalConflict,
    TransactionalVehicleStore,
    VehicleProjectionState,
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


@dataclass(frozen=True)
class ProjectionObservation:
    vehicle_instance_id: str
    projected_revision: int
    file_version: str
    file_sha256: str
    row_digest: str
    raw_preimage: bytes


class ProjectionSink(Protocol):
    """Implementations must atomically bind the write to observation's exact preimage."""

    def replace_if_preimage(self, observed: ProjectionObservation,
                            desired: ProjectionEvent, state: VehicleProjectionState) -> None: ...


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

    def build(self, preimage: bytes, event: ProjectionEvent, state: VehicleProjectionState) -> bytes:
        if (event.vehicle_instance_id != state.vehicle_instance_id
            or event.canonical_revision > state.canonical_revision):
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
        projected = _projection_revision(_values(target, book.shared).get(header[REVISION_COLUMN], ""))
        if projected > state.canonical_revision:
            raise CanonicalConflict("HOLD_PROJECTION_REVISION_REGRESSION")
        if projected == state.canonical_revision:
            _verify_row_values(_values(target, book.shared), header, state)
            return preimage
        for field, value in state.current_state.items():
            column = header[field]
            current = _values(target, book.shared).get(column, "")
            if current != str(value):
                _set_cell(_cell(target, column, create=True), value)
        revision = _values(target, book.shared).get(header[REVISION_COLUMN], "")
        if revision != str(state.canonical_revision):
            _set_cell(_cell(target, header[REVISION_COLUMN], create=True), str(state.canonical_revision))
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


def _projection_revision(raw: str) -> int:
    if not raw:
        return 0
    try:
        revision = int(raw)
    except ValueError as exc:
        raise CanonicalConflict("HOLD_PROJECTION_REVISION_INVALID") from exc
    if revision < 0 or str(revision) != raw:
        raise CanonicalConflict("HOLD_PROJECTION_REVISION_INVALID")
    return revision


def _verify_row_values(values: dict[int, str], header: dict[str, int],
                       state: VehicleProjectionState) -> None:
    if any(field not in header or values.get(header[field], "") != str(value)
           for field, value in state.current_state.items()):
        raise CanonicalConflict("HOLD_PROJECTION_FIELD_MISMATCH")


class XlsxProjectionVerifier:
    """No write method is accepted or called at this boundary."""

    def __init__(self, read: ProjectionReadTransport, *, file_id: str = CANONICAL_WORKBENCH_FILE_ID):
        if file_id != CANONICAL_WORKBENCH_FILE_ID:
            raise CanonicalConflict("HOLD_PROJECTION_TARGET_MISMATCH")
        self.read, self.file_id = read, file_id

    def observe(self, vehicle_instance_id: str) -> ProjectionObservation:
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
            if values.get(header["VEHICLE_INSTANCE_ID"]) == vehicle_instance_id:
                matching.append((row, values))
        if len(matching) != 1:
            raise CanonicalConflict("HOLD_PROJECTION_IDENTITY_MISMATCH")
        row, values = matching[0]
        return ProjectionObservation(
            vehicle_instance_id,
            _projection_revision(values.get(header[REVISION_COLUMN], "")),
            str(before["version"]), hashlib.sha256(payload).hexdigest(),
            hashlib.sha256(ET.tostring(row)).hexdigest(), payload,
        )

    def verify_observation(self, observed: ProjectionObservation,
                           state: VehicleProjectionState) -> str:
        if observed.vehicle_instance_id != state.vehicle_instance_id:
            raise CanonicalConflict("HOLD_PROJECTION_IDENTITY_MISMATCH")
        if observed.projected_revision != state.canonical_revision:
            raise CanonicalConflict("HOLD_PROJECTION_REVISION_MISMATCH")
        book = _Workbook.parse(observed.raw_preimage)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        matches = [row for row in _rows(ai)[1:] if _values(row, book.shared).get(
            header["VEHICLE_INSTANCE_ID"]
        ) == state.vehicle_instance_id]
        if len(matches) != 1 or hashlib.sha256(ET.tostring(matches[0])).hexdigest() != observed.row_digest:
            raise CanonicalConflict("HOLD_PROJECTION_OBSERVATION_MISMATCH")
        _verify_row_values(_values(matches[0], book.shared), header, state)
        return observed.file_sha256

    def verify_baseline(self, observed: ProjectionObservation,
                        state: VehicleProjectionState) -> None:
        if observed.projected_revision != 0 or observed.vehicle_instance_id != state.vehicle_instance_id:
            raise CanonicalConflict("HOLD_PROJECTION_BASELINE_CONFLICT")
        book = _Workbook.parse(observed.raw_preimage)
        ai = book.root(AI_SHEET)
        header = _header(ai, book.shared)
        matches = [row for row in _rows(ai)[1:] if _values(row, book.shared).get(
            header["VEHICLE_INSTANCE_ID"]
        ) == state.vehicle_instance_id]
        if len(matches) != 1:
            raise CanonicalConflict("HOLD_PROJECTION_IDENTITY_MISMATCH")
        values = _values(matches[0], book.shared)
        if any(field not in header or values.get(header[field], "") != str(value)
               for field, value in state.source_snapshot.items()):
            raise CanonicalConflict("HOLD_PROJECTION_BASELINE_FIELD_CONFLICT")

    def verify(self, event: ProjectionEvent, state: VehicleProjectionState) -> str:
        if event.vehicle_instance_id != state.vehicle_instance_id or (
            event.canonical_revision > state.canonical_revision
        ):
            raise CanonicalConflict("HOLD_PROJECTION_SOURCE_IDENTITY_MISMATCH")
        return self.verify_observation(self.observe(event.vehicle_instance_id), state)


class ProjectionOutboxWorker:
    """Latest-state monotonic convergence. A sink without atomic preimage CAS is inadmissible."""

    def __init__(self, store: TransactionalVehicleStore, sink: ProjectionSink,
                 verifier: XlsxProjectionVerifier):
        self.store, self.sink, self.verifier = store, sink, verifier

    def run(self, event_id: str) -> str:
        connection = self.store._open()
        db = _Sql(connection, self.store.dialect)
        try:
            if self.store.dialect == "sqlite_test":
                db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT vehicle_instance_id, canonical_revision, state FROM projection_outbox "
                "WHERE event_id = ?", (event_id,),
            ).fetchone()
            if row is None:
                raise CanonicalConflict("HOLD_PROJECTION_EVENT_MISSING")
            if row[2] in {"PROJECTED", "SUPERSEDED_BY_LATER_REVISION", "HOLD_CONFLICT"}:
                return str(row[2])
            event = ProjectionEvent(event_id, str(row[0]), int(row[1]))
            if self.store.dialect == "postgres":
                locked = db.execute(
                    "SELECT vehicle_instance_id FROM vehicle_record WHERE vehicle_instance_id = ? "
                    "FOR UPDATE", (event.vehicle_instance_id,),
                ).fetchone()
                if locked is None:
                    raise CanonicalConflict("HOLD_CANONICAL_PROJECTION_SOURCE_MISSING")
            try:
                if db.execute(
                    "SELECT COUNT(*) FROM projection_outbox WHERE vehicle_instance_id = ? "
                    "AND state = 'HOLD_CONFLICT'", (event.vehicle_instance_id,),
                ).fetchone()[0]:
                    raise CanonicalConflict("HOLD_PROJECTION_VEHICLE_ALREADY_HELD")
                state = self.store._projection_state(db, event.vehicle_instance_id)
                if state is None or state.canonical_revision < event.canonical_revision:
                    raise CanonicalConflict("HOLD_CANONICAL_PROJECTION_SOURCE_MISSING")
                observed = self.verifier.observe(event.vehicle_instance_id)
                cursor = db.execute(
                    "SELECT projected_revision, projected_row_digest "
                    "FROM vehicle_projection_cursor WHERE vehicle_instance_id = ?",
                    (event.vehicle_instance_id,),
                ).fetchone()
                self._admit_observation(observed, state, cursor)
                desired = ProjectionEvent(event.event_id, event.vehicle_instance_id,
                                          state.canonical_revision)
                if observed.projected_revision < state.canonical_revision:
                    self.sink.replace_if_preimage(observed, desired, state)
                    observed = self.verifier.observe(event.vehicle_instance_id)
                digest = self.verifier.verify_observation(observed, state)
                self._record_success(db, event, observed, digest)
                connection.commit()
                outcome = db.execute(
                    "SELECT state FROM projection_outbox WHERE event_id = ?", (event_id,),
                ).fetchone()
                return str(outcome[0])
            except CanonicalConflict as exc:
                self._record_failure(db, event_id, "HOLD_CONFLICT", str(exc))
                connection.commit()
                return "HOLD_CONFLICT"
            except Exception as exc:
                self._record_failure(db, event_id, "PROJECTION_FAILED", type(exc).__name__)
                connection.commit()
                return "PROJECTION_FAILED"
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _admit_observation(self, observed: ProjectionObservation, state: VehicleProjectionState,
                           cursor: tuple[int, str] | None) -> None:
        if observed.projected_revision > state.canonical_revision:
            raise CanonicalConflict("HOLD_PROJECTION_AHEAD_OF_CANONICAL")
        if cursor is None:
            if observed.projected_revision == 0:
                self.verifier.verify_baseline(observed, state)
            elif observed.projected_revision == state.canonical_revision:
                self.verifier.verify_observation(observed, state)
            else:
                raise CanonicalConflict("HOLD_PROJECTION_CURSOR_MISSING")
            return
        previous_revision, previous_row_digest = int(cursor[0]), str(cursor[1])
        if observed.projected_revision < previous_revision:
            raise CanonicalConflict("HOLD_PROJECTION_REVISION_REGRESSION")
        if observed.projected_revision == previous_revision and observed.row_digest != previous_row_digest:
            raise CanonicalConflict("HOLD_PROJECTION_EXTERNAL_ROW_MUTATION")
        if previous_revision < observed.projected_revision < state.canonical_revision:
            raise CanonicalConflict("HOLD_PROJECTION_UNVERIFIED_INTERMEDIATE_REVISION")
        if observed.projected_revision == state.canonical_revision:
            self.verifier.verify_observation(observed, state)

    @staticmethod
    def _record_success(db: _Sql, event: ProjectionEvent, observed: ProjectionObservation,
                        digest: str) -> None:
        now = datetime.now(UTC).isoformat()
        changed = db.execute(
            "INSERT INTO vehicle_projection_cursor (vehicle_instance_id, projected_revision, "
            "projected_row_digest, projected_sha256, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(vehicle_instance_id) DO UPDATE SET "
            "projected_revision = excluded.projected_revision, "
            "projected_row_digest = excluded.projected_row_digest, "
            "projected_sha256 = excluded.projected_sha256, updated_at = excluded.updated_at "
            "WHERE excluded.projected_revision >= vehicle_projection_cursor.projected_revision",
            (event.vehicle_instance_id, observed.projected_revision,
             observed.row_digest, digest, now),
        ).rowcount
        if changed != 1:
            raise CanonicalConflict("HOLD_PROJECTION_CURSOR_REGRESSION")
        db.execute(
            "UPDATE projection_outbox SET state = CASE WHEN canonical_revision = ? "
            "THEN 'PROJECTED' ELSE 'SUPERSEDED_BY_LATER_REVISION' END, "
            "satisfied_by_revision = ?, projected_sha256 = ?, last_error = NULL, "
            "updated_at = ?, attempts = attempts + CASE WHEN event_id = ? THEN 1 ELSE 0 END "
            "WHERE vehicle_instance_id = ? AND canonical_revision <= ? "
            "AND state IN ('PROJECTION_PENDING', 'PROJECTION_FAILED')",
            (observed.projected_revision, observed.projected_revision, digest, now,
             event.event_id, event.vehicle_instance_id, observed.projected_revision),
        )

    @staticmethod
    def _record_failure(db: _Sql, event_id: str, disposition: str, blocker: str) -> None:
        if disposition not in {"PROJECTION_FAILED", "HOLD_CONFLICT"}:
            raise ValueError("invalid projection failure disposition")
        db.execute(
            "UPDATE projection_outbox SET state = ?, attempts = attempts + 1, "
            "last_error = ?, updated_at = ? WHERE event_id = ? "
            "AND state IN ('PROJECTION_PENDING', 'PROJECTION_FAILED')",
            (disposition, blocker, datetime.now(UTC).isoformat(), event_id),
        )
