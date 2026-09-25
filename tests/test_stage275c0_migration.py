"""Explicit receipt-schema migration contract against disposable PostgreSQL."""
from __future__ import annotations

import os
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from global_hybrid_v2.migrations import (
    MigrationError,
    _upgrade_in_transaction,
    check_expected_commit,
    current_version,
    plan,
    upgrade,
    verify_schema_v1,
)

BASE = os.getenv("STAGE275B_TEST_DSN")
if not BASE and os.getenv("STAGE275B_TEST_HOST"):
    BASE = make_conninfo(
        host=os.environ["STAGE275B_TEST_HOST"],
        port=os.getenv("STAGE275B_TEST_PORT", "5432"),
        dbname=os.environ["STAGE275B_TEST_DB"],
        user=os.environ["STAGE275B_TEST_USER"],
    )
if not BASE:
    pytest.skip("disposable PostgreSQL DSN required", allow_module_level=True)
PARTS = conninfo_to_dict(BASE)
assert PARTS.get("host") in {"127.0.0.1", "localhost"}
assert PARTS.get("dbname", "").startswith("stage275b_")


@pytest.fixture
def db():
    schema = f"stage275c0_{uuid4().hex}"
    with psycopg.connect(BASE) as con:
        con.execute(f'CREATE SCHEMA "{schema}"')
    dsn = make_conninfo(BASE, options=f"-c search_path={schema}", connect_timeout=2)
    try:
        yield dsn
    finally:
        with psycopg.connect(BASE) as con:
            con.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_m1_fresh_to_v1(db):
    assert current_version(db) == 0
    assert plan(db, 0, 1) == (0, 1)
    assert upgrade(db, 0, 1) == 1
    assert current_version(db) == 1 and verify_schema_v1(db)


def test_m2_v1_to_v1_idempotent(db):
    upgrade(db, 0, 1)
    with psycopg.connect(db) as con:
        con.execute("INSERT INTO exact_object_source_receipt "
                    "(request_id,task_id,platform,requested_object_id,receipt,attempted_at) "
                    "VALUES ('keep','task','8891','4806397','{}'::jsonb,now())")
    assert upgrade(db, 1, 1) == 1
    with psycopg.connect(db) as con:
        assert con.execute("SELECT count(*) FROM exact_object_source_receipt").fetchone()[0] == 1


def test_m3_newer_unknown_version_rejected(db):
    upgrade(db, 0, 1)
    with psycopg.connect(db) as con:
        con.execute("UPDATE schema_migrations SET version=2 WHERE component='exact_object_receipt'")
    with pytest.raises(MigrationError):
        current_version(db)
    with pytest.raises(MigrationError):
        upgrade(db, 2, 1)


def test_m4_partial_schema_fails_closed(db):
    with psycopg.connect(db) as con:
        con.execute("CREATE TABLE exact_object_source_receipt (id bigint)")
    with pytest.raises(MigrationError):
        upgrade(db, 0, 1)
    with psycopg.connect(db) as con:
        assert con.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None


def test_m5_types_constraints_and_index_readback(db):
    upgrade(db, 0, 1)
    assert verify_schema_v1(db)
    with psycopg.connect(db) as con:
        con.execute("DROP INDEX exact_object_source_latest_idx")
    with pytest.raises(MigrationError):
        verify_schema_v1(db)


def test_m6_transaction_rollback_after_ddl(db):
    with pytest.raises(RuntimeError):
        with psycopg.connect(db) as con:
            _upgrade_in_transaction(con, 0, 1)
            raise RuntimeError("injected failure before commit")
    with psycopg.connect(db) as con:
        assert con.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None
        assert con.execute("SELECT to_regclass('exact_object_source_receipt')").fetchone()[0] is None


def test_m7_wrong_commit_rejected_by_workflow_gate():
    with pytest.raises(MigrationError):
        check_expected_commit("0" * 40, actual="1" * 40)
    assert check_expected_commit("a" * 40, actual="a" * 40)
    workflow = Path(__file__).parents[1] / ".github/workflows/production-db-migrate.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text and "check-commit" in text
    assert "push:" not in text and "schedule:" not in text
    rejected = subprocess.run(
        [sys.executable, "-m", "global_hybrid_v2.migrations", "exact_object_receipt",
         "check-commit", "--expected-git-commit", "0" * 40],
        capture_output=True, text=True,
    )
    assert rejected.returncode != 0


def test_m8_wrong_expected_from_rejected(db):
    with pytest.raises(MigrationError):
        upgrade(db, 1, 1)
    upgrade(db, 0, 1)
    with pytest.raises(MigrationError):
        plan(db, 0, 1)


def test_m9_runtime_does_not_auto_migrate():
    root = Path(__file__).parents[1]
    for path in (root / "Dockerfile", root / "src/global_hybrid_v2/application.py",
                 root / "src/global_hybrid_v2/adapters/mcp_server.py"):
        text = path.read_text(encoding="utf-8")
        assert "global_hybrid_v2.migrations" not in text
        assert "POSTGRES_SCHEMA" not in text


def test_m10_old_app_revision_ignores_additive_v1(db, tmp_path):
    upgrade(db, 0, 1)
    root = Path(__file__).parents[1]
    old = "1b51e965d91c804ef24c134644782da112d69092"
    source = subprocess.run(
        ["git", "show", f"{old}:src/global_hybrid_v2/application.py"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    assert "DATABASE_URL" not in source and "exact_object_source_receipt" not in source
    archive = subprocess.run(
        ["git", "archive", "--format=tar", old, "src/global_hybrid_v2"],
        cwd=root, check=True, capture_output=True,
    ).stdout
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as tar:
        tar.extractall(tmp_path, filter="data")
    env = dict(os.environ, PYTHONPATH=str(tmp_path / "src"), DATABASE_URL=db)
    started = subprocess.run(
        [sys.executable, "-c", "from global_hybrid_v2.application import create_application; "
         "assert create_application() is not None"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert started.returncode == 0, started.stderr


def test_m11_database_unavailable_fails(db):
    parts = conninfo_to_dict(db)
    parts["port"] = "1"
    bad = make_conninfo(**parts)
    with pytest.raises((psycopg.OperationalError, MigrationError)):
        upgrade(bad, 0, 1)


def test_m12_repeated_operator_invocation_stable(db):
    env = dict(os.environ, MIGRATION_DATABASE_URL=db)
    base = [sys.executable, "-m", "global_hybrid_v2.migrations", "exact_object_receipt"]
    for action, from_version in (("plan", 0), ("upgrade", 0), ("upgrade", 1), ("upgrade", 1)):
        result = subprocess.run(
            [*base, action, "--expected-from", str(from_version), "--target-version", "1"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 0, result.stderr
    status = subprocess.run([*base, "status"], env=env, capture_output=True, text=True, timeout=20)
    assert status.returncode == 0 and '"current_db_schema_version": 1' in status.stdout
    with psycopg.connect(db) as con:
        assert con.execute("SELECT count(*) FROM schema_migrations "
                           "WHERE component='exact_object_receipt'").fetchone()[0] == 1
