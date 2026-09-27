"""Offline exact-preimage import and single-authority cutover candidate."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.creative_media import CREATIVE_REFS_COLUMN
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalConflict,
    TransactionalVehicleStore,
    _digest,
    _Sql,
)
from global_hybrid_v2.workbench_mutation import AI_SHEET, _header, _rows, _values, _Workbook


@dataclass(frozen=True)
class ImportVehicle:
    vehicle_instance_id: str
    source_row: int
    state: dict[str, str]


@dataclass(frozen=True)
class ImportManifest:
    source_file_id: str
    source_sha256: str
    topology_digest: str
    state_digest: str
    vehicle_count: int
    vehicles: tuple[ImportVehicle, ...]


@dataclass(frozen=True)
class MigrationReceipt:
    state: str
    source_sha256: str
    topology_digest: str
    state_digest: str
    vehicle_count: int
    imported_state_digest: str


def compile_import(preimage: bytes, *, file_id: str) -> ImportManifest:
    if file_id != CANONICAL_WORKBENCH_FILE_ID:
        raise CanonicalConflict("HOLD_MIGRATION_TARGET_FILE_ID")
    book = _Workbook.parse(preimage)
    ai = book.root(AI_SHEET)
    header = _header(ai, book.shared)
    if "VEHICLE_INSTANCE_ID" not in header or "原始媒體Refs" not in header:
        raise CanonicalConflict("HOLD_MIGRATION_REQUIRED_COLUMN_MISSING")
    if CREATIVE_REFS_COLUMN not in header:
        raise CanonicalConflict("HOLD_MIGRATION_CREATIVE_REFS_MISSING")
    rows = _rows(ai)
    names = {column: name for name, column in header.items()}
    vehicles: list[ImportVehicle] = []
    seen: set[str] = set()
    for row in rows[1:]:
        number = int(row.get("r") or 0)
        if number < 2:
            raise CanonicalConflict("HOLD_MIGRATION_ROW_INVALID")
        fields = {names[column]: value for column, value in _values(row, book.shared).items()
                  if column in names}
        vehicle_id = fields.get("VEHICLE_INSTANCE_ID", "").strip()
        if not vehicle_id or vehicle_id in seen:
            raise CanonicalConflict("HOLD_MIGRATION_IDENTITY_DUPLICATE_OR_MISSING")
        seen.add(vehicle_id)
        fields.setdefault("原始媒體Refs", "")
        fields.setdefault(CREATIVE_REFS_COLUMN, "")
        if fields[CREATIVE_REFS_COLUMN].strip():
            raise CanonicalConflict("HOLD_MIGRATION_CREATIVE_LINKAGE_REQUIRED")
        vehicles.append(ImportVehicle(vehicle_id, number, fields))
    topology = {
        "entries": [(name, hashlib.sha256(book.entries[name]).hexdigest())
                    for name in book.entries if name != book.sheets[AI_SHEET]],
        "sheets": book.sheets,
        "header": header,
        "row_order": [row.get("r") for row in rows],
        "vehicle_order": [v.vehicle_instance_id for v in vehicles],
    }
    state = [(v.vehicle_instance_id, v.source_row, v.state) for v in vehicles]
    return ImportManifest(file_id, hashlib.sha256(preimage).hexdigest(),
                          _digest(topology), _digest(state), len(vehicles), tuple(vehicles))


def _db_snapshot(db: _Sql) -> tuple[tuple[str, int, dict[str, Any]], ...]:
    rows = db.execute(
        "SELECT vehicle_instance_id, source_row, source_snapshot FROM vehicle_record ORDER BY source_row"
    ).fetchall()
    from global_hybrid_v2.transactional_vehicle_store import _load_json

    return tuple((str(row[0]), int(row[1]), _load_json(row[2])) for row in rows)


def import_fixed_preimage(store: TransactionalVehicleStore, preimage: bytes,
                          manifest: ImportManifest) -> MigrationReceipt:
    """Import into an empty candidate DB. No Drive access and no production binding."""
    if compile_import(preimage, file_id=manifest.source_file_id) != manifest:
        raise CanonicalConflict("HOLD_MIGRATION_MISMATCH")
    connection = store._open()
    db = _Sql(connection, store.dialect)
    try:
        if store.dialect == "sqlite_test":
            db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM vehicle_record").fetchone()[0] != 0:
            raise CanonicalConflict("HOLD_MIGRATION_TARGET_NOT_EMPTY")
        if db.execute("SELECT COUNT(*) FROM canonical_cutover").fetchone()[0] != 0:
            raise CanonicalConflict("HOLD_MIGRATION_ALREADY_IMPORTED")
        now = datetime.now(UTC).isoformat()
        for vehicle in manifest.vehicles:
            db.execute(
                "INSERT INTO vehicle_record (vehicle_instance_id, revision, durable_identity, "
                "source_snapshot, verified_state, source_row, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vehicle.vehicle_instance_id, 0,
                 db.json({"VEHICLE_INSTANCE_ID": vehicle.vehicle_instance_id}),
                 db.json(vehicle.state), db.json({}), vehicle.source_row, now, now),
            )
        if _digest(_db_snapshot(db)) != manifest.state_digest:
            raise CanonicalConflict("HOLD_MIGRATION_MISMATCH")
        db.execute(
            "INSERT INTO canonical_cutover (singleton, source_file_id, source_sha256, "
            "source_topology_digest, source_state_digest, source_vehicle_count, state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (True, manifest.source_file_id, manifest.source_sha256, manifest.topology_digest,
             manifest.state_digest, manifest.vehicle_count, "IMPORTED"),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return verify_import(store, manifest)


def verify_import(store: TransactionalVehicleStore, manifest: ImportManifest) -> MigrationReceipt:
    connection = store._open()
    try:
        db = _Sql(connection, store.dialect)
        cutover = db.execute(
            "SELECT source_file_id, source_sha256, source_topology_digest, source_state_digest, "
            "source_vehicle_count FROM canonical_cutover WHERE singleton = ?", (True,),
        ).fetchone()
        imported = _db_snapshot(db)
        digest = _digest(imported)
        if cutover != (manifest.source_file_id, manifest.source_sha256, manifest.topology_digest,
                       manifest.state_digest, manifest.vehicle_count) or digest != manifest.state_digest:
            raise CanonicalConflict("HOLD_MIGRATION_MISMATCH")
        return MigrationReceipt("IMPORT_READBACK_PASS", manifest.source_sha256,
                                manifest.topology_digest, manifest.state_digest,
                                manifest.vehicle_count, digest)
    finally:
        connection.close()


def declare_db_canonical(store: TransactionalVehicleStore, manifest: ImportManifest) -> None:
    verify_import(store, manifest)
    connection = store._open()
    try:
        db = _Sql(connection, store.dialect)
        changed = db.execute(
            "UPDATE canonical_cutover SET state = ?, declared_at = ? "
            "WHERE singleton = ? AND state = ?",
            ("DB_CANONICAL", datetime.now(UTC).isoformat(), True, "IMPORTED"),
        ).rowcount
        if changed != 1:
            raise CanonicalConflict("HOLD_CUTOVER_STATE_CONFLICT")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def rollback_eligibility(store: TransactionalVehicleStore) -> str:
    connection = store._open()
    try:
        db = _Sql(connection, store.dialect)
        if db.execute("SELECT COUNT(*) FROM vehicle_mutation").fetchone()[0]:
            return "ROLLBACK_BLOCKED_NEW_CANONICAL_WRITES_PRESENT"
        return "ROLLBACK_TO_FROZEN_XLSX_PREIMAGE_ELIGIBLE"
    finally:
        connection.close()


def mark_prewrite_rollback(store: TransactionalVehicleStore) -> None:
    connection = store._open()
    try:
        db = _Sql(connection, store.dialect)
        if store.dialect == "sqlite_test":
            db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT COUNT(*) FROM vehicle_mutation").fetchone()[0]:
            raise CanonicalConflict("ROLLBACK_BLOCKED_NEW_CANONICAL_WRITES_PRESENT")
        changed = db.execute(
            "UPDATE canonical_cutover SET state = ? WHERE singleton = ? "
            "AND state IN ('IMPORTED', 'DB_CANONICAL')", ("ROLLED_BACK", True),
        ).rowcount
        if changed != 1:
            raise CanonicalConflict("HOLD_CUTOVER_STATE_CONFLICT")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
