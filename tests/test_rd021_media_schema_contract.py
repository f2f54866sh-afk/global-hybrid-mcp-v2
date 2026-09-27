from __future__ import annotations

import sqlite3
from pathlib import Path

from global_hybrid_v2.media_schema_contract import (
    DEFAULT_PREVIOUS_VERSION,
    MIGRATION_VERSION,
    D1MediaMigrationContract,
    D1MigrationState,
    sqlite_snapshot,
)

MIGRATION = Path(__file__).resolve().parents[1] / "infra/vehicle_knowledge/migrations/0002_media_asset.sql"


def database(revision=DEFAULT_PREVIOUS_VERSION):
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    connection.execute("INSERT INTO schema_migrations VALUES(?, 'test')", (revision,))
    return connection


def contract(path=MIGRATION):
    return D1MediaMigrationContract(path, expected_from=DEFAULT_PREVIOUS_VERSION)


def test_fingerprint_preflight_atomic_local_migration_readback_and_second_run():
    db = database()
    migration = contract()
    assert migration.inspect(sqlite_snapshot(db)).state is D1MigrationState.READY
    first = migration.apply_local_fixture(db)
    assert first.state is D1MigrationState.APPLIED_READBACK_PASS
    assert first.schema_fingerprint and len(first.migration_sha256) == 64
    assert migration.inspect(sqlite_snapshot(db)).state is D1MigrationState.ALREADY_APPLIED
    assert migration.apply_local_fixture(db).state is D1MigrationState.ALREADY_APPLIED
    assert {row[0] for row in db.execute("SELECT version FROM schema_migrations")} == {
        DEFAULT_PREVIOUS_VERSION, MIGRATION_VERSION,
    }


def test_partial_or_incompatible_or_unknown_revision_fails_closed():
    migration = contract()
    partial = database()
    partial.execute("CREATE TABLE media_asset(media_asset_id TEXT PRIMARY KEY)")
    assert migration.inspect(sqlite_snapshot(partial)).state is D1MigrationState.HOLD_D1_SCHEMA_CONFLICT
    unknown = database("unknown-revision")
    assert migration.inspect(sqlite_snapshot(unknown)).state is D1MigrationState.HOLD_D1_SCHEMA_CONFLICT
    incompatible = database()
    incompatible.executescript(MIGRATION.read_text(encoding="utf-8"))
    incompatible.execute("INSERT INTO schema_migrations VALUES(?, 'test')", (MIGRATION_VERSION,))
    incompatible.execute("DROP INDEX media_asset_source_lineage_idx")
    incompatible.execute("CREATE INDEX media_asset_source_lineage_idx ON media_asset(task_lineage)")
    assert migration.postmigration(sqlite_snapshot(incompatible)).state is (
        D1MigrationState.HOLD_D1_SCHEMA_CONFLICT
    )


def test_tampered_migration_fingerprint_holds_before_sql_execution(tmp_path):
    changed = tmp_path / "media.sql"
    changed.write_bytes(MIGRATION.read_bytes() + b"\n-- tampered\n")
    db = database()
    result = contract(changed).apply_local_fixture(db)
    assert result.state is D1MigrationState.HOLD_D1_SCHEMA_CONFLICT
    assert "FINGERPRINT" in result.blocker
    assert "media_asset" not in sqlite_snapshot(db).objects
