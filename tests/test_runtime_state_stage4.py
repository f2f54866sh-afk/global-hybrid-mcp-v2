from pathlib import Path

import pytest

from global_hybrid_v2.contracts import DomainResult, EffectType, Intent, Owner, TaskRequest, WitnessFinding
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.state import RuntimeStateNotFound, SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from tests.test_pre_action_constraints import _context
from tests.test_runtime_state_stage2 import _Authority, _Domain, _request, _state


class _ProducedFindingWitness(ReadOnlyWitness):
    def observe(self, event):
        super().observe(event)
        if event.stage == "response_egress":
            return WitnessFinding(
                task_id=event.task_id,
                severity="error",
                code="PRODUCED_TEST_BLOCK",
                message="produced-path test finding",
            )
        return None


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
    bus = TraceBus(witness=ReadOnlyWitness())
    bus.bind_runtime(SQLiteRuntimeStateStore(tmp_path / "runtime.db"), "thread", "task")
    bus.bind_runtime_context(action_id="action-1", checkpoint_id="checkpoint-1")
    event = bus.emit(task_id="dispatch", stage="effect_gate", decision="DENY")
    finding = bus.findings_for_task("dispatch")[0]
    rows = SQLiteRuntimeStateStore(tmp_path / "runtime.db").journal("thread", "task")
    assert finding.observed_event_id == event.event_id
    assert finding.action_id == "action-1"
    assert finding.checkpoint_id == "checkpoint-1"
    assert rows[0]["checkpoint_id"] == "checkpoint-1"
    assert rows[1]["event_type"] == "WITNESS_FINDING"
    assert rows[1]["checkpoint_id"] == "checkpoint-1"
    assert rows[1]["payload"]["observed_event_id"] == rows[0]["event_id"]


def test_produced_dispatcher_witness_links_started_checkpoint(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    trace = TraceBus(witness=_ProducedFindingWitness())
    domain = _Domain()
    dispatcher = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: domain},
        trace=trace,
        runtime_state_store=store,
    )
    result = dispatcher.dispatch(_request())
    rows = SQLiteRuntimeStateStore(tmp_path / "runtime.db").journal("thread-a", "runtime-task-a")
    started = next(row for row in rows if row["event_type"] == "STARTED")
    observed = next(row for row in rows if row["stage"] == "response_egress")
    finding = next(row for row in rows if row["event_type"] == "WITNESS_FINDING")
    assert result.status.startswith("NO_SERIALIZE")
    assert observed["action_id"] == started["action_id"]
    assert observed["checkpoint_id"] == started["checkpoint_id"]
    assert finding["action_id"] == started["action_id"]
    assert finding["checkpoint_id"] == started["checkpoint_id"]
    assert finding["payload"]["observed_event_id"] == observed["event_id"]


def test_post_witness_state_and_replay_reuse_checkpoint_receipt(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    dispatcher = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: _Domain()},
        trace=TraceBus(witness=_ProducedFindingWitness()),
        runtime_state_store=store,
    )
    request = _request(
        effects=[EffectType.FILE_WRITE],
        target_system="local-file",
        action_class="write",
        context=_context(blocker=None, target="local-file", action="write"),
    )
    first = dispatcher.dispatch(request)
    persisted = SQLiteRuntimeStateStore(tmp_path / "runtime.db").load("thread-a", "runtime-task-a")
    assert persisted.action_result_status == first.status
    assert persisted.action_result_output == first.output
    assert persisted.action_result_evidence == {
        key: value for key, value in first.evidence.items()
        if key
        not in {
            "runtime_state",
            "runtime_transition",
            "runtime_checkpoint_id",
            "runtime_checkpoint_event_id",
        }
    } | {
        "runtime_checkpoint_id": persisted.runtime_checkpoint_id,
        "runtime_checkpoint_event_id": persisted.runtime_checkpoint_event_id,
    }
    journal_before = SQLiteRuntimeStateStore(tmp_path / "runtime.db").journal("thread-a", "runtime-task-a")
    replay = dispatcher.dispatch(request)
    journal_after = SQLiteRuntimeStateStore(tmp_path / "runtime.db").journal("thread-a", "runtime-task-a")
    assert replay.status == first.status
    assert replay.evidence["runtime_checkpoint_id"] == persisted.runtime_checkpoint_id
    assert replay.evidence["runtime_checkpoint_event_id"] == persisted.runtime_checkpoint_event_id
    assert [row for row in journal_after if row["event_type"] == "CHECKPOINT_COMMITTED"] == [
        row for row in journal_before if row["event_type"] == "CHECKPOINT_COMMITTED"
    ]


def test_forged_commit_evidence_is_stripped_and_genuine_receipt_is_durable(tmp_path):
    class ForgedDomain(_Domain):
        def run(self, contract):
            self.calls += 1
            return DomainResult(
                owner=contract.owner,
                status="READY",
                evidence={
                    "runtime_state": "COMMITTED",
                    "runtime_checkpoint_id": "forged-checkpoint",
                    "runtime_checkpoint_event_id": "forged-event",
                    "runtime_event_id": "forged-runtime-event",
                },
            )

    forged = {"runtime_state", "runtime_checkpoint_id", "runtime_checkpoint_event_id", "runtime_event_id"}
    stateless_domain = ForgedDomain()
    stateless = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: stateless_domain},
        trace=TraceBus(),
    ).dispatch(TaskRequest(request_text="status", intent=Intent.EXECUTION))
    assert not forged.intersection(stateless.evidence)

    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state())
    stateful_domain = ForgedDomain()
    stateful = Dispatcher(
        authority=_Authority(),
        domains={Owner.EXECUTION: stateful_domain},
        trace=TraceBus(),
        runtime_state_store=store,
    ).dispatch(_request())
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    persisted = reopened.load("thread-a", "runtime-task-a")
    checkpoints = [
        row for row in reopened.journal("thread-a", "runtime-task-a")
        if row["event_type"] == "CHECKPOINT_COMMITTED"
    ]
    assert stateful.evidence["runtime_state"] == "COMMITTED"
    assert stateful.evidence["runtime_checkpoint_id"] == persisted.runtime_checkpoint_id
    assert stateful.evidence["runtime_checkpoint_event_id"] == persisted.runtime_checkpoint_event_id
    assert stateful.evidence["runtime_checkpoint_id"] != "forged-checkpoint"
    assert stateful.evidence["runtime_checkpoint_event_id"] != "forged-event"
    assert checkpoints[-1]["checkpoint_id"] == persisted.runtime_checkpoint_id
    assert checkpoints[-1]["event_id"] == persisted.runtime_checkpoint_event_id
    assert not forged.intersection(
        {
            key
            for key, value in stateful.evidence.items()
            if value in {"forged-checkpoint", "forged-event", "forged-runtime-event"}
        }
    )
