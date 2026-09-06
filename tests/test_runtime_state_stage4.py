from pathlib import Path

import pytest

from global_hybrid_v2.contracts import Intent, Owner, TaskRequest, WitnessFinding
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.state import RuntimeStateNotFound, SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from tests.test_runtime_state_stage2 import _Authority, _Domain, _request, _state


def test_journal_chain_survives_reopen_and_stateless_isolated(tmp_path: Path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    dispatcher = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: _Domain()},
        trace=TraceBus(),
        runtime_state_store=store,
    )
    dispatcher.dispatch(_request())
    before = store.journal("thread-a", "runtime-task-a")
    assert any(item["stage"] == "runtime_state_loaded" for item in before)
    assert any(item["event_type"] == "STARTED" for item in before)
    assert any(item["event_type"] == "CHECKPOINT_COMMITTED" for item in before)
    dispatcher.dispatch(TaskRequest(request_text="status", intent=Intent.EXECUTION))
    assert store.journal("thread-a", "runtime-task-a") == before
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    assert reopened.load("thread-a", "runtime-task-a").runtime_checkpoint_id


def test_checkpoint_missing_row_rolls_back_journal(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    state = _state()
    store.create(state)
    with store._connect() as connection:
        connection.execute(
            "DELETE FROM runtime_task_state WHERE conversation_or_thread_id = ? AND task_id = ?",
            (state.conversation_or_thread_id, state.task_id),
        )
    with pytest.raises(RuntimeStateNotFound):
        store.checkpoint(state, stage="state_after")
    assert store.journal("thread-a", "runtime-task-a") == []


def test_witness_finding_has_committed_identity(tmp_path):
    class FindingWitness:
        def observe(self, event):
            return WitnessFinding(
                task_id=event.task_id,
                severity="error",
                code="TEST_FINDING",
                message="test",
            )

        def consumption_assessment_for_task(self, task_id):
            return {}

    bus = TraceBus(witness=FindingWitness())
    bus.bind_runtime(SQLiteRuntimeStateStore(tmp_path / "runtime.db"), "thread", "task")
    # The identity propagation is asserted on the real emitted event shape;
    # persistence is covered by the produced dispatcher test above.
    bus.bind_runtime_context(action_id="action-1", checkpoint_id="checkpoint-1")
    event = bus.emit(task_id="dispatch", stage="response_egress", decision="PASS")
    finding = bus.findings_for_task("dispatch")[0]
    assert finding.observed_event_id == event.event_id
    assert finding.action_id == "action-1"
    assert finding.checkpoint_id == "checkpoint-1"
