from datetime import UTC, datetime

from global_hybrid_v2.contracts import AuthoritySnapshot, DomainResult, EffectType, Intent, Owner, TaskRequest
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.state import RuntimeTaskState, SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.runtime.transition import TransitionController


class _Authority:
    def resolve(self):
        return AuthoritySnapshot(entries={})


class _Domain:
    def __init__(self):
        self.calls = 0

    def run(self, contract):
        self.calls += 1
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
    assert first.kind == "EXECUTE"


def test_stateless_request_remains_unchanged(tmp_path):
    domain = _Domain()
    result = _dispatcher(SQLiteRuntimeStateStore(tmp_path / "runtime.db"), domain).dispatch(
        TaskRequest(request_text="status", intent=Intent.EXECUTION, effects=[EffectType.READ_ONLY])
    )
    assert result.status == "DONE"
    assert domain.calls == 1
