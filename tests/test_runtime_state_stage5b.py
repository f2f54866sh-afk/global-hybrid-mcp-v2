import asyncio
import json
from pathlib import Path

import pytest
from mcp import Client
from mcp.types import TextContent

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.contracts import Owner
from global_hybrid_v2.governance.host_projection import HostCurrentStateVerification
from global_hybrid_v2.runtime.state import (
    RuntimeStateAlreadyExists,
    RuntimeStateNotFound,
    SQLiteRuntimeStateStore,
)
from tests._host_projection import host_projection_payload
from tests.test_mcp_server import _copy_authority_repo, _test_settings
from tests.test_pre_action_constraints import _context
from tests.test_runtime_state_stage2 import _state
from tests.test_runtime_state_stage5 import _application, _CountingDomain, _dispatch, _payload


def _init_payload(text="first durable turn"):
    return {**_payload(), "request_text": text, "runtime_state_initialize": True}


def _dispatch_allow_error(server, payload):
    async def scenario():
        async with Client(server) as client:
            result = await client.call_tool("dispatch_task", {"payload": payload})
            if result.is_error:
                return None
            assert isinstance(result.content[0], TextContent)
            return json.loads(result.content[0].text)

    return asyncio.run(scenario())


class _FailingHostVerifier:
    def verify(self, projection):
        return HostCurrentStateVerification(False, "HOST_STATE_PROJECTION_STALE")


def _journal_without_execution(db):
    rows = SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    assert not any(row["event_type"] == "STARTED" for row in rows)
    assert not any(row["event_type"] == "CHECKPOINT_COMMITTED" for row in rows)
    return rows


class _CaptureStore:
    def __init__(self, store, *, crash_started=False, race=False):
        self.store = store
        self.created = []
        self.crash_started = crash_started
        self.race = race

    def load(self, thread, task):
        if self.race and not self.created:
            raise RuntimeStateNotFound()
        return self.store.load(thread, task)

    def create(self, state):
        self.created.append(state)
        if self.race:
            self.store.create(state)
            raise RuntimeStateAlreadyExists()
        return self.store.create(state)

    def checkpoint(self, state, **kwargs):
        if self.crash_started and kwargs.get("event_type") == "STARTED":
            raise RuntimeError("simulated crash")
        return self.store.checkpoint(state, **kwargs)

    def update(self, state):
        return self.store.update(state)

    def __getattr__(self, name):
        return getattr(self.store, name)


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


def test_initial_create_receives_non_started_state(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    app = _application(repo, settings, _CountingDomain())
    capture = _CaptureStore(SQLiteRuntimeStateStore(db))
    app.dispatcher.runtime_state_store = capture
    result = _dispatch(create_mcp_server(app), _init_payload())
    assert result["status"] == "READY"
    initial = capture.created[0]
    assert initial.current_progress == "NOT_STARTED"
    assert initial.current_phase == "INITIALIZED"
    assert initial.action_status is None
    assert initial.action_effect_type is None
    assert SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a").action_status == "COMPLETED"


def test_create_then_started_checkpoint_crash_leaves_non_started_row(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    app = _application(repo, settings, _CountingDomain())
    capture = _CaptureStore(SQLiteRuntimeStateStore(db), crash_started=True)
    app.dispatcher.runtime_state_store = capture
    assert _dispatch_allow_error(create_mcp_server(app), _init_payload()) is None
    state = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert state.action_status is None
    assert state.current_progress == "NOT_STARTED"
    assert not any(
        row["event_type"] == "STARTED"
        for row in SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    )


def test_create_race_fails_closed_without_domain(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain = _CountingDomain()
    app = _application(repo, settings, domain)
    app.dispatcher.runtime_state_store = _CaptureStore(SQLiteRuntimeStateStore(db), race=True)
    result = _dispatch(create_mcp_server(app), _init_payload())
    assert result["status"] == "RUNTIME_STATE_ALREADY_INITIALIZED"
    assert domain.calls == 0
    assert SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a").action_status is None


def test_first_turn_mutation_initializes_once_and_reopens(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(
        update={"runtime_state_path": "runtime.db", "live_execution": True}
    )
    mutation = {
        **_init_payload("write first file"),
        "intent": "execution",
        "effects": ["file_write"],
        "target_system": "local-file",
        "action_class": "write",
        "context": _context(blocker=None, target="local-file", action="write"),
    }
    first_domain = _CountingDomain()
    first = _dispatch(create_mcp_server(_application(repo, settings, first_domain)), mutation)
    state = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    before = SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    second_domain = _CountingDomain()
    second = _dispatch(
        create_mcp_server(_application(repo, settings, second_domain)),
        {**mutation, "runtime_state_initialize": False},
    )
    after = SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    assert first["status"] == "READY"
    assert second["status"] == "RUNTIME_STATE_WAIT"
    assert first_domain.calls == 1
    assert second_domain.calls == 0
    assert state.action_id and state.idempotency_key
    assert len([row for row in after if row["event_type"] == "CHECKPOINT_COMMITTED"]) == len(
        [row for row in before if row["event_type"] == "CHECKPOINT_COMMITTED"]
    )


def test_host_rejection_does_not_create_durable_state(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain = _CountingDomain()
    app = create_application(
        repo_root=repo,
        settings=settings,
        host_current_state_verifier=_FailingHostVerifier(),
    )
    app.dispatcher.domains[Owner.GLOBAL] = domain
    app.dispatcher.domains[Owner.EXECUTION] = domain
    payload = _init_payload()
    result = _dispatch(create_mcp_server(app), payload)
    assert result["status"] == "HOST_STATE_PROJECTION_STALE"
    assert domain.calls == 0
    with pytest.raises(RuntimeStateNotFound):
        SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    _journal_without_execution(db)


def test_pre_action_rejection_does_not_create_durable_state(tmp_path: Path):
    repo = _copy_authority_repo(tmp_path / "repo")
    db = repo / "runtime.db"
    settings = _test_settings().model_copy(
        update={"runtime_state_path": "runtime.db", "live_execution": True}
    )
    domain = _CountingDomain()
    app = _application(repo, settings, domain)
    mutation = {
        **_init_payload("blocked first write"),
        "intent": "execution",
        "effects": ["file_write"],
        "target_system": "local-file",
        "action_class": "write",
        "context": _context(blocker="QUOTA_5_OF_5", target="local-file", action="write"),
    }
    result = _dispatch(create_mcp_server(app), mutation)
    assert result["status"] == "PRE_ACTION_BLOCKED"
    assert domain.calls == 0
    with pytest.raises(RuntimeStateNotFound):
        SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    _journal_without_execution(db)
