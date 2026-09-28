"""ChatGPT Work MCP App entry; no production composition is installed here."""
from __future__ import annotations

import ipaddress
import socket
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict

MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 10
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


class ControlledCommandPort(Protocol):
    def execute(self, *, request_text: str, evidence_bytes: bytes,
                mime_type: str) -> EntryResult: ...


class ControlledSalesEntry:
    """One-file App boundary; command identity and persistence stay server-owned."""

    def __init__(self, *, command_handler: ControlledCommandPort | None,
                 downloader: Callable[[OpenAIFile], bytes] = download_openai_file) -> None:
        self._command_handler = command_handler
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
        if file.mime_type not in {None, "application/pdf", "image/jpeg", "image/png", "image/webp"}:
            return _blocked("EVIDENCE_MIME_UNSUPPORTED", debt=True)
        if self._command_handler is None:
            return _blocked("CONTROLLED_ENTRY_BINDING_UNAVAILABLE", debt=True)
        try:
            raw = self._downloader(file)
            if not raw or len(raw) > MAX_EVIDENCE_BYTES:
                return _blocked("EVIDENCE_SIZE_INVALID")
            if not raw.startswith(b"%PDF-"):
                return (_blocked("PHOTO_EVIDENCE_RESOLVER_UNAVAILABLE", debt=True)
                        if file.mime_type != "application/pdf" else _blocked("EVIDENCE_MIME_MISMATCH"))
            if file.mime_type not in {None, "application/pdf"}:
                return _blocked("EVIDENCE_MIME_MISMATCH")
            if b"%%EOF" not in raw[-1024:]:
                return _blocked("DOCUMENT_PREIMAGE_INVALID")
            result = self._command_handler.execute(
                request_text=request_text, evidence_bytes=raw, mime_type="application/pdf",
            )
        except Exception:
            return _blocked("CONTROLLED_EXECUTION_FAILED")
        if not isinstance(result, EntryResult):
            return _blocked("CONTROLLED_TERMINAL_INVALID")
        return result
