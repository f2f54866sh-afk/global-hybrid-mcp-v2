"""Permanent real-PostgreSQL migration and target qualification for RD-021 CI."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "infra" / "vehicle_canonical"
REQUIRED_TABLES = {
    "vehicle_record", "vehicle_field_evidence", "vehicle_mutation",
    "vehicle_media_link", "projection_outbox", "canonical_cutover",
    "vehicle_projection_cursor", "vehicle_source_observation",
}


class PostgresTestTargetBlocked(RuntimeError):
    pass


def guarded_dsn(value: str | None = None) -> str:
    """Reject every target except the job-local, disposable RD-021 test DB."""
    value = os.environ.get("RD021_TEST_POSTGRES_DSN") if value is None else value
    if (not value or os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("CI") != "true"
        or os.environ.get("RD021_REQUIRE_POSTGRES") != "1"
        or os.environ.get("PGHOSTADDR") or os.environ.get("PGSERVICE")):
        raise PostgresTestTargetBlocked("TEST_BLOCKED / POSTGRES_TEST_TARGET_NOT_EPHEMERAL")
    try:
        parts = conninfo_to_dict(value)
    except Exception as exc:
        raise PostgresTestTargetBlocked(
            "TEST_BLOCKED / POSTGRES_TEST_TARGET_NOT_EPHEMERAL"
        ) from exc
    if (parts.get("host") not in {"localhost", "127.0.0.1"}
        or parts.get("dbname") != "rd021_test"
        or parts.get("port") != "5432"
        or parts.get("user") != "postgres"
        or parts.get("password") != "postgres"
        or set(parts) - {"host", "dbname", "port", "user", "password"}):
        raise PostgresTestTargetBlocked("TEST_BLOCKED / POSTGRES_TEST_TARGET_NOT_EPHEMERAL")
    return value


def migration_chain() -> list[tuple[Path, bytes]]:
    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files or [int(path.name[:4]) for path in files] != list(range(1, len(files) + 1)):
        raise AssertionError("HOLD_POSTGRES_MIGRATION_CHAIN_GAP")
    return [(path, path.read_bytes()) for path in files]


def reset_and_migrate(dsn: str) -> None:
    guarded_dsn(dsn)
    with psycopg.connect(dsn, autocommit=False) as connection:
        connection.execute("DROP SCHEMA public CASCADE")
        connection.execute("CREATE SCHEMA public")
        for _, raw in migration_chain():
            connection.execute(raw.decode("utf-8"))
    introspect_schema(dsn)


def introspect_schema(dsn: str) -> None:
    guarded_dsn(dsn)
    with psycopg.connect(dsn, autocommit=False) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )}
        assert REQUIRED_TABLES <= tables
        columns = {(row[0], row[1]): (row[2], row[3]) for row in connection.execute(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema = 'public'"
        )}
        for table, names in {
            "vehicle_record": ("vehicle_instance_id", "revision", "source_snapshot",
                               "verified_state", "durable_identity"),
            "projection_outbox": ("event_id", "state", "satisfied_by_revision"),
            "vehicle_projection_cursor": ("vehicle_instance_id", "projected_revision",
                                          "projected_row_digest"),
            "vehicle_source_observation": ("source_observation_id", "source_row",
                                           "source_snapshot", "vehicle_instance_id"),
            "canonical_cutover": ("source_observation_count", "bound_vehicle_count",
                                  "unbound_observation_count"),
        }.items():
            assert all((table, name) in columns for name in names)
        for name in ("source_snapshot", "verified_state", "durable_identity"):
            assert columns["vehicle_record", name] == ("jsonb", "NO")
        assert columns["vehicle_source_observation", "source_snapshot"] == ("jsonb", "NO")
        assert columns["vehicle_source_observation", "vehicle_instance_id"][1] == "YES"
        constraints = {(row[0], row[1]): (row[2], row[3]) for row in connection.execute(
            "SELECT c.conrelid::regclass::text, c.conname, c.contype, "
            "pg_get_constraintdef(c.oid) FROM pg_constraint c "
            "WHERE c.connamespace = 'public'::regnamespace"
        )}
        for table in REQUIRED_TABLES:
            assert any(key[0] == table and value[0] == "p" for key, value in constraints.items())
        assert any(value[0] == "f" for value in constraints.values())
        assert any(value[0] == "c" for value in constraints.values())
        observation_constraints = [value for (table, _), value in constraints.items()
                                   if table == "vehicle_source_observation"]
        assert any(kind == "f" and "vehicle_record(vehicle_instance_id)" in definition
                   for kind, definition in observation_constraints)
        assert any(kind == "u" and "source_row" in definition
                   for kind, definition in observation_constraints)
        for field in ("source_row", "source_observation_id", "vehicle_instance_id"):
            assert any(kind == "c" and field in definition
                       for kind, definition in observation_constraints)
        outbox_checks = [definition for (table, _), (kind, definition) in constraints.items()
                         if table == "projection_outbox" and kind == "c"]
        assert any("SUPERSEDED_BY_LATER_REVISION" in item and "HOLD_CONFLICT" in item
                   for item in outbox_checks)
        indexes = {row[0]: row[1] for row in connection.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"
        )}
        for name in ("vehicle_record_source_row_unique", "vehicle_verified_vin_unique",
                     "vehicle_verified_plate_unique",
                     "vehicle_source_observation_bound_vehicle_unique"):
            assert "UNIQUE" in indexes[name]
        assert "WHERE" in indexes["vehicle_verified_vin_unique"]
        assert "WHERE" in indexes["vehicle_verified_plate_unique"]
        assert "WHERE" in indexes["vehicle_source_observation_bound_vehicle_unique"]


def main() -> None:
    dsn = guarded_dsn()
    with psycopg.connect(dsn, autocommit=False) as connection:
        version = connection.execute("SHOW server_version").fetchone()[0]
    print(f"CANDIDATE_SHA={os.environ.get('GITHUB_SHA', 'LOCAL')}")
    print(f"POSTGRES_SERVER_VERSION={version}")
    for path, raw in migration_chain():
        print(f"MIGRATION_{path.name[:4]}_SHA256={hashlib.sha256(raw).hexdigest()}")
    reset_and_migrate(dsn)
    print("MIGRATION_CHAIN_AND_INTROSPECTION=PASS")


if __name__ == "__main__":
    main()
