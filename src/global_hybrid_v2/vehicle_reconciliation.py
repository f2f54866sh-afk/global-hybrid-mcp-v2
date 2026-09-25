from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from global_hybrid_v2.adapters.google_vehicle_control import (
    GoogleInventoryReader,
    GoogleSheetsRestTransport,
)
from global_hybrid_v2.google_auth import (
    GoogleAuthUnavailable,
    ServiceAccountAccessTokenProvider,
    ServiceAccountIdentity,
)
from global_hybrid_v2.settings import Settings
from global_hybrid_v2.vehicle_knowledge import canonical_json


class VehicleControlResponseError(RuntimeError):
    def __init__(self, blocker: str):
        super().__init__(blocker)
        self.blocker = blocker


class CloudflareVehicleControlClient:
    def __init__(self, *, base_url: str, write_secret: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.write_secret = write_secret
        self.timeout = timeout

    def record_inventory_observation(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/internal/control/inventory-observation",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "authorization": f"Bearer {self.write_secret}",
                "content-type": "application/json",
                "accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                receipt = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                blocker = payload.get("blocker") if isinstance(payload, dict) else None
            except (UnicodeDecodeError, json.JSONDecodeError):
                blocker = None
            raise VehicleControlResponseError(
                blocker if isinstance(blocker, str) and blocker.strip()
                else "VEHICLE_CONTROL_RESPONSE_INVALID"
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VehicleControlResponseError("VEHICLE_CONTROL_RESPONSE_INVALID") from exc
        if not isinstance(receipt, dict):
            raise VehicleControlResponseError("VEHICLE_CONTROL_RESPONSE_INVALID")
        return receipt


class ConfiguredVehicleReconciliation:
    def __init__(
        self,
        *,
        inventory_reader: GoogleInventoryReader | None,
        control_client: CloudflareVehicleControlClient | None,
    ):
        self.inventory_reader = inventory_reader
        self.control_client = control_client
        self.invocation_count = 0

    def __call__(self) -> dict[str, Any]:
        self.invocation_count += 1
        if self.inventory_reader is None or self.control_client is None:
            return {"status": "HOLD", "blocker": "RECONCILIATION_DEPENDENCY_NOT_CONFIGURED"}
        try:
            inventory = self.inventory_reader.read()
        except GoogleAuthUnavailable:
            return {"status": "HOLD", "blocker": "GOOGLE_AUTH_UNAVAILABLE"}
        if inventory.state != "PASS":
            return {"status": "HOLD", "blocker": inventory.blocker or "INVENTORY_READ_FAILED"}
        if not inventory.rows:
            return {"status": "HOLD", "blocker": "INVENTORY_EMPTY"}
        row_payloads = [
            {
                "row_number": row.row_number,
                "payload": {
                    "row_number": row.row_number,
                    "make": row.make,
                    "model_year": row.model_year,
                    "model": row.model,
                    "raw_source_row": list(row.raw_source_row),
                },
            }
            for row in inventory.rows
        ]
        source = {
            "normalizer_version": self.inventory_reader.normalizer.version,
            "rows": row_payloads,
            "held_row_numbers": inventory.held_row_numbers,
        }
        source_revision = hashlib.sha256(canonical_json(source).encode()).hexdigest()
        observation_id = f"google-inventory-{source_revision[:24]}"
        try:
            receipt = self.control_client.record_inventory_observation(
                {
                    "observation_id": observation_id,
                    "source_revision": source_revision,
                    "observed_at": datetime.now(UTC).isoformat(),
                    "payload": {
                        "normalizer_version": self.inventory_reader.normalizer.version,
                        "held_row_numbers": inventory.held_row_numbers,
                    },
                    "rows": row_payloads,
                }
            )
        except VehicleControlResponseError as exc:
            return {"status": "HOLD", "blocker": exc.blocker}
        except (OSError, TimeoutError, urllib.error.URLError):
            return {"status": "HOLD", "blocker": "VEHICLE_CONTROL_UNAVAILABLE"}
        return {
            "status": "PASS",
            "observation_id": observation_id,
            "source_revision": source_revision,
            "control_receipt": receipt,
        }


def configured_vehicle_reconciliation(settings: Settings) -> ConfiguredVehicleReconciliation:
    google_credential = settings.google_service_account_json
    control_url = settings.vehicle_control_http_base_url
    control_secret = settings.vehicle_control_http_write_secret
    if google_credential is None or not control_url or control_secret is None:
        return ConfiguredVehicleReconciliation(inventory_reader=None, control_client=None)
    token_provider = ServiceAccountAccessTokenProvider(
        ServiceAccountIdentity.from_json(google_credential.get_secret_value())
    )
    return ConfiguredVehicleReconciliation(
        inventory_reader=GoogleInventoryReader(
            GoogleSheetsRestTransport(token_provider)
        ),
        control_client=CloudflareVehicleControlClient(
            base_url=control_url,
            write_secret=control_secret.get_secret_value(),
        ),
    )
