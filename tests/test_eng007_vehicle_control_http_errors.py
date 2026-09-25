from __future__ import annotations

import io
import json
import socket
import urllib.error
from unittest.mock import patch

import pytest

from global_hybrid_v2.adapters.google_vehicle_control import InventoryReadResult
from global_hybrid_v2.vehicle_knowledge import InventoryRow
from global_hybrid_v2.vehicle_reconciliation import (
    CloudflareVehicleControlClient,
    ConfiguredVehicleReconciliation,
)


class _Reader:
    normalizer = type("Normalizer", (), {"version": "normalizer-v1"})()

    def read(self):
        return InventoryReadResult(
            "PASS",
            [InventoryRow(7, "VW", "2021", "TIGUAN R", ("", "", "VW", "2021"))],
            [],
            1,
        )


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _http_error(status: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://control.example/internal/control/inventory-observation",
        status,
        "upstream rejected request",
        {},
        io.BytesIO(body),
    )


def _reconcile_with_urlopen(side_effect):
    client = CloudflareVehicleControlClient(
        base_url="https://control.example",
        write_secret="never-log-this-secret",
    )
    patch_kwargs = (
        {"side_effect": side_effect}
        if isinstance(side_effect, BaseException)
        else {"return_value": side_effect}
    )
    with patch(
        "global_hybrid_v2.vehicle_reconciliation.urllib.request.urlopen",
        **patch_kwargs,
    ):
        return ConfiguredVehicleReconciliation(
            inventory_reader=_Reader(),
            control_client=client,
        )()


def test_worker_503_json_blocker_is_preserved():
    result = _reconcile_with_urlopen(
        _http_error(503, b'{"state":"HOLD","blocker":"INVALID_VEHICLE_ROW"}')
    )
    assert result == {"status": "HOLD", "blocker": "INVALID_VEHICLE_ROW"}


def test_worker_403_is_not_collapsed_to_transport_unavailable():
    result = _reconcile_with_urlopen(
        _http_error(403, b'{"state":"HOLD","blocker":"CONTROL_AUTH_REQUIRED"}')
    )
    assert result == {"status": "HOLD", "blocker": "CONTROL_AUTH_REQUIRED"}


@pytest.mark.parametrize(
    "response",
    [
        _http_error(503, b"not-json"),
        _Response(b"not-json"),
    ],
)
def test_worker_malformed_response_is_controlled_hold(response):
    result = _reconcile_with_urlopen(response)
    assert result == {"status": "HOLD", "blocker": "VEHICLE_CONTROL_RESPONSE_INVALID"}


@pytest.mark.parametrize(
    "transport_error",
    [
        TimeoutError("timed out"),
        socket.gaierror("dns failure"),
        urllib.error.URLError("tls failure"),
    ],
)
def test_real_transport_failures_remain_unavailable(transport_error):
    result = _reconcile_with_urlopen(transport_error)
    assert result == {"status": "HOLD", "blocker": "VEHICLE_CONTROL_UNAVAILABLE"}


def test_worker_200_valid_recorded_receipt_passes():
    response = _Response(
        json.dumps(
            {
                "state": "RECORDED",
                "observation_id": "google-inventory-test",
                "row_count": 1,
            }
        ).encode()
    )
    result = _reconcile_with_urlopen(response)
    assert result["status"] == "PASS"
    assert result["control_receipt"]["state"] == "RECORDED"
