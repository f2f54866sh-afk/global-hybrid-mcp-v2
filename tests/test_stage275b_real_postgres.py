"""Real PostgreSQL validation. Requires an isolated loopback stage275b_* database."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from global_hybrid_v2.governance.exact_object_source import ExactObjectRequest, HttpResponse
from global_hybrid_v2.governance.postgres_exact_object_source import (
    POSTGRES_SCHEMA,
    ExactObjectSourceAdapter,
    PostgreSQLExactObjectReceiptRepository,
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
    pytest.skip("isolated PostgreSQL DSN not configured", allow_module_level=True)
PARTS = conninfo_to_dict(BASE)
assert PARTS.get("host") in {"127.0.0.1", "localhost"}
assert PARTS.get("dbname", "").startswith("stage275b_")


def _request(*, task="task-a", object_id="4806397", request_id=None, when=None):
    return ExactObjectRequest(
        "8891", object_id,
        f"https://auto.8891.com.tw/usedauto-infos-{object_id}.html",
        task, request_id or uuid4().hex, when or datetime.now(UTC),
    )


def _response(object_id="4806397", suffix=b""):
    canonical = f"https://auto.8891.com.tw/usedauto-infos-{object_id}.html"
    raw = (f'<link rel="canonical" href="{canonical}">'
           f'<meta property="og:url" content="{canonical}">').encode() + suffix
    return HttpResponse(200, f"https://auto.8891.com.tw/usedauto-userInfos-{object_id}.html",
                        raw, "text/html", None)


@pytest.fixture
def pg():
    schema = f"stage275b_{uuid4().hex}"
    with psycopg.connect(BASE) as con:
        con.execute(f'CREATE SCHEMA "{schema}"')
    dsn = make_conninfo(BASE, options=f"-c search_path={schema}", connect_timeout=2)
    with psycopg.connect(dsn) as con:
        con.execute(POSTGRES_SCHEMA)
    repo = PostgreSQLExactObjectReceiptRepository.from_dsn(dsn)
    try:
        yield schema, dsn, repo
    finally:
        with psycopg.connect(BASE) as con:
            con.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_pg1_schema_fresh_create_drop_recreate(pg):
    schema, dsn, _repo = pg
    with psycopg.connect(dsn) as con:
        columns = {row[0]: (row[1], row[2]) for row in con.execute(
            "SELECT column_name, data_type, is_identity FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name='exact_object_source_receipt'", (schema,)
        )}
        indexes = [row[0] for row in con.execute(
            "SELECT indexdef FROM pg_indexes WHERE schemaname=%s", (schema,)
        )]
        assert columns["receipt"][0] == "jsonb" and columns["raw_capture"][0] == "bytea"
        assert columns["id"] == ("bigint", "YES")
        assert any("_pkey" in item and "(id)" in item for item in indexes)
        assert any("UNIQUE" in item and "request_id" in item for item in indexes)
        assert any("task_id, platform, requested_object_id, id DESC" in item for item in indexes)
        con.execute("DROP TABLE exact_object_source_receipt")
        con.execute(POSTGRES_SCHEMA)
        assert con.execute("SELECT count(*) FROM exact_object_source_receipt").fetchone()[0] == 0


def test_pg2_atomic_pg5_bytea_pg6_jsonb(pg):
    _schema, dsn, repo = pg
    req = _request()
    receipt = ExactObjectSourceAdapter(repo, transport=lambda _url: _response()).fetch_exact_object(req)
    with psycopg.connect(dsn) as con:
        stored, raw = con.execute(
            "SELECT receipt, raw_capture FROM exact_object_source_receipt WHERE request_id=%s",
            (req.request_id,),
        ).fetchone()
    assert isinstance(stored, dict) and stored["schema_version"] == 1
    assert stored["task_id"] == req.task_id and stored["request_id"] == req.request_id
    assert bytes(raw) == _response().body
    assert hashlib.sha256(bytes(raw)).hexdigest() == receipt.content_hash
    assert repo.readback_current(req).ok


def test_pg3_real_rollback(pg):
    _schema, dsn, _repo = pg
    try:
        with psycopg.connect(dsn) as con:
            con.execute("INSERT INTO exact_object_source_receipt "
                        "(request_id,task_id,platform,requested_object_id,receipt,raw_capture,attempted_at) "
                        "VALUES ('rollback','t','8891','4806397','{}'::jsonb,%s,now())", (b"raw",))
            con.execute("SELECT 1/0")
    except psycopg.errors.DivisionByZero:
        pass
    with psycopg.connect(dsn) as con:
        assert con.execute("SELECT count(*) FROM exact_object_source_receipt").fetchone()[0] == 0


def test_pg4_unique_request_constraint(pg):
    _schema, dsn, repo = pg
    req = _request()
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: _response())
    adapter.fetch_exact_object(req)
    with pytest.raises(psycopg.errors.UniqueViolation):
        adapter.fetch_exact_object(req)
    with psycopg.connect(dsn) as con:
        assert con.execute("SELECT count(*) FROM exact_object_source_receipt").fetchone()[0] == 1


def test_pg7_successive_pg8_failure_supersedes(pg):
    _schema, dsn, repo = pg
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: _response())
    a, b, c = _request(), _request(), _request()
    adapter.fetch_exact_object(a)
    adapter.fetch_exact_object(b)
    assert not repo.readback_current(a).ok and repo.readback_current(b).ok
    failed = ExactObjectSourceAdapter(repo, transport=lambda _url: (_ for _ in ()).throw(OSError()))
    assert failed.fetch_exact_object(c).fetch_status == "FETCH_FAILED"
    assert not repo.readback_current(b).ok and not repo.readback_current(c).ok
    with psycopg.connect(dsn) as con:
        rows = list(con.execute("SELECT receipt->>'request_id' FROM exact_object_source_receipt ORDER BY id"))
    assert [row[0] for row in rows] == [a.request_id, b.request_id, c.request_id]


def test_pg9_cross_task_pg10_cross_object(pg):
    _schema, _dsn, repo = pg
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: _response())
    a = _request()
    adapter.fetch_exact_object(a)
    assert not repo.readback_current(_request(task="task-b", request_id=a.request_id)).ok
    assert not repo.readback_current(_request(object_id="4806398", request_id=a.request_id)).ok
    assert repo.readback_current(a).ok


def test_pg11_raw_and_hash_tamper(pg):
    _schema, dsn, repo = pg
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: _response())
    a = _request()
    adapter.fetch_exact_object(a)
    with psycopg.connect(dsn) as con:
        con.execute("UPDATE exact_object_source_receipt SET raw_capture=%s WHERE request_id=%s",
                    (b"tampered", a.request_id))
    assert not repo.readback_current(a).ok
    b = _request()
    adapter.fetch_exact_object(b)
    with psycopg.connect(dsn) as con:
        con.execute("UPDATE exact_object_source_receipt "
                    "SET receipt=jsonb_set(receipt,'{content_hash}',%s::jsonb) WHERE request_id=%s",
                    (json.dumps("0" * 64), b.request_id))
    assert not repo.readback_current(b).ok


def test_pg12_timezone_aware_freshness(pg):
    _schema, _dsn, repo = pg
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: _response())
    now = datetime.now(UTC)
    valid = _request(when=now)
    adapter.fetch_exact_object(valid, clock=lambda: now)
    assert repo.readback_current(valid, now=now).ok
    future = _request(when=now + timedelta(minutes=1))
    adapter.fetch_exact_object(future, clock=lambda: now + timedelta(minutes=1))
    assert not repo.readback_current(future, now=now).ok
    stale = _request(when=now - timedelta(minutes=6))
    adapter.fetch_exact_object(stale, clock=lambda: now - timedelta(minutes=6))
    assert not repo.readback_current(stale, now=now).ok


def test_pg13_identity_order_not_timestamp(pg):
    _schema, dsn, repo = pg
    same_time = datetime.now(UTC)
    a, b = _request(when=same_time), _request(when=same_time)
    captures = []

    class Collect:
        def save(self, receipt, raw):
            captures.append((receipt, raw))

    adapter = ExactObjectSourceAdapter(Collect(), transport=lambda _url: _response())
    adapter.fetch_exact_object(a, clock=lambda: same_time)
    adapter.fetch_exact_object(b, clock=lambda: same_time)
    first = psycopg.connect(dsn)
    second = psycopg.connect(dsn)
    try:
        for con, (receipt, raw) in zip((first, second), captures, strict=True):
            con.execute("INSERT INTO exact_object_source_receipt "
                        "(request_id,task_id,platform,requested_object_id,receipt,raw_capture,attempted_at) "
                        "VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)",
                        (receipt.request_id, receipt.task_id, receipt.platform,
                         receipt.requested_object_id, json.dumps(receipt.__dict__), raw, same_time))
        second.commit()  # The higher identity commits first.
        first.commit()
    finally:
        first.close()
        second.close()
    with psycopg.connect(dsn) as con:
        rows = list(con.execute("SELECT request_id FROM exact_object_source_receipt ORDER BY id DESC"))
    assert rows[0][0] == b.request_id
    assert repo.readback_current(b).ok and not repo.readback_current(a).ok


def test_pg15_new_connection_persists(pg):
    _schema, dsn, repo = pg
    req = _request()
    ExactObjectSourceAdapter(repo, transport=lambda _url: _response()).fetch_exact_object(req)
    del repo
    reopened = PostgreSQLExactObjectReceiptRepository.from_dsn(dsn)
    assert reopened.readback_current(req).ok


def test_z_pg14_actual_server_outage(pg):
    _schema, _dsn, repo = pg
    req = _request()
    ExactObjectSourceAdapter(repo, transport=lambda _url: _response()).fetch_exact_object(req)
    ctl = os.getenv("STAGE275B_PG_CTL")
    data = os.getenv("STAGE275B_PG_DATA")
    log = os.getenv("STAGE275B_PG_LOG")
    if not (ctl and data and log):
        pytest.skip("disposable server control unavailable")
    subprocess.run([ctl, "-D", data, "-m", "immediate", "stop"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    try:
        assert not repo.readback_current(req).ok
        with pytest.raises(psycopg.OperationalError):
            ExactObjectSourceAdapter(repo, transport=lambda _url: _response()).fetch_exact_object(_request())
    finally:
        subprocess.run([ctl, "-D", data, "-l", log, "-o", "-h 127.0.0.1 -p 55439", "start"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
