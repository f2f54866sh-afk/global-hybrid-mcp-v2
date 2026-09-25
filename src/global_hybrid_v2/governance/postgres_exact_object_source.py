"""Isolated Stage 2.75A PostgreSQL exact-object capture candidate.

The database row contains the receipt and raw bytes atomically. A stored PASS
label is never sufficient for current admission. No production wiring exists.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Protocol

from global_hybrid_v2.governance.exact_object_source import (
    _CURRENT_WINDOW,
    _MAX_BYTES,
    ExactObjectReadback,
    ExactObjectRequest,
    ExactObjectSourceReceiptV1,
    HttpResponse,
    _canonical_url,
    _default_transport,
    _detail_url,
    _observed_object_id,
)

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS exact_object_source_receipt (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    requested_object_id TEXT NOT NULL,
    receipt JSONB NOT NULL,
    raw_capture BYTEA,
    attempted_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS exact_object_source_latest_idx
    ON exact_object_source_receipt (task_id, platform, requested_object_id, id DESC);
"""

_INSERT = """INSERT INTO exact_object_source_receipt
    (request_id, task_id, platform, requested_object_id, receipt, raw_capture, attempted_at)
    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)"""
_BY_REQUEST = """SELECT receipt, raw_capture FROM exact_object_source_receipt
    WHERE request_id = %s AND task_id = %s AND platform = %s AND requested_object_id = %s"""
_LATEST = """SELECT receipt, raw_capture FROM exact_object_source_receipt
    WHERE task_id = %s AND platform = %s AND requested_object_id = %s
    ORDER BY id DESC LIMIT 1"""


class _Cursor(Protocol):
    def execute(self, sql: str, params: tuple = ()) -> _Cursor: ...
    def fetchone(self) -> tuple | None: ...


class _Connection(_Cursor, Protocol):
    def __enter__(self) -> _Connection: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> object: ...


class ExactObjectReceiptRepository(Protocol):
    def save(self, receipt: ExactObjectSourceReceiptV1, raw_capture: bytes | None) -> None: ...
    def readback_current(
        self, request: ExactObjectRequest, *, now: datetime | None = None,
    ) -> ExactObjectReadback: ...


class PostgreSQLExactObjectReceiptRepository:
    def __init__(self, connect: Callable[[], _Connection]) -> None:
        self._connect = connect

    @classmethod
    def from_dsn(cls, dsn: str) -> PostgreSQLExactObjectReceiptRepository:
        """Construct the candidate against a provisioned PostgreSQL DSN."""
        import psycopg

        if not dsn:
            raise ValueError("POSTGRES_DSN_REQUIRED")
        return cls(lambda: psycopg.connect(dsn, connect_timeout=5))

    def save(self, receipt: ExactObjectSourceReceiptV1, raw_capture: bytes | None) -> None:
        # One INSERT and one commit boundary: no receipt can outlive failed raw persistence.
        with self._connect() as connection:
            connection.execute(_INSERT, (
                receipt.request_id, receipt.task_id, receipt.platform,
                receipt.requested_object_id, json.dumps(asdict(receipt)),
                raw_capture, datetime.fromisoformat(receipt.request_time),
            ))

    def readback_current(
        self, request: ExactObjectRequest, *, now: datetime | None = None,
    ) -> ExactObjectReadback:
        try:
            with self._connect() as connection:
                exact = connection.execute(_BY_REQUEST, (
                    request.request_id, request.task_id, request.platform, request.object_id,
                )).fetchone()
                latest = connection.execute(_LATEST, (
                    request.task_id, request.platform, request.object_id,
                )).fetchone()
        except Exception:
            return ExactObjectReadback(False, "DB_UNAVAILABLE")
        if exact is None or latest is None:
            return ExactObjectReadback(False, "RECEIPT_NOT_FOUND")
        try:
            receipt = exact[0] if isinstance(exact[0], dict) else json.loads(exact[0])
            newest = latest[0] if isinstance(latest[0], dict) else json.loads(latest[0])
            raw = bytes(exact[1]) if exact[1] is not None else None
            if newest["request_id"] != request.request_id:
                return ExactObjectReadback(False, "SUPERSEDED")
            if (receipt["schema_version"] != 1 or receipt["request_id"] != request.request_id
                or receipt["task_id"] != request.task_id or receipt["platform"] != request.platform
                or receipt["requested_object_id"] != request.object_id
                or receipt["request_time"] != request.request_time.isoformat()
                or receipt["requested_url"] != _detail_url(request.object_id)
                or receipt["requested_canonical_url"] != request.canonical_object_ref
                or request.canonical_object_ref != _canonical_url(request.object_id)
                or receipt["final_url"] != _detail_url(request.object_id)
                or raw is None or not raw or len(raw) > _MAX_BYTES):
                return ExactObjectReadback(False, "SCOPE_OR_CAPTURE_INVALID")
            if hashlib.sha256(raw).hexdigest() != receipt["content_hash"]:
                return ExactObjectReadback(False, "CAPTURE_HASH_MISMATCH")
            observed = _observed_object_id(raw, request.canonical_object_ref)
            if observed != request.object_id or receipt["observed_object_id"] != observed:
                return ExactObjectReadback(False, "OBJECT_IDENTITY_MISMATCH")
            if receipt["fetch_status"] != "PASS" or receipt["identity_match"] is not True:
                return ExactObjectReadback(False, "FETCH_NOT_PASS")
            current = now or datetime.now(UTC)
            capture = datetime.fromisoformat(receipt["capture_time"])
            requested = datetime.fromisoformat(receipt["request_time"])
            if (current.tzinfo is None or capture.tzinfo is None or requested.tzinfo is None
                or not timedelta(0) <= current - capture <= _CURRENT_WINDOW
                or abs(capture - requested) > _CURRENT_WINDOW):
                return ExactObjectReadback(False, "CAPTURE_EXPIRED")
        except (KeyError, ValueError, TypeError, AttributeError):
            return ExactObjectReadback(False, "RECEIPT_INVALID")
        return ExactObjectReadback(True, None)


