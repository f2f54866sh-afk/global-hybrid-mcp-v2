"""Stage 2.75A contract tests at the PostgreSQL connection boundary."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.governance.exact_object_source import ExactObjectRequest, HttpResponse
from global_hybrid_v2.governance.postgres_exact_object_source import (
    ExactObjectSourceAdapter,
    PostgreSQLExactObjectReceiptRepository,
)

NOW = datetime.now(UTC)


class FakeConnection:
    def __init__(self, db):
        self.db = db
        self.pending = []
        self.result = None

    def __enter__(self):
        if self.db.unavailable:
            raise OSError("database unavailable")
        return self

    def __exit__(self, kind, _value, _tb):
        if kind is None and not self.db.rollback:
            self.db.rows.extend(self.pending)
        self.pending.clear()
        if self.db.rollback and kind is None:
            raise OSError("commit failed")

    def execute(self, sql, params=()):
        if self.db.unavailable:
            raise OSError("database unavailable")
        if sql.startswith("INSERT INTO exact_object_source_receipt"):
            if any(row[0] == params[0] for row in self.db.rows + self.pending):
                raise ValueError("duplicate request")
            self.pending.append(tuple(params))
        elif "WHERE request_id =" in sql:
            self.result = next((row[4:6] for row in self.db.rows if row[:4] == params), None)
        else:
            rows = [row for row in self.db.rows if row[1:4] == params]
            self.result = rows[-1][4:6] if rows else None
        return self

    def fetchone(self):
        return self.result


class FakeDB:
    def __init__(self):
        self.rows = []
        self.unavailable = False
        self.rollback = False

    def connect(self):
        return FakeConnection(self)


def request(task="task-a", object_id="4806397", request_id="req-1", when=None):
    return ExactObjectRequest("8891", object_id,
        f"https://auto.8891.com.tw/usedauto-infos-{object_id}.html",
        task, request_id, when or NOW)


def response(object_id="4806397"):
    canonical = f"https://auto.8891.com.tw/usedauto-infos-{object_id}.html"
    body = (f'<link rel="canonical" href="{canonical}">'
            f'<meta property="og:url" content="{canonical}">').encode()
    return HttpResponse(200, f"https://auto.8891.com.tw/usedauto-userInfos-{object_id}.html",
                        body, "text/html", None)


def setup():
    db = FakeDB()
    repo = PostgreSQLExactObjectReceiptRepository(db.connect)
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: response())
    return db, repo, adapter


def test_atomic_write_and_readback():
    db, repo, adapter = setup()
    receipt = adapter.fetch_exact_object(request())
    assert len(db.rows) == 1 and db.rows[0][5] == response().body
    assert repo.readback_current(request(), now=datetime.now(UTC)).ok
    assert receipt.fetch_status == "PASS"


def test_hash_tamper_fails():
    db, repo, adapter = setup()
    adapter.fetch_exact_object(request())
    row = db.rows[0]
    db.rows[0] = (*row[:5], b"tampered", row[6])
    assert not repo.readback_current(request()).ok


def test_raw_missing_fails():
    db, repo, adapter = setup()
    adapter.fetch_exact_object(request())
    row = db.rows[0]
    db.rows[0] = (*row[:5], None, row[6])
    assert not repo.readback_current(request()).ok


def test_duplicate_request_id_rejected():
    _db, _repo, adapter = setup()
    adapter.fetch_exact_object(request())
    with pytest.raises(ValueError):
        adapter.fetch_exact_object(request())


def test_successive_captures_keep_history_and_latest():
    db, repo, adapter = setup()
    first = request(request_id="one")
    second = request(request_id="two")
    adapter.fetch_exact_object(first)
    adapter.fetch_exact_object(second)
    assert len(db.rows) == 2
    assert not repo.readback_current(first).ok
    assert repo.readback_current(second).ok


def test_failed_new_request_does_not_repromote_old_success():
    _db, repo, adapter = setup()
    first = request(request_id="one")
    adapter.fetch_exact_object(first)
    failing = ExactObjectSourceAdapter(repo, transport=lambda _url: (_ for _ in ()).throw(OSError()))
    second = request(request_id="two")
    assert failing.fetch_exact_object(second).fetch_status == "FETCH_FAILED"
    assert not repo.readback_current(first).ok
    assert not repo.readback_current(second).ok


def test_cross_task_isolation():
    _db, repo, adapter = setup()
    adapter.fetch_exact_object(request())
    assert not repo.readback_current(request(task="task-b")).ok


def test_cross_object_isolation():
    _db, repo, adapter = setup()
    adapter.fetch_exact_object(request())
    assert not repo.readback_current(request(object_id="4806398")).ok


def test_transaction_rollback():
    db, repo, adapter = setup()
    db.rollback = True
    with pytest.raises(OSError):
        adapter.fetch_exact_object(request())
    assert db.rows == [] and not repo.readback_current(request()).ok


def test_db_outage_fails_closed():
    db, repo, adapter = setup()
    adapter.fetch_exact_object(request())
    db.unavailable = True
    assert not repo.readback_current(request()).ok
    with pytest.raises(OSError):
        adapter.fetch_exact_object(request(request_id="two"))


def test_freshness_and_stored_pass_are_not_trusted():
    db, repo, adapter = setup()
    old = datetime.now(UTC) - timedelta(minutes=6)
    adapter.fetch_exact_object(request(when=old), clock=lambda: old)
    assert not repo.readback_current(request(when=old)).ok
    import json
    row = db.rows[0]
    payload = json.loads(row[4])
    payload["identity_match"] = True
    db.rows[0] = (*row[:4], json.dumps(payload), *row[5:])
    assert not repo.readback_current(request(when=old)).ok


def test_stored_pass_cannot_override_wrong_object():
    import json
    db = FakeDB()
    repo = PostgreSQLExactObjectReceiptRepository(db.connect)
    adapter = ExactObjectSourceAdapter(repo, transport=lambda _url: response("4806398"))
    adapter.fetch_exact_object(request())
    row = db.rows[0]
    payload = json.loads(row[4])
    payload["fetch_status"] = "PASS"
    payload["identity_match"] = True
    db.rows[0] = (*row[:4], json.dumps(payload), *row[5:])
    assert not repo.readback_current(request()).ok
