from __future__ import annotations

import hashlib
import hmac
import subprocess
import tomllib
from pathlib import Path

from starlette.testclient import TestClient

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.settings import Settings
from tests._authority_signing import TEST_KEY_ID, TEST_PUBLIC_KEY
from tests.test_mcp_server import _copy_authority_repo

ROOT = Path(__file__).resolve().parents[1]


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
    assert config["workers_dev"] is False
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
    body = b'{"operation":"vehicle-knowledge-reconcile"}'
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

        assert client.post("/internal/vehicle-knowledge/reconcile", content=body).status_code == 403
        override = b'{"operation":"vehicle-knowledge-reconcile","target":"caller"}'
        override_signature = hmac.new(b"secret", override, hashlib.sha256).hexdigest()
        rejected = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=override,
            headers={"x-vehicle-control-signature": override_signature},
        )
        assert rejected.status_code == 403
        assert rejected.json()["blocker"] == "CONTROL_TARGET_OVERRIDE_REJECTED"
        assert called == [True]


def test_render_reconciliation_route_fails_closed_when_not_configured(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/internal/vehicle-knowledge/reconcile",
            content=b'{"operation":"vehicle-knowledge-reconcile"}',
        )
    assert response.status_code == 503
    assert response.json()["blocker"] == "RECONCILIATION_NOT_CONFIGURED"
