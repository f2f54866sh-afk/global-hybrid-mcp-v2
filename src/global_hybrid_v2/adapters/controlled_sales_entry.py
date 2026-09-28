"""ChatGPT Work MCP App entry; no production composition is installed here."""
from __future__ import annotations

import hashlib
import ipaddress
import socket
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from global_hybrid_v2.adapters.controlled_responses import ServerTurnContext
from global_hybrid_v2.adapters.controlled_sales_executor import (
    FAILURE,
    ControlledSalesCompletionExecutor,
)
from global_hybrid_v2.media_admission import (
    ProducingActivity,
    TrustedMediaActivityIssuer,
    canonical_image_mime,
)

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 10
SOURCE_LINEAGE = "chatgpt-work-file-input"
CAPABILITY_DEBT = "PERSISTENCE_CAPABILITY_DEBT"
EXECUTION_FAIL = "EXECUTION_FAIL"


class OpenAIFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    download_url: str
    file_id: str
    mime_type: str | None = None
    file_name: str | None = None


class EntryToolResult(BaseModel):
    execution_state: str
    terminal_disposition: str | None
    result_text: str


def _public_https_url(url: str) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "files.oaiusercontent.com"
            or parsed.username or parsed.password
            or parsed.port not in (None, 443) or not parsed.path):
        raise ValueError("EVIDENCE_DOWNLOAD_URL_INVALID")
    for address in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("EVIDENCE_DOWNLOAD_URL_INVALID")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def download_openai_file(file: OpenAIFile) -> bytes:
    """Read one temporary HTTPS URL once; never retain the URL or bytes."""
    url = _public_https_url(file.download_url)
    request = urllib.request.Request(url, headers={"User-Agent": "global-hybrid-evidence/1"})
    with urllib.request.build_opener(_NoRedirect()).open(
        request, timeout=DOWNLOAD_TIMEOUT_SECONDS,
    ) as response:
        if response.status != 200:
            raise ValueError("EVIDENCE_DOWNLOAD_FAILED")
        raw = response.read(MAX_EVIDENCE_BYTES + 1)
    if not raw or len(raw) > MAX_EVIDENCE_BYTES:
        raise ValueError("EVIDENCE_SIZE_INVALID")
    return raw


@dataclass(frozen=True)
class EntryResult:
    execution_state: str
    terminal_disposition: str | None
    result_text: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "execution_state": self.execution_state,
            "terminal_disposition": self.terminal_disposition,
            "result_text": self.result_text,
        }


def _blocked(reason: str, *, debt: bool = False) -> EntryResult:
    return EntryResult(
        CAPABILITY_DEBT if debt else EXECUTION_FAIL,
        CAPABILITY_DEBT if debt else None,
        reason,
    )


class ControlledSalesEntry:
    """Owns entry identity and one-file admission before invoking N2."""

    def __init__(self, *, executor: ControlledSalesCompletionExecutor | None,
                 media_issuer: TrustedMediaActivityIssuer | None,
                 downloader: Callable[[OpenAIFile], bytes] = download_openai_file) -> None:
        self._executor = executor
        self._media_issuer = media_issuer
        self._downloader = downloader

    def execute(self, *, request_text: str, evidence_file: list[OpenAIFile] | None) -> EntryResult:
        if not isinstance(request_text, str) or not request_text.strip():
            return _blocked("TASK_TEXT_REQUIRED")
        if not evidence_file:
            return _blocked("EVIDENCE_FILE_REQUIRED")
        if len(evidence_file) != 1:
            return _blocked("MULTI_EVIDENCE_BINDING_CAPABILITY_DEBT", debt=True)
        file = evidence_file[0]
        if not file.file_id or not file.download_url:
            return _blocked("EVIDENCE_FILE_INVALID")
        if file.mime_type not in {None, "image/jpeg", "image/png", "image/webp", "application/pdf"}:
            return _blocked("EVIDENCE_MIME_UNSUPPORTED", debt=True)
        if self._executor is None:
            return _blocked("CONTROLLED_ENTRY_BINDING_UNAVAILABLE", debt=True)
        try:
            raw = self._downloader(file)
            if not raw or len(raw) > MAX_EVIDENCE_BYTES:
                return _blocked("EVIDENCE_SIZE_INVALID")
            is_pdf = raw.startswith(b"%PDF-")
            if file.mime_type == "application/pdf" and not is_pdf:
                return _blocked("EVIDENCE_MIME_MISMATCH")
            if not is_pdf:
                actual_mime = canonical_image_mime(raw)
                if file.mime_type is not None and actual_mime != file.mime_type:
                    return _blocked("EVIDENCE_MIME_MISMATCH")
                if self._media_issuer is None or self._executor.ingress.media_gate is None:
                    return _blocked("MEDIA_ADMISSION_UNAVAILABLE", debt=True)
            elif file.mime_type not in {None, "application/pdf"}:
                return _blocked("EVIDENCE_MIME_MISMATCH")
            turn = ServerTurnContext(uuid4().hex, uuid4().hex)
            if is_pdf:
                result = self._executor.execute(
                    turn=turn, request_text=request_text, intent="sales_human", raw_evidence=raw,
                    media_inputs=({"type": "input_file"},), document_mime="application/pdf",
                )
            else:
                scope = f"conversation:{turn.conversation_id}:turn:{turn.turn_id}"
                activity = ProducingActivity.FIRST_OBSERVED_EXTERNAL
                attestation = self._media_issuer.issue(
                    raw_sha256=hashlib.sha256(raw).hexdigest(), activity=activity,
                    source_lineage=SOURCE_LINEAGE, task_lineage=scope,
                )
                result = self._executor.execute(
                    turn=turn, request_text=request_text, intent="sales_human", raw_evidence=raw,
                    media_inputs=({"type": "input_image"},), media_activity=activity,
                    media_attestation=attestation, media_source_lineage=SOURCE_LINEAGE,
                )
        except Exception:
            return _blocked("CONTROLLED_EXECUTION_FAILED")
        if result.state == FAILURE or result.receipt is None or result.user_visible_text is None:
            return _blocked("CONTROLLED_EXECUTION_FAILED")
        if result.state not in {
            "WRITE_AND_READBACK_PASS", "NO_DELTA", CAPABILITY_DEBT, "HOLD_CONFLICT",
        }:
            return _blocked("CONTROLLED_TERMINAL_INVALID")
        return EntryResult("TERMINAL", result.state, result.user_visible_text)
