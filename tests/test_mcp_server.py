import asyncio
import json
import shutil
from pathlib import Path

from mcp import Client
from mcp.types import TextContent
from starlette.testclient import TestClient

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application

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
    return tmp_path


def _mutate_registry(repo_root: Path, document: str, field: str, value: str) -> None:
    registry = repo_root / "authority" / "current" / "registry.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["documents"][document][field] = value
    registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _http_client(repo_root: Path) -> TestClient:
    application = create_application(repo_root=repo_root)
    server = create_mcp_server(application)
    return TestClient(
        server.streamable_http_app(
            stateless_http=True,
            json_response=True,
            host="testserver",
        )
    )


def test_mcp_in_memory_client_lists_tools_and_dispatches_through_runtime():
    application = create_application(repo_root=REPO_ROOT)
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


def test_ready_resolves_current_authority():
    with _http_client(REPO_ROOT) as client:
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
        "failure_code": "AUTHORITY_RESOLUTION_FAILED",
    }


def test_ready_fails_closed_on_revision_mismatch(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    _mutate_registry(repo_root, "GLOBAL", "expected_revision", "wrong-revision")

    with _http_client(repo_root) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["failure_code"] == "AUTHORITY_RESOLUTION_FAILED"


def test_dispatch_fails_closed_when_authority_is_broken(tmp_path):
    repo_root = _copy_authority_repo(tmp_path)
    _mutate_registry(repo_root, "GLOBAL", "content_sha256", "0" * 64)
    application = create_application(repo_root=repo_root)
    server = create_mcp_server(application)

    async def scenario():
        async with Client(server) as client:
            return await client.call_tool("dispatch_task", {"payload": SAFE_TASK})

    result = asyncio.run(scenario())

    assert result.is_error is True
    assert result.structured_content is None
