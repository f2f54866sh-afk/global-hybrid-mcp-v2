from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from global_hybrid_v2.vehicle_knowledge import InventoryNormalizer, InventoryRow

COMPANY_INVENTORY_SPREADSHEET_ID = "12NL4A7CQ_MsUrRWyDgVDsrzFgKJJBdg94HQo75soikI"
CONTROL_SPREADSHEET_ID = "1UeL0K3PwJ1iSXRfld2R9aObJiqY0V99j_L_VGPKXivk"
COMPANY_INVENTORY_RANGE = "車源!A1:N"


class GoogleSheetsTransport(Protocol):
    def read_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]: ...


class GoogleQuotaExceeded(RuntimeError): ...


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

    @staticmethod
    def reject_authority_claim(payload: dict) -> None:
        forbidden = {"verified", "query_ready", "promoted", "authority_state"}
        if forbidden.intersection(payload):
            raise ValueError("CONTROL_SHEET_AUTHORITY_CLAIM_REJECTED")
        if payload.get("spreadsheet_id", CONTROL_SPREADSHEET_ID) != CONTROL_SPREADSHEET_ID:
            raise ValueError("CONTROL_SHEET_TARGET_OVERRIDE_REJECTED")
