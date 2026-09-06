import asyncio
import json
from pathlib import Path

from mcp import Client
from mcp.types import TextContent

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore
from tests._host_projection import TestHostCurrentStateVerifier, host_projection_payload
from tests.test_mcp_server import _copy_authority_repo, _test_settings
from tests.test_runtime_state_stage2 import _state


def _payload():
    return {
        "request_text": "continue durable runtime task",
        "intent": "governance",
        "effects": ["read_only"],
        "runtime_state_required": True,
        "conversation_or_thread_id": "thread-a",
        "runtime_task_id": "runtime-task-a",
        **host_projection_payload(),
    }


def _dispatch(server, payload):
    async def scenario():
        async with Client(server) as client:
            result = await client.call_tool("dispatch_task", {"payload": payload})
            assert result.is_error is False
            assert isinstance(result.content[0], TextContent)
            return json.loads(result.content[0].text)

    return asyncio.run(scenario())


def test_real_application_mcp_reopens_existing_runtime_state(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    db = repo_root / "runtime.db"
    SQLiteRuntimeStateStore(db).create(_state())
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    app1 = create_application(
        repo_root=repo_root,
        settings=settings,
        host_current_state_verifier=TestHostCurrentStateVerifier(),
    )
    first = _dispatch(create_mcp_server(app1), _payload())
    state1 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert first["evidence"]["runtime_state"] == "COMMITTED"
    assert state1.runtime_checkpoint_id == first["evidence"]["runtime_checkpoint_id"]
    app2 = create_application(
        repo_root=repo_root,
        settings=settings,
        host_current_state_verifier=TestHostCurrentStateVerifier(),
    )
    second = _dispatch(create_mcp_server(app2), _payload())
    state2 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert state2.conversation_or_thread_id == "thread-a"
    assert state2.task_id == "runtime-task-a"
    assert second["status"] in {"RUNTIME_STATE_WAIT", "BLOCKED_NOT_CONFIGURED", "DONE"}


def test_runtime_path_is_optional_and_explicit_store_wins(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    settings = _test_settings()
    app = create_application(repo_root=repo_root, settings=settings)
    assert app.dispatcher.runtime_state_store is None
    explicit = SQLiteRuntimeStateStore(tmp_path / "explicit.db")
    injected = create_application(repo_root=repo_root, settings=settings, runtime_state_store=explicit)
    assert injected.dispatcher.runtime_state_store is explicit
    configured = create_application(
        repo_root=repo_root,
        settings=settings.model_copy(update={"runtime_state_path": "configured.db"}),
    )
    assert configured.dispatcher.runtime_state_store is not None
    assert (repo_root / "configured.db").exists()
