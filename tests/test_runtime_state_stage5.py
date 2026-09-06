import asyncio
import json
from pathlib import Path

from mcp import Client
from mcp.types import TextContent

from global_hybrid_v2.adapters.mcp_server import create_mcp_server
from global_hybrid_v2.application import create_application
from global_hybrid_v2.contracts import DomainResult, Owner
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.transition import TransitionController
from tests._host_projection import TestHostCurrentStateVerifier, host_projection_payload
from tests.test_mcp_server import _copy_authority_repo, _test_settings
from tests.test_pre_action_constraints import _context
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


def _journal_dispatch_rows(db: Path, thread="thread-a", task="runtime-task-a"):
    with SQLiteRuntimeStateStore(db)._connect() as connection:
        return connection.execute(
            "SELECT dispatch_task_id, trace_id, stage, event_type FROM runtime_event_journal "
            "WHERE conversation_or_thread_id = ? AND task_id = ? ORDER BY rowid",
            (thread, task),
        ).fetchall()


class _CountingDomain:
    def __init__(self, status="READY"):
        self.calls = 0
        self.status = status

    def run(self, contract):
        self.calls += 1
        return DomainResult(owner=contract.owner, status=self.status, output="counted")


def _application(repo_root, settings, domain=None):
    app = create_application(
        repo_root=repo_root,
        settings=settings,
        host_current_state_verifier=TestHostCurrentStateVerifier(),
    )
    if domain is not None:
        app.dispatcher.domains[Owner.GLOBAL] = domain
        app.dispatcher.domains[Owner.EXECUTION] = domain
    return app


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
    journal1 = _journal_dispatch_rows(db)
    assert first["evidence"]["runtime_state"] == "COMMITTED"
    assert state1.runtime_checkpoint_id == first["evidence"]["runtime_checkpoint_id"]
    app2 = create_application(
        repo_root=repo_root,
        settings=settings,
        host_current_state_verifier=TestHostCurrentStateVerifier(),
    )
    second = _dispatch(create_mcp_server(app2), _payload())
    state2 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    journal2 = _journal_dispatch_rows(db)
    assert state2.conversation_or_thread_id == "thread-a"
    assert state2.task_id == "runtime-task-a"
    assert second["status"] == "RUNTIME_STATE_WAIT"
    dispatches = []
    for rows in (journal1, journal2):
        row = [row for row in rows if row[2] == "runtime_state_loaded"][-1]
        dispatches.append(row)
    assert dispatches[0][0] != dispatches[1][0]
    assert dispatches[0][1] != dispatches[1][1]
    assert all(row[0] and row[1] for row in dispatches)


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


