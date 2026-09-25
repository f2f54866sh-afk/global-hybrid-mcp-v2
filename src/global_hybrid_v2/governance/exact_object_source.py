"""Stage 2.5: fresh exact 8891 detail-page read with durable local receipt.

This candidate has no Company Inventory or mutable-offer semantics. The default
transport fetches a fixed HTTPS detail URL; test transports are not production
evidence. Receipts prove a capture, never vehicle or company-row identity.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

_BASE = "https://auto.8891.com.tw"
_MAX_BYTES = 2_000_000
_CURRENT_WINDOW = timedelta(minutes=5)


@dataclass(frozen=True)
class ExactObjectRequest:
    platform: str
    object_id: str
    canonical_object_ref: str
    task_id: str
    request_id: str
    request_time: datetime


@dataclass(frozen=True)
class HttpResponse:
    status: int
    final_url: str
    body: bytes
    content_type: str
    etag: str | None


@dataclass(frozen=True)
class ExactObjectSourceReceiptV1:
    schema_version: int
    task_id: str
    request_id: str
    request_time: str
    platform: str
    fetch_status: str
    requested_object_id: str
    observed_object_id: str | None
    requested_url: str
    requested_canonical_url: str
    final_url: str | None
    capture_time: str | None
    content_hash: str | None
    source_version_or_etag: str | None
    raw_capture_ref: str | None
    receipt_ref: str
    identity_match: bool
    freshness_state: str
    error_state: str | None
    source_role: str


@dataclass(frozen=True)
class ExactObjectReadback:
    ok: bool
    reason: str | None


class _ObjectMeta(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.canonicals: list[str] = []
        self.og_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        href = values.get("href")
        content = values.get("content")
        if tag == "link" and values.get("rel") == "canonical" and href is not None:
            self.canonicals.append(href)
        if tag == "meta" and values.get("property") == "og:url" and content is not None:
            self.og_urls.append(content)


def _detail_url(object_id: str) -> str:
    return f"{_BASE}/usedauto-userInfos-{object_id}.html"


def _canonical_url(object_id: str) -> str:
    return f"{_BASE}/usedauto-infos-{object_id}.html"


def _default_transport(url: str) -> HttpResponse:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=8) as response:
        body = response.read(_MAX_BYTES + 1)
        return HttpResponse(
            status=response.status, final_url=response.geturl(), body=body,
            content_type=response.headers.get("Content-Type", ""),
            etag=response.headers.get("ETag"),
        )


def _observed_object_id(body: bytes, expected_url: str) -> str | None:
    parser = _ObjectMeta()
    parser.feed(body.decode("latin1"))
    if parser.canonicals != [expected_url] or parser.og_urls != [expected_url]:
        return None
    match = re.fullmatch(rf"{re.escape(_BASE)}/usedauto-infos-(\d+)\.html", expected_url)
    return match.group(1) if match else None


def _write_receipt(path: Path, receipt: ExactObjectSourceReceiptV1) -> None:
    value = json.dumps(asdict(receipt), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.write_text(value, encoding="utf-8")


def _latest_ref(receipt: ExactObjectSourceReceiptV1) -> Path:
    task_key = hashlib.sha256(receipt.task_id.encode("utf-8")).hexdigest()[:20]
    return Path(receipt.receipt_ref).parent / f"latest-{task_key}-{receipt.requested_object_id}.json"


def fetch_exact_object(
    request: ExactObjectRequest,
    *,
    capture_dir: str | Path,
    transport: Callable[[str], HttpResponse] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> ExactObjectSourceReceiptV1:
    """Fetch once; never promote a previous capture after this attempt fails."""
    if (
        request.platform != "8891" or not re.fullmatch(r"[1-9]\d{0,15}", request.object_id)
        or request.canonical_object_ref != _canonical_url(request.object_id)
        or not request.task_id.strip() or not request.request_id.strip()
        or request.request_time.tzinfo is None
    ):
        raise ValueError("EXACT_OBJECT_REQUEST_INVALID")
    directory = Path(capture_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    now = (clock or (lambda: datetime.now(UTC)))()
    if now.tzinfo is None:
        raise ValueError("CAPTURE_CLOCK_NOT_AWARE")
    url = _detail_url(request.object_id)
    uid = uuid4().hex
    receipt_path = directory / f"{uid}.receipt.json"
    status = "FETCH_FAILED"
    error = None
    observed = None
    response = None
    try:
        response = (transport or _default_transport)(url)
        if response.status != 200:
            status, error = "SOURCE_UNAVAILABLE", f"HTTP_{response.status}"
        elif (
            response.final_url != url or "text/html" not in response.content_type.lower()
            or not response.body or len(response.body) > _MAX_BYTES
        ):
            status, error = "OBJECT_MISMATCH", "NOT_EXACT_DETAIL_HTML"
        else:
            observed = _observed_object_id(response.body, request.canonical_object_ref)
            status = "PASS" if observed == request.object_id else "OBJECT_MISMATCH"
            if status != "PASS":
                error = "EXACT_OBJECT_ID_NOT_IN_PAGE_METADATA"
    except HTTPError as exc:
        status, error = "SOURCE_UNAVAILABLE", f"HTTP_{exc.code}"
    except (URLError, OSError, TimeoutError) as exc:
        status, error = "FETCH_FAILED", type(exc).__name__
    capture_path = None
    content_hash = None
    if response is not None and response.body and len(response.body) <= _MAX_BYTES:
        capture_path = directory / f"{uid}.capture.html"
        capture_path.write_bytes(response.body)
        content_hash = hashlib.sha256(response.body).hexdigest()
    freshness = (
        "CURRENT_CAPTURE" if status == "PASS" and abs(now - request.request_time) <= _CURRENT_WINDOW
        else "STALE_CAPTURE" if status == "PASS" else status
    )
    receipt = ExactObjectSourceReceiptV1(
        schema_version=1,
        task_id=request.task_id,
        request_id=request.request_id,
        request_time=request.request_time.isoformat(),
        platform=request.platform,
        fetch_status=status,
        requested_object_id=request.object_id,
        observed_object_id=observed,
        requested_url=url,
        requested_canonical_url=request.canonical_object_ref,
        final_url=response.final_url if response is not None else None,
        capture_time=now.isoformat() if response is not None else None,
        content_hash=content_hash,
        source_version_or_etag=response.etag if response is not None else None,
        raw_capture_ref=str(capture_path) if capture_path is not None else None,
        receipt_ref=str(receipt_path),
        identity_match=status == "PASS" and observed == request.object_id,
        freshness_state=freshness,
        error_state=error,
        source_role="EXACT_PLATFORM_OBJECT_CAPTURE_NOT_COMPANY_OR_VEHICLE_IDENTITY",
    )
    _write_receipt(receipt_path, receipt)
    _latest_ref(receipt).write_text(receipt.receipt_ref, encoding="utf-8")
    return receipt


def readback_exact_object(receipt: ExactObjectSourceReceiptV1) -> ExactObjectReadback:
    """Verify persisted receipt and raw bytes against the caller's exact receipt."""
    try:
        stored = json.loads(Path(receipt.receipt_ref).read_text(encoding="utf-8"))
        if stored != asdict(receipt):
            return ExactObjectReadback(False, "RECEIPT_MISMATCH")
        if receipt.raw_capture_ref is not None:
            raw = Path(receipt.raw_capture_ref).read_bytes()
            if hashlib.sha256(raw).hexdigest() != receipt.content_hash:
                return ExactObjectReadback(False, "CAPTURE_HASH_MISMATCH")
        elif receipt.content_hash is not None:
            return ExactObjectReadback(False, "MISSING_CAPTURE")
    except (OSError, ValueError, TypeError):
        return ExactObjectReadback(False, "READBACK_UNAVAILABLE")
    return ExactObjectReadback(True, None)


