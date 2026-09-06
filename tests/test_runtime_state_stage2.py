from datetime import UTC, datetime

import pytest

from global_hybrid_v2.contracts import AuthoritySnapshot, DomainResult, EffectType, Intent, Owner, TaskRequest
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.state import RuntimeTaskState, SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.runtime.transition import TransitionController, TransitionDecision


class _Authority:
    def resolve(self):
        return AuthoritySnapshot(entries={})


class _Domain:
    def __init__(self):
        self.calls = 0
        self.contracts = []

    def run(self, contract):
        self.calls += 1
        self.contracts.append(contract)
        return DomainResult(owner=contract.owner, status="DONE")


def _state(*, thread="thread-a", task="runtime-task-a", **updates):
    values = {
        "runtime_state_version": 1,
        "conversation_or_thread_id": thread,
        "task_id": task,
        "primary_user_outcome": "finish work",
        "current_progress": "interrupted",
        "active_main_task_id": task,
        "current_phase": "EXECUTION",
        "current_authority_revisions": {},
        "current_requirement_ids": ["REQ-1"],
        "next_action_candidate": "continue",
        "closure_state": "OPEN",
        "updated_at": datetime.now(UTC),
    }
    values.update(updates)
    return RuntimeTaskState(**values)


def _dispatcher(store, domain=None):
    return Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: domain or _Domain()},
        trace=TraceBus(),
        runtime_state_store=store,
    )


def _request(**updates):
    values = {
        "request_text": "continue work",
        "intent": Intent.EXECUTION,
        "effects": [EffectType.READ_ONLY],
        "runtime_state_required": True,
        "conversation_or_thread_id": "thread-a",
        "runtime_task_id": "runtime-task-a",
    }
    values.update(updates)
    return TaskRequest(**values)


def test_stateful_request_loads_transitions_consumes_and_persists(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    domain = _Domain()
    result = _dispatcher(store, domain).dispatch(_request())

    assert result.status == "DONE"
    assert domain.calls == 1
    persisted = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a")
    assert persisted.current_progress == "DONE"
    assert persisted.current_phase == "COMPLETED"
    assert persisted.last_action_result == "DONE"


def test_stateful_missing_identity_or_state_blocks_before_domain(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    domain = _Domain()
    missing = _dispatcher(store, domain).dispatch(
        _request(conversation_or_thread_id=None)
    )
    absent = _dispatcher(store, domain).dispatch(_request())
    assert missing.status == "RUNTIME_STATE_BINDING_REQUIRED"
    assert absent.status == "RUNTIME_STATE_LOAD_BLOCKED"
    assert domain.calls == 0


def test_stateful_thread_task_key_does_not_cross_contaminate(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(thread="thread-a", task="task-a"))
    store.create(_state(thread="thread-b", task="task-b"))
    result = _dispatcher(store).dispatch(_request(runtime_task_id="task-b"))
    assert result.status == "RUNTIME_STATE_LOAD_BLOCKED"


def test_transition_controller_keeps_support_candidate_stable():
    state = _state(next_action_candidate="support")
    controller = TransitionController()
    first = controller.decide(state, _request(runtime_state_required=False))
    second = controller.decide(state, _request(runtime_state_required=False))
    assert first == second
    assert first.kind == "SUPPORT"


def test_transition_controller_marks_mutation_candidate_executable():
    state = _state(next_action_candidate="publish")
    request = _request(runtime_state_required=False).model_copy(
        update={"effects": [EffectType.FILE_WRITE]}
    )
    assert TransitionController().decide(state, request).kind == "EXECUTE"


def test_completed_support_clears_subtask_and_keeps_parent():
    state = _state(
        active_subtask_id="support-1",
        active_main_task_id="main-1",
        resume_cursor="parent-next",
    )
    result = DomainResult(owner=Owner.GLOBAL, status="DONE")
    updated = TransitionController().consume_result(
        state, _request(runtime_state_required=False), result,
        TransitionDecision("SUPPORT", "done"),
    )
    assert updated.active_subtask_id is None
    assert updated.active_main_task_id == "main-1"
    assert updated.next_action_candidate == "parent-next"
    assert updated.closure_state == "OPEN"


def test_support_child_completion_resumes_parent_on_next_dispatch(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(
        _state(
            task="task-a",
            active_subtask_id="support-1",
            active_main_task_id="main-1",
            resume_cursor="parent-next",
        )
    )
    domain = _Domain()
    dispatcher = _dispatcher(store, domain)
    first = dispatcher.dispatch(_request(runtime_task_id="task-a"))
    assert first.status == "DONE"
    persisted = store.load("thread-a", "task-a")
    assert persisted.active_subtask_id is None
    assert persisted.active_main_task_id == "main-1"
    assert persisted.next_action_candidate == "parent-next"
    assert persisted.closure_state == "OPEN"
    second = dispatcher.dispatch(_request(runtime_task_id="task-a"))
    assert second.status == "DONE"
    assert domain.calls == 2
    assert domain.contracts[0].task_id != domain.contracts[1].task_id
    assert domain.contracts[0].task_trace_id != domain.contracts[1].task_trace_id
    final = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "task-a")
    assert final.conversation_or_thread_id == persisted.conversation_or_thread_id == "thread-a"
    assert final.task_id == persisted.task_id == "task-a"


def _completed_support(**updates):
    values = {
        "current_progress": "READY",
        "action_status": "COMPLETED",
        "action_result_status": "READY",
        "action_result_output": "support evidence",
        "action_result_evidence": {"support": "checked"},
        "logical_action_identity": "continue",
        "last_action_result": "READY",
    }
    values.update(updates)
    return _state(**values)


@pytest.mark.parametrize("effects", [[EffectType.READ_ONLY], [EffectType.MODEL_INFERENCE], []])
def test_repeated_support_without_new_value_does_not_execute_or_change_state(tmp_path, effects):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    original = store.create(_completed_support())
    domain = _Domain()
    dispatcher = _dispatcher(store, domain)
    for _ in range(2):
        result = dispatcher.dispatch(_request(effects=effects))
        assert result.status == "RUNTIME_STATE_WAIT"
        assert result.evidence["transition"] == "SUPPORT"
    assert domain.calls == 0
    assert SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a") == original


def test_produced_support_state_suppresses_identical_second_dispatch(tmp_path):
    class ReadyDomain(_Domain):
        def run(self, contract):
            self.calls += 1
            self.contracts.append(contract)
            return DomainResult(owner=contract.owner, status="READY", output="still working")

    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(next_action_candidate="continue"))
    domain = ReadyDomain()
    dispatcher = _dispatcher(store, domain)
    first = dispatcher.dispatch(_request())
    assert first.status == "READY"
    produced = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a")
    assert produced.next_action_candidate is None
    assert produced.current_phase == "COMPLETED"
    second = dispatcher.dispatch(_request())
    assert second.status == "RUNTIME_STATE_WAIT"
    assert domain.calls == 1
    assert SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a") == produced


@pytest.mark.parametrize("updates", [
    {"next_action_candidate": "new support"},
    {"current_progress": "new evidence available"},
    {"active_subtask_id": "support-2", "resume_cursor": "parent-next"},
    {"current_phase": "PARENT_CONTINUATION"},
])
def test_support_with_new_progress_or_continuation_still_executes(tmp_path, updates):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_completed_support(**updates))
    domain = _Domain()
    assert _dispatcher(store, domain).dispatch(_request()).status == "DONE"
    assert domain.calls == 1