def test_real_mcp_support_child_parent_resume_across_reopen(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    db = repo_root / "runtime.db"
    base = _state(
        primary_user_outcome="parent goal",
        active_subtask_id="child-task",
        resume_cursor="parent-cursor",
        next_action_candidate="parent-next",
    )
    store = SQLiteRuntimeStateStore(db)
    store.create(TransitionController().interrupt(base, "child-task"))
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain = _CountingDomain(status="DONE")
    app1 = _application(repo_root, settings, domain)
    first = _dispatch(create_mcp_server(app1), _payload())
    resumed = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert first["status"] == "DONE"
    assert resumed.active_subtask_id is None
    assert resumed.next_action_candidate == "parent-next"
    assert resumed.resume_cursor == "parent-cursor"
    assert resumed.primary_user_outcome == "parent goal"
    assert resumed.closure_state == "OPEN"
    resumed_before = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert resumed_before.current_phase == "PARENT_CONTINUATION"
    app2 = _application(repo_root, settings, _CountingDomain(status="DONE"))
    second = _dispatch(create_mcp_server(app2), _payload())
    assert second["status"] == "DONE"
    resumed_after = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert resumed_after.current_progress == second["status"]
    assert resumed_after.current_phase == "COMPLETED"
    assert resumed_after.active_subtask_id is None
    assert resumed_after.primary_user_outcome == "parent goal"
    assert resumed_after.next_action_candidate is None
    assert resumed_after.resume_cursor == "parent-cursor"


def test_real_mcp_support_suppression_across_reopen(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    db = repo_root / "runtime.db"
    SQLiteRuntimeStateStore(db).create(_state())
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    domain1 = _CountingDomain()
    first = _dispatch(create_mcp_server(_application(repo_root, settings, domain1)), _payload())
    state1 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    domain2 = _CountingDomain()
    second = _dispatch(create_mcp_server(_application(repo_root, settings, domain2)), _payload())
    state2 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert first["status"] == "READY"
    assert second["status"] == "RUNTIME_STATE_WAIT"
    assert domain1.calls == 1
    assert domain2.calls == 0
    assert state2.current_progress == state1.current_progress
    assert state2.next_action_candidate == state1.next_action_candidate
    assert state2.resume_cursor == state1.resume_cursor


def test_real_mcp_mutation_exactly_once_across_reopen(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    db = repo_root / "runtime.db"
    SQLiteRuntimeStateStore(db).create(_state())
    settings = _test_settings().model_copy(
        update={"runtime_state_path": "runtime.db", "live_execution": True}
    )
    mutation = {
        **_payload(),
        "intent": "execution",
        "effects": ["file_write"],
        "target_system": "local-file",
        "action_class": "write",
        "context": _context(blocker=None, target="local-file", action="write"),
    }
    domain1 = _CountingDomain()
    first = _dispatch(create_mcp_server(_application(repo_root, settings, domain1)), mutation)
    state1 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    checkpoint_count = len([
        row for row in SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
        if row["event_type"] == "CHECKPOINT_COMMITTED"
    ])
    domain2 = _CountingDomain()
    second = _dispatch(create_mcp_server(_application(repo_root, settings, domain2)), mutation)
    state2 = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    checkpoint_count_after = len([
        row for row in SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
        if row["event_type"] == "CHECKPOINT_COMMITTED"
    ])
    assert first["status"] == "READY"
    assert second["status"] == "RUNTIME_STATE_WAIT"
    assert domain1.calls == 1
    assert domain2.calls == 0
    assert state2.action_id == state1.action_id
    assert state2.idempotency_key == state1.idempotency_key
    assert state2.logical_action_identity == state1.logical_action_identity
    assert state2.runtime_checkpoint_id == state1.runtime_checkpoint_id
    assert checkpoint_count_after == checkpoint_count


def test_real_mcp_returned_evidence_and_stateless_isolation(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    db = repo_root / "runtime.db"
    SQLiteRuntimeStateStore(db).create(_state())
    settings = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    app = _application(repo_root, settings, _CountingDomain())
    server = create_mcp_server(app)
    returned = _dispatch(server, _payload())
    before = SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    state = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert returned["evidence"]["runtime_checkpoint_id"] == state.runtime_checkpoint_id
    assert returned["evidence"]["runtime_checkpoint_event_id"] == state.runtime_checkpoint_event_id
    checkpoint_rows = [
        row for row in before if row["event_type"] == "CHECKPOINT_COMMITTED"
    ]
    assert len(checkpoint_rows) == 1
    checkpoint = checkpoint_rows[0]
    assert checkpoint["event_id"] == state.runtime_checkpoint_event_id
    assert checkpoint["checkpoint_id"] == state.runtime_checkpoint_id
    started_rows = [row for row in before if row["event_type"] == "STARTED"]
    assert len(started_rows) == 1
    started = started_rows[0]
    assert state.action_id == started["action_id"] == checkpoint["action_id"]
    assert state.idempotency_key == started["idempotency_key"] == checkpoint["idempotency_key"]
    expected_state = {
        "primary_user_outcome": "finish work",
        "current_progress": "READY",
        "current_phase": "COMPLETED",
        "active_main_task_id": "runtime-task-a",
        "active_subtask_id": None,
        "resume_cursor": None,
        "next_action_candidate": None,
    }
    for field, expected in expected_state.items():
        assert getattr(state, field) == expected
    reopened = SQLiteRuntimeStateStore(db).load("thread-a", "runtime-task-a")
    assert reopened.model_dump(mode="json") == state.model_dump(mode="json")
    stateless = _dispatch(
        server,
        {
            "request_text": "status",
            "intent": "execution",
            "effects": ["read_only"],
            **host_projection_payload(),
        },
    )
    after = SQLiteRuntimeStateStore(db).journal("thread-a", "runtime-task-a")
    assert stateless["status"] == "READY"
    assert after == before


def test_real_mcp_negative_runtime_bindings(tmp_path: Path):
    repo_root = _copy_authority_repo(tmp_path / "repo")
    settings = _test_settings()
    no_store = _dispatch(
        create_mcp_server(_application(repo_root, settings)),
        _payload(),
    )
    assert no_store["status"] == "RUNTIME_STATE_BINDING_REQUIRED"
    db = repo_root / "runtime.db"
    SQLiteRuntimeStateStore(db).create(_state())
    configured = _test_settings().model_copy(update={"runtime_state_path": "runtime.db"})
    missing = _dispatch(
        create_mcp_server(_application(repo_root, configured)),
        {**_payload(), "runtime_task_id": "missing-task"},
    )
    assert missing["status"] == "RUNTIME_STATE_LOAD_BLOCKED"
    with SQLiteRuntimeStateStore(db)._connect() as connection:
        connection.execute("UPDATE runtime_task_state SET runtime_state_version = 0")
    stale = _dispatch(create_mcp_server(_application(repo_root, configured)), _payload())
    assert stale["status"] == "RUNTIME_STATE_LOAD_BLOCKED"
