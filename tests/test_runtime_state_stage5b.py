from pathlib import Path

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore
from tests._host_projection import host_projection_payload
from tests.test_mcp_server import _copy_authority_repo, _test_settings
from tests.test_runtime_state_stage2 import _state
from tests.test_runtime_state_stage5 import _application, _CountingDomain, _dispatch, _payload


def _init_payload(text="first durable turn"):
    return {**_payload(), "request_text": text, "runtime_state_initialize": True}


def test_first_explicit_initialization_real_mcp(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain = _CountingDomain()
    result = _dispatch(create_mcp_server(_application(repo, settings, domain)), _init_payload())
    state = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert result["status"] == "READY"
    assert domain.calls == 1
    assert state.primary_user_outcome == "first durable turn"
    assert state.active_main_task_id == "runtime-task-a"
    assert state.current_progress == "READY"
    assert state.current_phase == "COMPLETED"
    assert state.selected_route == "GLOBAL"
    assert state.current_authority_revisions
    assert result["evidence"]["runtime_checkpoint_id"] == state.runtime_checkpoint_id
    assert result["evidence"]["runtime_checkpoint_event_id"] == state.runtime_checkpoint_event_id
    rows = SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    assert any(row["event_type"] == "STARTED" for row in rows)
    assert any(row["event_type"] == "CHECKPOINT_COMMITTED" for row in rows)


def test_initialize_then_independent_reopen(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    first = _dispatch(create_mcp_server(_application(repo, settings, _CountingDomain())), _init_payload())
    before = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    second = _dispatch(create_mcp_server(_application(repo, settings, _CountingDomain())), _payload())
    after = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert first["status"] == "READY"
    assert second["status"] == "RUNTIME_STATE_WAIT"
    assert after.model_dump(mode="json") == before.model_dump(mode="json")
    assert len(SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")) > 0


def test_missing_without_explicit_initialization_remains_blocked(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain = _CountingDomain()
    result = _dispatch(create_mcp_server(_application(repo, settings, domain)), _payload())
    assert result["status"] == "RUNTIME_STATE_LOAD_BLOCKED"
    assert domain.calls == 0
    assert SQLiteRuntimeStateStore(repo / "runtime.db").journal(
        "thread-a", "runtime-task-a"
    ) == []


def test_existing_row_rejects_explicit_reinitialization(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    SQLiteRuntimeStateStore(db).create(_state())
    before = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain = _CountingDomain()
    result = _dispatch(create_mcp_server(_application(repo, settings, domain)), _init_payload())
    after = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert result["status"] == "RUNTIME_STATE_ALREADY_INITIALIZED"
    assert domain.calls == 0
    assert after.model_dump(mode="json") == before.model_dump(mode="json")


def test_stale_row_is_not_initialization_candidate(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    store = SQLiteRuntimeStateStore(db)
    store.create(_state())
    with store._connect() as connection:
        connection.execute(
            "UPDATE runtime_task_state SET runtime_state_version = 99 WHERE task_id = ?",
            ("runtime-task-a",),
        )
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    result = _dispatch(create_mcp_server(_application(repo, settings, _CountingDomain())), _init_payload())
    assert result["status"] == "RUNTIME_STATE_LOAD_BLOCKED"


def test_stateless_initialization_flag_does_not_create_runtime_state(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    payload = {
        "request_text": "ordinary",
        "intent": "execution",
        "effects": ["read_only"],
        **host_projection_payload(),
    }
    result = _dispatch(create_mcp_server(_application(repo, settings, _CountingDomain())), payload)
    assert result["status"] == "READY"
    assert SQLiteRuntimeStateStore(repo / "runtime.db").journal("thread-a", "runtime-task-a") == []