def readback_current_exact_object(
    receipt: ExactObjectSourceReceiptV1,
    *,
    now: datetime | None = None,
) -> ExactObjectReadback:
    readback = readback_exact_object(receipt)
    if not readback.ok:
        return readback
    if receipt.fetch_status != "PASS" or not receipt.identity_match:
        return ExactObjectReadback(False, "CURRENT_RECEIPT_NOT_PASS")
    if receipt.freshness_state != "CURRENT_CAPTURE" or receipt.capture_time is None:
        return ExactObjectReadback(False, "CURRENT_RECEIPT_STALE")
    current_time = now or datetime.now(UTC)
    captured = datetime.fromisoformat(receipt.capture_time)
    if current_time.tzinfo is None or not timedelta(0) <= current_time - captured <= _CURRENT_WINDOW:
        return ExactObjectReadback(False, "CURRENT_RECEIPT_EXPIRED")
    try:
        latest = _latest_ref(receipt).read_text(encoding="utf-8")
    except OSError:
        return ExactObjectReadback(False, "CURRENT_RECEIPT_LATEST_UNAVAILABLE")
    if latest != receipt.receipt_ref:
        return ExactObjectReadback(False, "CURRENT_RECEIPT_SUPERSEDED")
    return ExactObjectReadback(True, None)
