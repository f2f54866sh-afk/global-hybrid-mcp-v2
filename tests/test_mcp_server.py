import asyncio
import base64
import hashlib
import json
import logging
import shutil
from pathlib import Path

from mcp import Client
from mcp.types import TextContent
from starlette.testclient import TestClient

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.contracts import Owner
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.runtime.deployment import read_runtime_identity
from global_hybrid_v2.settings import Settings
from tests._authority_signing import TEST_KEY_ID, TEST_PUBLIC_KEY, activate_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICALS = (
    "GLOBAL_WINDOW_CANONICAL.md",
    "SALES_CANONICAL.md",
    "SALES_HUMAN_CANONICAL.md",
    "VEHICLE_KNOWLEDGE_BASE.md",
    "REAL_CAR_統一正式指令.md",
)
SAFE_TASK = {
    "request_text": "post-activation governance smoke test",
    "intent": "governance",
    "effects": ["read_only"],
}


def _copy_authority_repo(tmp_path: Path) -> Path:
    registry_target = tmp_path / "authority" / "current" / "registry.json"
    registry_target.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "authority" / "current" / "registry.json", registry_target)
    for filename in CANONICALS:
        shutil.copy2(REPO_ROOT / filename, tmp_path / filename)
    activate_registry(registry_target)
    return tmp_path


def _mutate_registry(repo_root: Path, document: str, field: str, value: str) -> None:
    registry = repo_root / "authority" / "current" / "registry.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["documents"][document][field] = value
    registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _test_settings() -> Settings:
    return Settings(
        authority_trusted_key_id=TEST_KEY_ID,
        authority_trusted_public_key=TEST_PUBLIC_KEY,
    )


def _http_client(repo_root: Path, *, render_identity: bool = False) -> TestClient:
    runtime_identity = None
    if render_identity:
        runtime_identity = read_runtime_identity(
            {
                "RENDER": "true",
                "RENDER_GIT_COMMIT": "candidate-sha",
                "RENDER_GIT_BRANCH": "main",
                "RENDER_GIT_REPO_SLUG": "f2f54866sh-afk/global-hybrid-mcp-v2",
            }
        )
    application = create_application(
        repo_root=repo_root,
        settings=_test_settings(),
        runtime_identity=runtime_identity,
    )
    server = create_mcp_server(application)
    return TestClient(
        server.streamable_http_app(
            stateless_http=True,
            json_response=True,
            host="testserver",
        )
    )


