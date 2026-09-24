from __future__ import annotations

import hashlib
import hmac
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from starlette.testclient import TestClient

from global_hybrid_v2.adapters.google_vehicle_control import InventoryReadResult
from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.settings import Settings
from global_hybrid_v2.vehicle_knowledge import InventoryRow
from global_hybrid_v2.vehicle_reconciliation import ConfiguredVehicleReconciliation
from tests._authority_signing import TEST_KEY_ID, TEST_PUBLIC_KEY
from tests.test_mcp_server import _copy_authority_repo

ROOT = Path(__file__).resolve().parents[1]


def _scheduled_body(timestamp_ms=1790208000000):
    return json.dumps(
        {
            "operation": "vehicle-knowledge-reconcile",
            "run_id": f"cf-{timestamp_ms}",
            "scheduled_at": "2026-09-24T00:00:00.000Z",
        },
        separators=(",", ":"),
    ).encode()


def test_concrete_reconciliation_reads_normalizes_and_records_fixed_observation():
    class Reader:
        normalizer = type("Normalizer", (), {"version": "normalizer-v1"})()

        def read(self):
            return InventoryReadResult(
                "PASS",
                [InventoryRow(7, "VW", "2021", "TIGUAN R", ("", "", "VW", "2021"))],
                [],
                1,
            )

    class Control:
        def __init__(self):
            self.payloads = []

        def record_inventory_observation(self, payload):
            self.payloads.append(payload)
            return {"state": "RECORDED", "observation_id": payload["observation_id"]}

    control = Control()
    reconciliation = ConfiguredVehicleReconciliation(
        inventory_reader=Reader(),
        control_client=control,
    )
    result = reconciliation()
    assert result["status"] == "PASS"
    assert reconciliation.invocation_count == 1
    assert len(control.payloads) == 1
    assert control.payloads[0]["rows"][0]["payload"]["model"] == "TIGUAN R"


def test_worker_executes_fixed_d1_control_and_read_paths():
    result = subprocess.run(
        ["node", str(ROOT / "tests/fixtures/eng007_worker_execution.mjs")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ENG007_WORKER_EXECUTION_BINDING_PASS" in result.stdout


def test_wrangler_candidate_binds_exact_entrypoint_and_d1():
    config = tomllib.loads((ROOT / "infra/vehicle_knowledge/wrangler.toml").read_text())
    assert config["main"] == "worker.js"
    assert config["workers_dev"] is True
    assert config["triggers"] == {"crons": ["0 * * * *"]}
    assert config["d1_databases"] == [
        {
            "binding": "DB",
            "database_name": "vehicle-knowledge",
            "database_id": "REQUIRED_AT_DEPLOYMENT",
        }
    ]


def _client(tmp_path, *, secret=None, reconcile=None):
    application = create_application(
        repo_root=_copy_authority_repo(tmp_path),
        settings=Settings(
            authority_trusted_key_id=TEST_KEY_ID,
            authority_trusted_public_key=TEST_PUBLIC_KEY,
            vehicle_reconciliation_shared_secret=secret,
        ),
    )
    server = create_mcp_server(application, vehicle_reconciliation=reconcile)
    return TestClient(server.streamable_http_app(stateless_http=True, json_response=True))


def test_render_reconciliation_route_is_callable_and_hmac_bound(tmp_path):
    called = []
    body = _scheduled_body()
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    reconcile = lambda: called.append(True) or {"status": "PASS"}  # noqa: E731
    with _client(tmp_path, secret="secret", reconcile=reconcile) as client:
        response = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=body,
            headers={"x-vehicle-control-signature": signature},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "PASS"}
        assert called == [True]

        replay = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=body,
            headers={"x-vehicle-control-signature": signature},
        )
        assert replay.status_code == 200
        assert called == [True]

        reordered = (
            b'{"scheduled_at":"2026-09-24T00:00:00.000Z",'
            b'"run_id":"cf-1790208000000","operation":"vehicle-knowledge-reconcile"}'
        )
        reordered_signature = hmac.new(b"secret", reordered, hashlib.sha256).hexdigest()
        collision = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=reordered,
            headers={"x-vehicle-control-signature": reordered_signature},
        )
        assert collision.status_code == 403
        assert collision.json()["blocker"] == "SCHEDULER_RUN_COLLISION"
        assert called == [True]

        assert client.post("/internal/vehicle-knowledge/reconcile", content=body).status_code == 403
        override = body[:-1] + b',"target":"caller"}'
        override_signature = hmac.new(b"secret", override, hashlib.sha256).hexdigest()
        rejected = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=override,
            headers={"x-vehicle-control-signature": override_signature},
        )
        assert rejected.status_code == 403
        assert rejected.json()["blocker"] == "CONTROL_TARGET_OVERRIDE_REJECTED"
        assert called == [True]

        new_body = _scheduled_body(1790208001000).replace(
            b"2026-09-24T00:00:00.000Z", b"2026-09-24T00:00:01.000Z"
        )
        new_signature = hmac.new(b"secret", new_body, hashlib.sha256).hexdigest()
        assert client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=new_body,
            headers={"x-vehicle-control-signature": new_signature},
        ).status_code == 200
        assert called == [True, True]

        legacy = b'{"operation":"vehicle-knowledge-reconcile"}'
        legacy_signature = hmac.new(b"secret", legacy, hashlib.sha256).hexdigest()
        legacy_response = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=legacy,
            headers={"x-vehicle-control-signature": legacy_signature},
        )
        assert legacy_response.status_code == 403
        assert legacy_response.json()["blocker"] == "CONTROL_TARGET_OVERRIDE_REJECTED"


def test_render_reconciliation_route_fails_closed_when_not_configured(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=_scheduled_body(),
        )
    assert response.status_code == 503
    assert response.json()["blocker"] == "RECONCILIATION_NOT_CONFIGURED"


def test_production_module_entrypoint_binds_real_reconciliation_callable():
    script = r'''
import hashlib
import hmac
from starlette.testclient import TestClient
import global_hybrid_v2.adapters.mcp_server as production

body = (
    b'{"operation":"vehicle-knowledge-reconcile","run_id":"cf-1790208000000",'
    b'"scheduled_at":"2026-09-24T00:00:00.000Z"}'
)
signature = hmac.new(b"entrypoint-secret", body, hashlib.sha256).hexdigest()
with TestClient(production.mcp.streamable_http_app(stateless_http=True, json_response=True)) as client:
    response = client.post(
        "/internal/vehicle-knowledge/reconcile",
        content=body,
        headers={"x-vehicle-control-signature": signature},
    )
assert response.status_code == 200, response.text
assert response.json()["blocker"] == "RECONCILIATION_DEPENDENCY_NOT_CONFIGURED"
assert production.vehicle_reconciliation.invocation_count == 1
'''
    env = {
        **__import__("os").environ,
        "PYTHONPATH": str(ROOT / "src"),
        "GLOBAL_VEHICLE_RECONCILIATION_SHARED_SECRET": "entrypoint-secret",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
