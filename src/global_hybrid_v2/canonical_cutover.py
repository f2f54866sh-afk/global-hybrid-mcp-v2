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
class SourceObservation:
    source_observation_id: str
    source_row: int
    state: dict[str, str]
    vehicle_instance_id: str | None
    company_source_state: str
    ai_usage_state: str


@dataclass(frozen=True)
class ImportManifest:
    source_file_id: str
    source_sha256: str
    topology_digest: str
    state_digest: str
    vehicle_count: int
    vehicles: tuple[ImportVehicle, ...]
    observations: tuple[SourceObservation, ...]
    observation_count: int
    unbound_observation_count: int
    source_schema: str


@dataclass(frozen=True)
class MigrationReceipt:
    state: str
    source_sha256: str
    topology_digest: str
    state_digest: str
    vehicle_count: int
    imported_state_digest: str
    source_observation_count: int
    bound_vehicle_count: int
    unbound_observation_count: int


def compile_import(preimage: bytes, *, file_id: str) -> ImportManifest:
    if file_id != CANONICAL_WORKBENCH_FILE_ID:
        raise CanonicalConflict("HOLD_MIGRATION_TARGET_FILE_ID")
    book = _Workbook.parse(preimage)
    ai = book.root(AI_SHEET)
    header = _header(ai, book.shared)
    if "VEHICLE_INSTANCE_ID" not in header or "原始媒體Refs" not in header:
        raise CanonicalConflict("HOLD_MIGRATION_REQUIRED_COLUMN_MISSING")
    source_schema = ("CREATIVE_REFS" if CREATIVE_REFS_COLUMN in header
                     else "PRE_CREATIVE_REFS")
    rows = _rows(ai)
    names = {column: name for name, column in header.items()}
    vehicles: list[ImportVehicle] = []
    observations: list[SourceObservation] = []
    seen: set[str] = set()
    seen_observations: set[str] = set()
    for row in rows[1:]:
        number = int(row.get("r") or 0)
        if number < 2:
            raise CanonicalConflict("HOLD_MIGRATION_ROW_INVALID")
        fields = {names[column]: value for column, value in _values(row, book.shared).items()
                  if column in names}
        vehicle_id = fields.get("VEHICLE_INSTANCE_ID", "").strip()
        if vehicle_id and vehicle_id in seen:
            raise CanonicalConflict("HOLD_MIGRATION_IDENTITY_DUPLICATE_OR_MISSING")
        observation_id = fields.get("來源觀測ID", "").strip()
        if not observation_id and source_schema == "CREATIVE_REFS" and vehicle_id:
            # Legacy all-bound contract fixtures predate the observation key.
            observation_id = f"legacy-bound:{vehicle_id}"
        if not observation_id or observation_id in seen_observations:
            raise CanonicalConflict("HOLD_MIGRATION_OBSERVATION_ID_DUPLICATE_OR_MISSING")
        seen_observations.add(observation_id)
        ai_usage = fields.get("AI使用狀態", "")
        company_state = fields.get("COMPANY_SOURCE_STATE", "")
        if not vehicle_id:
            usage_tokens = {token.strip() for token in ai_usage.split("/")}
            if ({"INSTANCE_READY", "PLATFORM_INSTANCE_READY", "INSTANCE_READY_FOR_8891_FACTS",
                 "INSTANCE_READY_FOR_VERIFIED_FACTS"} & usage_tokens
                or "SOURCE_OBSERVATION_ONLY" not in usage_tokens
                or "NOT_INSTANCE_READY" not in usage_tokens
                or company_state not in {"NOT_IN_CURRENT_SOURCE", "NEW_CURRENT_UNBOUND"}):
                raise CanonicalConflict("HOLD_MIGRATION_IDENTITY_CONTRADICTION")
        else:
            seen.add(vehicle_id)
            vehicles.append(ImportVehicle(vehicle_id, number, fields))
        if fields.get(CREATIVE_REFS_COLUMN, "").strip():
            raise CanonicalConflict("HOLD_MIGRATION_CREATIVE_LINKAGE_REQUIRED")
        observations.append(SourceObservation(observation_id, number, fields,
                                              vehicle_id or None, company_state, ai_usage))
    topology = {
        "entries": [(name, hashlib.sha256(book.entries[name]).hexdigest())
                    for name in book.entries if name != book.sheets[AI_SHEET]],
        "sheets": book.sheets,
        "header": header,
        "row_order": [row.get("r") for row in rows],
        "observation_order": [item.source_observation_id for item in observations],
        "vehicle_order": [v.vehicle_instance_id for v in vehicles],
    }
    state = {
        "observations": [(item.source_observation_id, item.source_row,
                          file_id, hashlib.sha256(preimage).hexdigest(), item.state,
                          item.vehicle_instance_id, item.company_source_state,
                          item.ai_usage_state) for item in observations],
        "vehicles": [(v.vehicle_instance_id, v.source_row, v.state) for v in vehicles],
    }
    return ImportManifest(file_id, hashlib.sha256(preimage).hexdigest(),
                          _digest(topology), _digest(state), len(vehicles), tuple(vehicles),
                          tuple(observations), len(observations),
                          len(observations) - len(vehicles), source_schema)


