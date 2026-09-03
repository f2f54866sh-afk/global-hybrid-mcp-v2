from datetime import UTC, datetime

import pytest

from global_hybrid_v2.runtime.state import (
    CURRENT_RUNTIME_STATE_VERSION,
    RuntimeStateNotFound,
    RuntimeStateVersionError,
    RuntimeTaskState,
    SQLiteRuntimeStateStore,
)


def _state(*, thread="thread-a", task="task-a", **updates):
    values = {
        "runtime_state_version": CURRENT_RUNTIME_STATE_VERSION,
        "conversation_or_thread_id": thread,
        "task_id": task,
        "primary_user_outcome": "complete deployment",
        "current_progress": "validated build",
        "active_main_task_id": task,
        "active_subtask_id": "test",
        "current_phase": "VALIDATION",
        "active_blocker": None,
        "current_authority_revisions": {"GLOBAL": "GLOBAL_CURRENT_1"},
        "current_requirement_ids": ["REQ-1"],
        "selected_route": "EXECUTION",
        "next_action_candidate": "publish",
        "last_action_id": "action-1",
        "last_action_result": "PASS",
        "closure_state": "OPEN",
        "resume_cursor": "cursor-1",
        "updated_at": datetime.now(UTC),
    }
    values.update(updates)
    return RuntimeTaskState(**values)


def test_create_close_reopen_exact_reload(tmp_path):
    path = tmp_path / "runtime.db"
    original = _state()
    SQLiteRuntimeStateStore(path).create(original)

    reopened = SQLiteRuntimeStateStore(path)
    assert reopened.load("thread-a", "task-a") == original


def test_update_reload_latest_state(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    updated = _state(current_progress="handoff ready", closure_state="CLOSED")
    store.update(updated)
    assert store.load("thread-a", "task-a").current_progress == "handoff ready"
    assert store.load("thread-a", "task-a").closure_state == "CLOSED"


def test_thread_and_task_key_isolation(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(thread="thread-a", task="task-a"))
    store.create(_state(thread="thread-b", task="task-b"))
    assert store.load("thread-a", "task-a").conversation_or_thread_id == "thread-a"
    assert store.load("thread-b", "task-b").task_id == "task-b"
    with pytest.raises(RuntimeStateNotFound):
        store.load("thread-a", "task-b")


def test_unsupported_runtime_state_version_fails_explicitly(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    unsupported = _state().model_construct(runtime_state_version=99)
    with pytest.raises(RuntimeStateVersionError, match="unsupported runtime_state_version"):
        store.create(unsupported)


def test_stale_persisted_version_fails_on_reload(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    with store._connect() as connection:
        connection.execute(
            "UPDATE runtime_task_state SET runtime_state_version = 0 WHERE conversation_or_thread_id = ?",
            ("thread-a",),
        )
    with pytest.raises(RuntimeStateVersionError, match="unsupported runtime_state_version"):
        store.load("thread-a", "task-a")


def test_stateless_task_request_path_is_unchanged():
    from global_hybrid_v2.contracts import EffectType, Intent, TaskRequest

    request = TaskRequest(request_text="status", intent=Intent.GOVERNANCE, effects=[EffectType.READ_ONLY])
    assert request.engineering_checkpoint is None
