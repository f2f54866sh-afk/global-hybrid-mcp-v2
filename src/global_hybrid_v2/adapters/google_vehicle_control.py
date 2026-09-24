from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from global_hybrid_v2.vehicle_knowledge import InventoryNormalizer, InventoryRow

COMPANY_INVENTORY_SPREADSHEET_ID = "12NL4A7CQ_MsUrRWyDgVDsrzFgKJJBdg94HQo75soikI"
CONTROL_SPREADSHEET_ID = "1UeL0K3PwJ1iSXRfld2R9aObJiqY0V99j_L_VGPKXivk"
COMPANY_INVENTORY_RANGE = "車源!A1:N"


class GoogleSheetsTransport(Protocol):
    def read_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]: ...


class GoogleQuotaExceeded(RuntimeError): ...


class GoogleSheetsRestTransport:
    """REST transport fed by a deployment-owned access-token producer."""

    def __init__(self, access_token_provider: Callable[[], str], *, timeout: float = 15):
        self._access_token_provider = access_token_provider
        self.timeout = timeout

    def _request(self, url: str, *, method: str = "GET", payload=None) -> dict:
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "authorization": f"Bearer {self._access_token_provider()}",
                "accept": "application/json",
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise GoogleQuotaExceeded("Google Sheets free quota exhausted") from exc
            raise

    def read_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/" + urllib.parse.quote(
            range_name, safe=""
        )
        return self._request(url).get("values", [])

    def write_values(self, spreadsheet_id: str, range_name: str, values: list[list[str]]) -> dict:
        url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/"
            + urllib.parse.quote(range_name, safe="")
            + "?valueInputOption=RAW"
        )
        return self._request(
            url,
            method="PUT",
            payload={"range": range_name, "majorDimension": "ROWS", "values": values},
        )


@dataclass(frozen=True)
class InventoryReadResult:
    state: str
    rows: list[InventoryRow]
    held_row_numbers: list[int]
    attempts: int
    blocker: str | None = None


class GoogleInventoryReader:
    def __init__(self, transport: GoogleSheetsTransport, *, max_attempts: int = 3):
        self.transport = transport
        self.max_attempts = max_attempts
        self.normalizer = InventoryNormalizer()

    def read(self) -> InventoryReadResult:
        for attempt in range(1, self.max_attempts + 1):
            try:
                values = self.transport.read_values(COMPANY_INVENTORY_SPREADSHEET_ID, COMPANY_INVENTORY_RANGE)
                rows, held = self.normalizer.normalize(values)
                return InventoryReadResult("PASS", rows, held, attempt)
            except GoogleQuotaExceeded:
                if attempt == self.max_attempts:
                    return InventoryReadResult("HOLD", [], [], attempt, "FREE_TIER_QUOTA_EXHAUSTED")
        raise AssertionError("unreachable")


class GoogleControlSheetAdapter:
    allowed_tabs = frozenset({"RESEARCH_QUEUE", "EVIDENCE_INBOX", "EVIDENCE_ARCHIVE", "CONTROL_READBACK"})

    def __init__(self, transport: GoogleSheetsTransport):
        self.transport = transport

    def read(self, tab: str, range_suffix: str) -> list[list[str]]:
        if tab not in self.allowed_tabs:
            raise ValueError("CONTROL_SHEET_TAB_REJECTED")
        return self.transport.read_values(CONTROL_SPREADSHEET_ID, f"{tab}!{range_suffix}")

    def write_evidence(self, tab: str, range_suffix: str, values: list[list[str]]) -> dict:
        if tab not in self.allowed_tabs:
            raise ValueError("CONTROL_SHEET_TAB_REJECTED")
        if tab == "CONTROL_READBACK":
            raise ValueError("CONTROL_READBACK_IS_RECEIPT_ONLY")
        writer = getattr(self.transport, "write_values", None)
        if writer is None:
            raise RuntimeError("CONTROL_SHEET_WRITE_TRANSPORT_UNAVAILABLE")
        return writer(CONTROL_SPREADSHEET_ID, f"{tab}!{range_suffix}", values)

    @staticmethod
    def reject_authority_claim(payload: dict) -> None:
        forbidden = {"verified", "query_ready", "promoted", "authority_state"}
        if forbidden.intersection(payload):
            raise ValueError("CONTROL_SHEET_AUTHORITY_CLAIM_REJECTED")
        if payload.get("spreadsheet_id", CONTROL_SPREADSHEET_ID) != CONTROL_SPREADSHEET_ID:
            raise ValueError("CONTROL_SHEET_TARGET_OVERRIDE_REJECTED")