def test_mcp_in_memory_client_lists_tools_and_dispatches_through_runtime(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    application = create_application(repo_root=repo_root, settings=_test_settings())
    server = create_mcp_server(application)

    async def scenario():
        async with Client(server) as client:
            tools = await client.list_tools()
            result = await client.call_tool("dispatch_task", {"payload": SAFE_TASK})
            return tools, result

    tools, result = asyncio.run(scenario())

    names = {tool.name for tool in tools.tools}
    assert {"validate_task", "dispatch_task"} <= names
    assert result.is_error is False
    assert isinstance(result.content[0], TextContent)
    payload = json.loads(result.content[0].text)
    assert payload["status"] == "BLOCKED_NOT_CONFIGURED"
    assert payload["owner"] == "GLOBAL"


def test_all_owner_domains_remain_explicitly_not_configured(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    application = create_application(repo_root=repo_root, settings=_test_settings())

    assert set(application.dispatcher.domains) == set(Owner)
    assert all(
        isinstance(domain, NotConfiguredDomain)
        for domain in application.dispatcher.domains.values()
    )


def test_ready_resolves_current_authority(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    with _http_client(repo_root) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "resolved_owners": [
            "GLOBAL",
            "SALES_HUMAN",
            "LIBRARY_FACT",
            "VISUAL",
            "EXECUTION",
        ],
        "runtime": {
            "provider": "LOCAL_OR_UNKNOWN",
            "git_commit": None,
            "git_branch": None,
            "repo_slug": None,
        },
    }


def test_ready_fails_closed_on_hash_mismatch_but_health_stays_live(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    _mutate_registry(repo_root, "GLOBAL", "content_sha256", "0" * 64)

    with _http_client(repo_root) as client:
        health_response = client.get("/health")
        ready_response = client.get("/ready")

    assert health_response.status_code == 200
    assert health_response.json()["ok"] is True
    assert ready_response.status_code == 503
    assert ready_response.json() == {
        "ready": False,
        "failure_code": "AUTHORITY_ACTIVATION_INVALID",
    }


def test_ready_fails_closed_on_revision_mismatch(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    _mutate_registry(repo_root, "GLOBAL", "expected_revision", "wrong-revision")

    with _http_client(repo_root) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["failure_code"] == "AUTHORITY_ACTIVATION_INVALID"


def test_ready_logs_chained_authority_failure_without_changing_response(tmp_path, caplog):
    repo_root = _copy_authority_repo(tmp_path)
    activation_path = repo_root / "authority" / "current" / "activation.json"
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    activation["key_id"] = "unexpected-key"
    activation_path.write_text(json.dumps(activation), encoding="utf-8")

    with caplog.at_level(
        logging.ERROR,
        logger="global_hybrid_v2.adapters.mcp_server",
    ):
        with _http_client(repo_root) as client:
            response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "failure_code": "AUTHORITY_ACTIVATION_INVALID",
    }
    assert "Authority readiness check failed" in caplog.text
    assert "activation key id mismatch" in caplog.text


def test_ready_logs_safe_authority_fingerprints_for_invalid_signature(tmp_path, caplog):
    repo_root = _copy_authority_repo(tmp_path)
    registry_path = repo_root / "authority" / "current" / "registry.json"
    activation_path = registry_path.parent / "activation.json"
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    raw_public_key = base64.b64decode(TEST_PUBLIC_KEY, validate=True)
    raw_signature = base64.b64decode(activation["signature"], validate=True)

    _mutate_registry(repo_root, "GLOBAL", "content_sha256", "0" * 64)
    expected_registry_fingerprint = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    expected_public_key_fingerprint = hashlib.sha256(raw_public_key).hexdigest()
    expected_signature_fingerprint = hashlib.sha256(raw_signature).hexdigest()

    with caplog.at_level(
        logging.ERROR,
        logger="global_hybrid_v2.adapters.mcp_server",
    ):
        with _http_client(repo_root) as client:
            response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "failure_code": "AUTHORITY_ACTIVATION_INVALID",
    }
    assert f"registry_raw_sha256={expected_registry_fingerprint}" in caplog.text
    assert f"trusted_public_key_raw_sha256={expected_public_key_fingerprint}" in caplog.text
    assert f"activation_signature_raw_sha256={expected_signature_fingerprint}" in caplog.text
    assert f"trusted_key_id='{TEST_KEY_ID}'" in caplog.text
    assert f"activation_key_id='{TEST_KEY_ID}'" in caplog.text
    assert f"registry_path={str(registry_path)!r}" in caplog.text
    assert TEST_PUBLIC_KEY not in caplog.text
    assert activation["signature"] not in caplog.text
    assert raw_public_key.hex() not in caplog.text
    assert raw_signature.hex() not in caplog.text


def test_dispatch_fails_closed_when_authority_is_broken(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    _mutate_registry(repo_root, "GLOBAL", "content_sha256", "0" * 64)
    application = create_application(repo_root=repo_root, settings=_test_settings())
    server = create_mcp_server(application)

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool("dispatch_task", {"payload": SAFE_TASK})

    result = asyncio.run(scenario())

    assert result.is_error is True
    assert result.structured_content is None


def test_ready_returns_render_deployment_attestation(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)

    with _http_client(repo_root, render_identity=True) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["runtime"] == {
        "provider": "RENDER",
        "git_commit": "candidate-sha",
        "git_branch": "main",
        "repo_slug": "f2f54866sh-afk/global-hybrid-mcp-v2",
    }


def test_ready_does_not_treat_incomplete_deployment_identity_as_authority_failure(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    application = create_application(
        repo_root=repo_root,
        settings=_test_settings(),
        runtime_identity=read_runtime_identity({"RENDER": "true"}),
    )
    server = create_mcp_server(application)

    with TestClient(
        server.streamable_http_app(
            stateless_http=True,
            json_response=True,
            host="testserver",
        )
    ) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["runtime"] == {
        "provider": "RENDER",
        "git_commit": None,
        "git_branch": None,
        "repo_slug": None,
    }