def test_mutation_candidate_executes_with_existing_gates(tmp_path):
    from tests.test_pre_action_constraints import _context

    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_completed_support())
    domain = _Domain()
    result = _dispatcher(store, domain).dispatch(_request(
        effects=[EffectType.FILE_WRITE],
        target_system="local-file",
        action_class="write",
        context=_context(blocker=None, target="local-file", action="write"),
    ))
    assert result.status == "DONE"
    assert result.evidence["runtime_transition"] == "EXECUTE"
    assert domain.calls == 1


def test_stale_state_binding_blocks_before_domain(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    with store._connect() as connection:
        connection.execute("UPDATE runtime_task_state SET runtime_state_version = 0")
    domain = _Domain()
    result = _dispatcher(store, domain).dispatch(_request())
    assert result.status == "RUNTIME_STATE_LOAD_BLOCKED"
    assert domain.calls == 0


def test_required_research_persists_final_resumed_result(tmp_path, capsys):
    import json

    from tests.test_research_loop import (
        _CapabilityDomain,
        _execution_receipt,
        _FakeResearchPort,
    )
    from tests.test_research_loop import _dispatcher as research_dispatcher
    from tests.test_research_loop import _request as research_request

    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    domain = _CapabilityDomain()
    provider = _FakeResearchPort(lambda request, _: _execution_receipt(request))
    dispatcher = research_dispatcher(domain, provider)
    dispatcher.runtime_state_store = store
    result = dispatcher.dispatch(research_request().model_copy(update={
        "runtime_state_required": True,
        "conversation_or_thread_id": "thread-a",
        "runtime_task_id": "runtime-task-a",
    }))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "research_required" in {event["stage"] for event in events}
    assert "task_resumed" in {event["stage"] for event in events}
    assert len(provider.requests) == 1
    assert len(domain.contracts) == 2
    assert domain.contracts[0].task_id == domain.contracts[1].task_id == provider.requests[0].task_id
    assert result.status == "READY"
    persisted = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a")
    assert persisted.current_progress == persisted.last_action_result == result.status
    assert persisted.action_result_status == result.status
    assert persisted.action_result_output == result.output
    assert persisted.action_result_evidence == {
        key: value for key, value in result.evidence.items()
        if key not in {"runtime_state", "runtime_transition"}
    }
    assert persisted.action_status == "COMPLETED"


def test_stateless_request_remains_unchanged(tmp_path):
    domain = _Domain()
    result = _dispatcher(SQLiteRuntimeStateStore(tmp_path / "runtime.db"), domain).dispatch(
        TaskRequest(request_text="status", intent=Intent.EXECUTION, effects=[EffectType.READ_ONLY])
    )
    assert result.status == "DONE"
    assert domain.calls == 1
