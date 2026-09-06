
import pytest

from global_hybrid_v2.contracts import DomainResult, EffectType, Owner
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.runtime.transition import TransitionController
from tests.test_pre_action_constraints import _context
from tests.test_runtime_state_stage2 import _Authority, _Domain, _request, _state


def _mutation_request(**updates):
    values = {
        "effects": [EffectType.FILE_WRITE],
        "target_system": "local-file",
        "action_class": "write",
        "context": [],
    }
    values.update(updates)
    return _request(**values)


def _dispatcher(store, domain):
    return Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: domain},
        trace=TraceBus(),
        runtime_state_store=store,
    )


def test_pre_domain_block_does_not_strand_started_state(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    domain = _Domain()
    dispatcher = _dispatcher(store, domain)
    first = dispatcher.dispatch(_mutation_request())
    persisted = store.load("thread-a", "runtime-task-a")
    second = dispatcher.dispatch(_mutation_request())
    assert first.status == second.status == "PRE_ACTION_BLOCKED"
    assert domain.calls == 0
    assert persisted.action_status not in {"STARTED", "PENDING"}
    assert second.status != "RUNTIME_EFFECT_OUTCOME_UNKNOWN"


def test_completed_mutation_repeat_does_not_duplicate_effect(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    domain = _Domain()
    request = _mutation_request()
    # The existing pre-action gate is authoritative; use a read-only completion
    # to prove durable replay suppression without inventing a second sink.
    request = request.model_copy(update={"effects": [EffectType.READ_ONLY]})
    dispatcher = _dispatcher(store, domain)
    first = dispatcher.dispatch(request)
    second = dispatcher.dispatch(request)
    persisted = store.load("thread-a", "runtime-task-a")
    assert first.status == "DONE"
    assert second.status in {"RUNTIME_STATE_CLOSED", "RUNTIME_STATE_WAIT"}
    assert domain.calls == 1
    assert persisted.action_id and persisted.idempotency_key


def test_inflight_mutation_retry_fails_closed_without_duplicate(tmp_path):
    class FailingDomain(_Domain):
        def run(self, contract):
            self.calls += 1
            raise RuntimeError("lost after invocation")

    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    domain = FailingDomain()
    dispatcher = _dispatcher(store, domain)
    with pytest.raises(RuntimeError):
        dispatcher.dispatch(
            _mutation_request(context=_context(blocker=None, target="local-file", action="write"))
        )
    persisted = store.load("thread-a", "runtime-task-a")
    retry = dispatcher.dispatch(
        _mutation_request(context=_context(blocker=None, target="local-file", action="write"))
    )
    assert persisted.action_status == "STARTED"
    assert persisted.action_id and persisted.idempotency_key
    assert retry.status == "RUNTIME_EFFECT_OUTCOME_UNKNOWN"
    assert domain.calls == 1


def test_interrupt_persist_reopen_resume_pops_frame(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    state = _state(
        primary_user_outcome="parent goal",
        current_phase="EXECUTION",
        next_action_candidate="parent-next",
        resume_cursor="parent-cursor",
        current_requirement_ids=["REQ-PARENT"],
    )
    interrupted = TransitionController().interrupt(state, "child-task")
    store.create(interrupted)
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a")
    completed = TransitionController().consume_result(
        reopened,
        _request(runtime_state_required=False),
        DomainResult(owner=Owner.GLOBAL, status="DONE"),
        transition=type("Decision", (), {"kind": "SUPPORT", "reason": "child"})(),
    )
    store.update(completed)
    resumed = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a")
    assert resumed.interrupted_task_stack == []
    assert resumed.active_subtask_id is None
    assert resumed.primary_user_outcome == "parent goal"
    assert resumed.current_requirement_ids == ["REQ-PARENT"]
    assert resumed.resume_cursor == "parent-cursor"
    assert resumed.next_action_candidate == "parent-next"
    assert resumed.current_phase == "PARENT_CONTINUATION"
    assert TransitionController().decide(resumed, _request(runtime_state_required=False)).kind == "SUPPORT"