def _db_snapshot(db: _Sql, source_file_id: str) -> dict[str, list[tuple[Any, ...]]]:
    vehicle_rows = db.execute(
        "SELECT vehicle_instance_id, source_row, source_snapshot FROM vehicle_record ORDER BY source_row"
    ).fetchall()
    observation_rows = db.execute(
        "SELECT source_observation_id, source_row, source_file_id, source_sha256, "
        "source_snapshot, vehicle_instance_id, "
        "company_source_state, ai_usage_state FROM vehicle_source_observation "
        "WHERE source_file_id = ? ORDER BY source_row", (source_file_id,),
    ).fetchall()
    from global_hybrid_v2.transactional_vehicle_store import _load_json

    return {
        "observations": [(str(row[0]), int(row[1]), str(row[2]), str(row[3]),
                          _load_json(row[4]), row[5], str(row[6]), str(row[7]))
                         for row in observation_rows],
        "vehicles": [(str(row[0]), int(row[1]), _load_json(row[2])) for row in vehicle_rows],
    }


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
        if db.execute("SELECT COUNT(*) FROM vehicle_source_observation").fetchone()[0] != 0:
            raise CanonicalConflict("HOLD_MIGRATION_TARGET_NOT_EMPTY")
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
        for observation in manifest.observations:
            db.execute(
                "INSERT INTO vehicle_source_observation (source_observation_id, source_file_id, "
                "source_sha256, source_row, source_snapshot, vehicle_instance_id, "
                "company_source_state, ai_usage_state, imported_at, binding_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (observation.source_observation_id, manifest.source_file_id,
                 manifest.source_sha256, observation.source_row, db.json(observation.state),
                 observation.vehicle_instance_id, observation.company_source_state,
                 observation.ai_usage_state, now,
                 "INSTANCE_BOUND" if observation.vehicle_instance_id else "UNBOUND_OBSERVATION"),
            )
        if _digest(_db_snapshot(db, manifest.source_file_id)) != manifest.state_digest:
            raise CanonicalConflict("HOLD_MIGRATION_MISMATCH")
        db.execute(
            "INSERT INTO canonical_cutover (singleton, source_file_id, source_sha256, "
            "source_topology_digest, source_state_digest, source_vehicle_count, "
            "source_observation_count, bound_vehicle_count, unbound_observation_count, state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (True, manifest.source_file_id, manifest.source_sha256, manifest.topology_digest,
             manifest.state_digest, manifest.vehicle_count, manifest.observation_count,
             manifest.vehicle_count, manifest.unbound_observation_count, "IMPORTED"),
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
            "source_vehicle_count, source_observation_count, bound_vehicle_count, "
            "unbound_observation_count FROM canonical_cutover WHERE singleton = ?", (True,),
        ).fetchone()
        imported = _db_snapshot(db, manifest.source_file_id)
        digest = _digest(imported)
        expected_cutover = (
            manifest.source_file_id, manifest.source_sha256, manifest.topology_digest,
            manifest.state_digest, manifest.vehicle_count, manifest.observation_count,
            manifest.vehicle_count, manifest.unbound_observation_count,
        )
        if cutover != expected_cutover or digest != manifest.state_digest:
            raise CanonicalConflict("HOLD_MIGRATION_MISMATCH")
        return MigrationReceipt("IMPORT_READBACK_PASS", manifest.source_sha256,
                                manifest.topology_digest, manifest.state_digest,
                                manifest.vehicle_count, digest, manifest.observation_count,
                                manifest.vehicle_count, manifest.unbound_observation_count)
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