class ExactObjectSourceAdapter:
    def __init__(
        self, repository: ExactObjectReceiptRepository,
        *, transport: Callable[[str], HttpResponse] | None = None,
    ) -> None:
        self.repository = repository
        self.transport = transport or _default_transport

    def fetch_exact_object(
        self, request: ExactObjectRequest, *, clock: Callable[[], datetime] | None = None,
    ) -> ExactObjectSourceReceiptV1:
        if (request.platform != "8891" or not re.fullmatch(r"[1-9]\d{0,15}", request.object_id)
            or request.canonical_object_ref != _canonical_url(request.object_id)
            or not request.task_id.strip() or not request.request_id.strip()
            or request.request_time.tzinfo is None):
            raise ValueError("EXACT_OBJECT_REQUEST_INVALID")
        now = (clock or (lambda: datetime.now(UTC)))()
        if now.tzinfo is None:
            raise ValueError("CAPTURE_CLOCK_NOT_AWARE")
        url = _detail_url(request.object_id)
        response = None
        status, error, observed = "FETCH_FAILED", None, None
        try:
            response = self.transport(url)
            if response.status != 200:
                status, error = "SOURCE_UNAVAILABLE", f"HTTP_{response.status}"
            elif (response.final_url != url or "text/html" not in response.content_type.lower()
                  or not response.body or len(response.body) > _MAX_BYTES):
                status, error = "OBJECT_MISMATCH", "NOT_EXACT_DETAIL_HTML"
            else:
                observed = _observed_object_id(response.body, request.canonical_object_ref)
                status = "PASS" if observed == request.object_id else "OBJECT_MISMATCH"
                if status != "PASS":
                    error = "EXACT_OBJECT_ID_NOT_IN_PAGE_METADATA"
        except (OSError, TimeoutError) as exc:
            error = type(exc).__name__
        raw = response.body if response and response.body and len(response.body) <= _MAX_BYTES else None
        receipt = ExactObjectSourceReceiptV1(
            schema_version=1, task_id=request.task_id, request_id=request.request_id,
            request_time=request.request_time.isoformat(), platform=request.platform,
            fetch_status=status, requested_object_id=request.object_id, observed_object_id=observed,
            requested_url=url, requested_canonical_url=request.canonical_object_ref,
            final_url=response.final_url if response else None,
            capture_time=now.isoformat() if response else None,
            content_hash=hashlib.sha256(raw).hexdigest() if raw else None,
            source_version_or_etag=response.etag if response else None,
            raw_capture_ref=f"postgres:exact_object_source_receipt:{request.request_id}" if raw else None,
            receipt_ref=f"postgres:exact_object_source_receipt:{request.request_id}",
            identity_match=status == "PASS" and observed == request.object_id,
            freshness_state=("CURRENT_CAPTURE" if status == "PASS" and
                abs(now - request.request_time) <= _CURRENT_WINDOW else
                "STALE_CAPTURE" if status == "PASS" else status),
            error_state=error,
            source_role="EXACT_PLATFORM_OBJECT_CAPTURE_NOT_COMPANY_OR_VEHICLE_IDENTITY",
        )
        self.repository.save(receipt, raw)
        return receipt
