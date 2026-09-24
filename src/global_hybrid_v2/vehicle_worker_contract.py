from __future__ import annotations

from collections.abc import Callable
from typing import Any

CONTROL_PATHS = {
    "/internal/control/inventory-observation",
    "/internal/control/coverage-work",
    "/internal/control/verified-revision",
    "/internal/control/snapshot-promote",
}
READ_PATHS = {"/v1/vehicle-config/query", "/v1/vehicle-config/readback"}
FORBIDDEN_CALLER_FIELDS = {
    "sql",
    "raw_sql",
    "table",
    "table_name",
    "spreadsheet_id",
    "verified",
    "promoted",
    "promotion_state",
    "authority_state",
    "query_ready",
}


class WorkerProviderUnavailable(RuntimeError): ...


class WorkerQuotaExceeded(RuntimeError): ...


class VehicleKnowledgeWorkerContract:
    def __init__(
        self,
        *,
        control_secret: str,
        read_secret: str,
        control_handler: Callable[[str, dict[str, Any]], dict[str, Any]],
        read_handler: Callable[[str, dict[str, Any]], dict[str, Any]],
    ):
        if not control_secret or not read_secret or control_secret == read_secret:
            raise ValueError("separate control and runtime read credentials required")
        self.control_secret = control_secret
        self.read_secret = read_secret
        self.control_handler = control_handler
        self.read_handler = read_handler

    def handle(self, path: str, *, token: str | None, payload: dict[str, Any]) -> tuple[int, dict]:
        if path in CONTROL_PATHS:
            if token != self.control_secret:
                return 403, {"error": "CONTROL_AUTH_REQUIRED"}
            if FORBIDDEN_CALLER_FIELDS.intersection(payload):
                return 400, {"error": "DIRECT_AUTHORITY_INJECTION"}
            try:
                return 200, self.control_handler(path, payload)
            except WorkerQuotaExceeded:
                return 503, {"state": "HOLD", "blocker": "FREE_TIER_QUOTA_EXHAUSTED"}
            except WorkerProviderUnavailable:
                return 503, {"state": "HOLD", "blocker": "PROVIDER_UNAVAILABLE"}
        if path in READ_PATHS:
            if token != self.read_secret:
                return 403, {"error": "RUNTIME_READ_AUTH_REQUIRED"}
            try:
                return 200, self.read_handler(path, payload)
            except (WorkerQuotaExceeded, WorkerProviderUnavailable):
                return 503, {"state": "PROVIDER_UNAVAILABLE"}
        return 404, {"error": "NOT_FOUND"}
