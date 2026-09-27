"""Read-only D1 schema admission with an isolated SQLite execution fixture."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MIGRATION_VERSION = "0002_media_asset"
DEFAULT_PREVIOUS_VERSION = "0001_vehicle_knowledge"
EXPECTED_MIGRATION_SHA256 = "d12069b5afd6076eb31fee37888d247f79c7afa8908bd964d93e4527afaa78c4"
TARGET_OBJECTS = frozenset({"media_asset", "creative_media_ref", "media_asset_source_lineage_idx"})
EXPECTED_COLUMNS = {
    "media_asset": frozenset({
        "media_asset_id", "raw_sha256", "object_key", "object_size", "normalized_pixel_hash",
        "perceptual_fingerprint", "width", "height", "mime", "provenance_class",
        "provenance_confidence", "earlier_source_status", "parent_asset_id", "producing_activity",
        "truth_eligibility", "first_seen_at", "source_lineage", "task_lineage",
        "independent_evidence_id",
    }),
    "creative_media_ref": frozenset({
        "creative_ref_id", "media_asset_id", "vehicle_instance_id", "target_column",
        "channels_json", "admitted_at",
    }),
}


class D1MigrationState(StrEnum):
    READY = "READY"
    APPLIED_READBACK_PASS = "APPLIED_READBACK_PASS"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    HOLD_D1_SCHEMA_CONFLICT = "HOLD_D1_SCHEMA_CONFLICT"


@dataclass(frozen=True)
class D1MigrationReceipt:
    state: D1MigrationState
    expected_from: str
    target_version: str
    migration_sha256: str
    schema_fingerprint: str | None = None
    blocker: str | None = None


@dataclass(frozen=True)
class D1SchemaSnapshot:
    revisions: tuple[str, ...]
    objects: dict[str, str]
    columns: dict[str, tuple[str, ...]]


class D1MediaSchemaReadbackHttp:
    def __init__(self, *, base_url: str, read_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or not read_secret:
            raise ValueError("D1_SCHEMA_READBACK_BINDING_INCOMPLETE")
        self.base_url = base_url.rstrip("/")
        self.read_secret = read_secret

    def snapshot(self) -> D1SchemaSnapshot:
        request = Request(
            self.base_url + "/internal/media-schema/readback",
            headers={"Authorization": f"Bearer {self.read_secret}"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
            if result.get("state") != "READBACK":
                raise ValueError("D1_SCHEMA_READBACK_INVALID")
            return D1SchemaSnapshot(
                tuple(result["revisions"]), dict(result["objects"]),
                {key: tuple(value) for key, value in result["columns"].items()},
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("D1_SCHEMA_READBACK_UNAVAILABLE") from exc


def sqlite_snapshot(connection: sqlite3.Connection) -> D1SchemaSnapshot:
    objects = dict(connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE name IN "
        "('media_asset','creative_media_ref','media_asset_source_lineage_idx')"
    ).fetchall())
    has_migrations = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    revisions = tuple(row[0] for row in connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    )) if has_migrations else ()
    columns = {
        name: tuple(row[1] for row in connection.execute(f"PRAGMA table_info({name})"))
        for name in EXPECTED_COLUMNS if name in objects
    }
    return D1SchemaSnapshot(revisions, objects, columns)


class D1MediaMigrationContract:
    def __init__(self, migration_file: Path, *, expected_from: str) -> None:
        self.migration_file = migration_file
        self.expected_from = expected_from

    def _sql(self) -> str:
        raw = self.migration_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != EXPECTED_MIGRATION_SHA256:
            raise ValueError("D1_MIGRATION_FINGERPRINT_MISMATCH")
        return raw.decode("utf-8")

    @staticmethod
    def _fingerprint(snapshot: D1SchemaSnapshot) -> str:
        canonical = "\n".join(
            name + ":" + re.sub(r"\s+", " ", snapshot.objects[name]).strip()
            for name in sorted(TARGET_OBJECTS)
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _expected_snapshot(self) -> D1SchemaSnapshot:
        connection = sqlite3.connect(":memory:")
        connection.executescript(self._sql())
        return sqlite_snapshot(connection)

    def inspect(self, snapshot: D1SchemaSnapshot) -> D1MigrationReceipt:
        try:
            self._sql()
        except (ValueError, UnicodeDecodeError) as exc:
            return D1MigrationReceipt(
                D1MigrationState.HOLD_D1_SCHEMA_CONFLICT, self.expected_from,
                MIGRATION_VERSION, EXPECTED_MIGRATION_SHA256, blocker=str(exc),
            )
        base = {self.expected_from}
        versions = set(snapshot.revisions)
        present = TARGET_OBJECTS & snapshot.objects.keys()
        if versions == base and not present:
            return D1MigrationReceipt(
                D1MigrationState.READY, self.expected_from, MIGRATION_VERSION,
                EXPECTED_MIGRATION_SHA256,
            )
        if versions == base | {MIGRATION_VERSION} and present == TARGET_OBJECTS:
            expected = self._expected_snapshot()
            if (self._fingerprint(snapshot) == self._fingerprint(expected)
                and all(set(snapshot.columns.get(name, ())) == columns
                        for name, columns in EXPECTED_COLUMNS.items())):
                return D1MigrationReceipt(
                    D1MigrationState.ALREADY_APPLIED, self.expected_from, MIGRATION_VERSION,
                    EXPECTED_MIGRATION_SHA256, self._fingerprint(snapshot),
                )
        return D1MigrationReceipt(
            D1MigrationState.HOLD_D1_SCHEMA_CONFLICT, self.expected_from, MIGRATION_VERSION,
            EXPECTED_MIGRATION_SHA256, blocker="D1_SCHEMA_REVISION_OR_OBJECT_CONFLICT",
        )

    def postmigration(self, snapshot: D1SchemaSnapshot) -> D1MigrationReceipt:
        result = self.inspect(snapshot)
        if result.state is D1MigrationState.ALREADY_APPLIED:
            return D1MigrationReceipt(
                D1MigrationState.APPLIED_READBACK_PASS, result.expected_from,
                result.target_version, result.migration_sha256, result.schema_fingerprint,
            )
        return result

    def apply_local_fixture(self, connection: sqlite3.Connection) -> D1MigrationReceipt:
        """Test-only atomic execution; production migration requires a separate operator step."""
        before = self.inspect(sqlite_snapshot(connection))
        if before.state is not D1MigrationState.READY:
            return before
        sql = self._sql()
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n" + sql + "\n"
                "INSERT INTO schema_migrations(version,applied_at) "
                f"VALUES('{MIGRATION_VERSION}',CURRENT_TIMESTAMP);\nCOMMIT;"
            )
        except sqlite3.Error:
            connection.rollback()
            return D1MigrationReceipt(
                D1MigrationState.HOLD_D1_SCHEMA_CONFLICT, self.expected_from,
                MIGRATION_VERSION, EXPECTED_MIGRATION_SHA256,
                blocker="D1_MIGRATION_TRANSACTION_FAILED",
            )
        return self.postmigration(sqlite_snapshot(connection))
