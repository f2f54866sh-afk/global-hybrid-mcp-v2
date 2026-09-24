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
from global_hybrid_v2.settings import Settings
from global_hybrid_v2.vehicle_knowledge import canonical_json


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
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)


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
        inventory = self.inventory_reader.read()
        if inventory.state != "PASS":
            return {"status": "HOLD", "blocker": inventory.blocker or "INVENTORY_READ_FAILED"}
        row_payloads = [
            {
                "id": f"inventory-row-{row.row_number}",
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
        except (OSError, TimeoutError, urllib.error.URLError):
            return {"status": "HOLD", "blocker": "VEHICLE_CONTROL_UNAVAILABLE"}
        return {
            "status": "PASS",
            "observation_id": observation_id,
            "source_revision": source_revision,
            "control_receipt": receipt,
        }


def configured_vehicle_reconciliation(settings: Settings) -> ConfiguredVehicleReconciliation:
    google_token = settings.google_sheets_access_token
    control_url = settings.vehicle_control_http_base_url
    control_secret = settings.vehicle_control_http_write_secret
    if google_token is None or not control_url or control_secret is None:
        return ConfiguredVehicleReconciliation(inventory_reader=None, control_client=None)
    return ConfiguredVehicleReconciliation(
        inventory_reader=GoogleInventoryReader(
            GoogleSheetsRestTransport(lambda: google_token.get_secret_value())
        ),
        control_client=CloudflareVehicleControlClient(
            base_url=control_url,
            write_secret=control_secret.get_secret_value(),
        ),
    )
