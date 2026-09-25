"""Explicit, operator-run migrations for the exact-object receipt store.

This module is intentionally absent from application startup and request paths.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any

import psycopg

from global_hybrid_v2.governance.postgres_exact_object_source import POSTGRES_SCHEMA

_COMPONENT = "exact_object_receipt"
_VERSION = 1
_LEDGER_SCHEMA = """CREATE TABLE schema_migrations (
    component TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version >= 1),
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""
_EXPECTED_COLUMNS = {
    "id": ("bigint", "NO"),
    "request_id": ("text", "NO"),
    "task_id": ("text", "NO"),
    "platform": ("text", "NO"),
    "requested_object_id": ("text", "NO"),
    "receipt": ("jsonb", "NO"),
    "raw_capture": ("bytea", "YES"),
    "attempted_at": ("timestamp with time zone", "NO"),
}


class MigrationError(RuntimeError):
    pass


def _exists(connection: Any, relation: str) -> bool:
    return connection.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0] is not None


def _verify_schema(connection: Any) -> bool:
    if not _exists(connection, "exact_object_source_receipt"):
        raise MigrationError("RECEIPT_TABLE_MISSING")
    columns = {
        row[0]: (row[1], row[2])
        for row in connection.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='exact_object_source_receipt'"
        )
    }
    if set(columns) != set(_EXPECTED_COLUMNS):
        raise MigrationError("RECEIPT_COLUMNS_MISMATCH")
    for name, (data_type, nullable) in _EXPECTED_COLUMNS.items():
        if columns[name] != (data_type, nullable):
            raise MigrationError("RECEIPT_COLUMN_TYPE_MISMATCH")
    identity = connection.execute(
        "SELECT is_identity FROM information_schema.columns "
        "WHERE table_schema=current_schema() AND table_name='exact_object_source_receipt' "
        "AND column_name='id'"
    ).fetchone()
    if identity != ("YES",):
        raise MigrationError("RECEIPT_IDENTITY_MISSING")
    constraints = {
        row[0]: row[1]
        for row in connection.execute(
            "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='exact_object_source_receipt'::regclass"
        )
    }
    if constraints.get("p") != "PRIMARY KEY (id)" or constraints.get("u") != "UNIQUE (request_id)":
        raise MigrationError("RECEIPT_CONSTRAINT_MISMATCH")
    indexes = [
        row[0] for row in connection.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema() "
            "AND tablename='exact_object_source_receipt'"
        )
    ]
    if not any(
        "exact_object_source_latest_idx" in value
        and "(task_id, platform, requested_object_id, id DESC)" in value
        for value in indexes
    ):
        raise MigrationError("LATEST_INDEX_MISSING")
    return True


def _current_version(connection: Any) -> int:
    ledger = _exists(connection, "schema_migrations")
    receipt = _exists(connection, "exact_object_source_receipt")
    if not ledger:
        if receipt:
            raise MigrationError("PARTIAL_SCHEMA_WITHOUT_LEDGER")
        return 0
    rows = list(connection.execute(
        "SELECT version FROM schema_migrations WHERE component=%s", (_COMPONENT,)
    ))
    if len(rows) > 1:
        raise MigrationError("DUPLICATE_SCHEMA_LEDGER")
    if not rows:
        if receipt:
            raise MigrationError("UNOWNED_RECEIPT_TABLE")
        return 0
    version = rows[0][0]
    if version != _VERSION:
        raise MigrationError("UNKNOWN_SCHEMA_VERSION")
    _verify_schema(connection)
    return version


def current_version(dsn: str) -> int:
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        return _current_version(connection)


def verify_schema_v1(dsn: str) -> bool:
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        if _current_version(connection) != 1:
            raise MigrationError("SCHEMA_V1_NOT_INSTALLED")
        return _verify_schema(connection)


def _validate_transition(actual: int, expected_from: int, target: int) -> None:
    if actual != expected_from:
        raise MigrationError("EXPECTED_SCHEMA_FROM_MISMATCH")
    if target != _VERSION or actual not in (0, 1):
        raise MigrationError("UNSUPPORTED_SCHEMA_TRANSITION")


def plan(dsn: str, expected_from: int, target: int) -> tuple[int, int]:
    actual = current_version(dsn)
    _validate_transition(actual, expected_from, target)
    return actual, target


def _upgrade_in_transaction(connection: Any, expected_from: int, target: int) -> int:
    connection.execute("SELECT pg_advisory_xact_lock(275, 1)")
    actual = _current_version(connection)
    _validate_transition(actual, expected_from, target)
    if actual == target:
        return target
    if not _exists(connection, "schema_migrations"):
        connection.execute(_LEDGER_SCHEMA)
    connection.execute(POSTGRES_SCHEMA)
    _verify_schema(connection)
    connection.execute(
        "INSERT INTO schema_migrations (component, version) VALUES (%s, %s)",
        (_COMPONENT, target),
    )
    if _current_version(connection) != target:
        raise MigrationError("MIGRATION_READBACK_FAILED")
    return target


def upgrade(dsn: str, expected_from: int, target: int) -> int:
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        result = _upgrade_in_transaction(connection, expected_from, target)
    if current_version(dsn) != target or not verify_schema_v1(dsn):
        raise MigrationError("POST_COMMIT_READBACK_FAILED")
    return result


def check_expected_commit(expected: str, *, actual: str | None = None) -> bool:
    if actual is None:
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected) or actual != expected:
        raise MigrationError("EXPECTED_GIT_COMMIT_MISMATCH")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="global_hybrid_v2.migrations")
    parser.add_argument("component", choices=[_COMPONENT])
    parser.add_argument("action", choices=["check-commit", "status", "plan", "upgrade"])
    parser.add_argument("--expected-git-commit")
    parser.add_argument("--expected-from", type=int)
    parser.add_argument("--target-version", type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == "check-commit":
            if not args.expected_git_commit:
                raise MigrationError("EXPECTED_GIT_COMMIT_REQUIRED")
            check_expected_commit(args.expected_git_commit)
            print(json.dumps({"git_commit_match": True}))
            return 0
        dsn = os.getenv("MIGRATION_DATABASE_URL")
        if not dsn:
            raise MigrationError("MIGRATION_DATABASE_URL_REQUIRED")
        if args.action == "status":
            version = current_version(dsn)
        else:
            if args.expected_from is None or args.target_version is None:
                raise MigrationError("EXPECTED_TRANSITION_REQUIRED")
            version = (plan(dsn, args.expected_from, args.target_version)[0]
                       if args.action == "plan" else
                       upgrade(dsn, args.expected_from, args.target_version))
        print(json.dumps({"component": _COMPONENT, "current_db_schema_version": version,
                          "target_schema_version": args.target_version}))
        return 0
    except (MigrationError, psycopg.Error, OSError, subprocess.CalledProcessError) as exc:
        print(f"migration failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
