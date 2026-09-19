"""Synthetic Copy only: no Sales production, image, product or publishing calls."""
import json
from dataclasses import replace

import pytest

from global_hybrid_v2.contracts import DomainResult, EffectType, Intent, Owner, TaskContract, TaskRequest
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.public_copy import STAGES, CopyCheckResult, digest
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from tests.test_runtime_state_stage2 import _state
from tests.test_sales_consumption_e2e import _application


class RecordingChecks:
    def __init__(self, corrupt=None):
        self.calls = []
        self.corrupt = corrupt

    def evaluate(self, *, stage, candidate_json, witness_json, requirement_ids):
        self.calls.append((stage, candidate_json, witness_json))
        exact = digest(json.loads(candidate_json))
        details = {}
        if stage == STAGES[0]:
            details = {
                "public_copy_acceptance_witness": "PASS",
                "hard_requirement_coverage": {
                    key: {"decision": "PASS", "exact_candidate_digest": exact} for key in requirement_ids
                },
                "non_binding_literal_leak_check": "PASS",
                "supporting_proof_serialization": "PASS",
                "supporting_proof": {"source": "synthetic fixture", "candidate": exact},
            }
        elif stage in {"disposition_invariance", "copy_egress_audit"}:
            details[stage] = "PASS"
        receipt = CopyCheckResult("PASS", exact, digest(json.loads(witness_json)) if witness_json else None,
                                  details)
        return self.corrupt(stage, receipt) if self.corrupt else receipt


class RecordingSales:
    def __init__(self):
        self.contracts = []

    def run(self, contract):
        self.contracts.append(contract)
        return DomainResult(owner=Owner.SALES_HUMAN, status="DONE", output="synthetic candidate A")


def setup(tmp_path, *, port=None, trace=None):
    app = _application(tmp_path)
    dispatcher = app.dispatcher
    store = SQLiteRuntimeStateStore(tmp_path / "copy.db")
    store.create(_state())
    dispatcher.runtime_state_store = store
    dispatcher.public_copy_checks = port
    if trace:
        dispatcher.trace = trace
    return dispatcher, store


def contract(public=True):
    return TaskContract(task_id="dispatch-a", request_text="synthetic copy", intent=Intent.SALES_HUMAN,
                        owner=Owner.SALES_HUMAN, effects=[EffectType.READ_ONLY], authority_snapshot_id="fake",
                        context=[], public_commercial_copy=public, public_copy_requirement_ids=["REQ-1"])


def readback(store, dispatch_id=None, terminal_id=None):
    rows = store.journal("thread-a", "runtime-task-a")
    terminal = next(row for row in reversed(rows) if row["stage"] in {"closure", "response_egress"})
    return ReadOnlyWitness().assess_public_copy(
        store, conversation_id="thread-a", runtime_task_id="runtime-task-a",
        dispatch_task_id=dispatch_id or terminal["payload"]["task_id"],
        trace_id=terminal["payload"]["trace_id"], terminal_event_id=terminal_id or terminal["event_id"],
    )


def egress(tmp_path, port, trace=None, public=True):
    dispatcher, store = setup(tmp_path, port=port, trace=trace)
    dispatcher.trace.bind_runtime(store, "thread-a", "runtime-task-a")
    result = dispatcher._validate_egress(
        contract(public), DomainResult(owner=Owner.SALES_HUMAN, status="DONE", output="synthetic candidate A",
                                      evidence={"PUBLIC_COPY_ACCEPTANCE_WITNESS": "PASS"}),
    )
    return result, store


def test_full_positive_dispatch_reopen(tmp_path):
    port = RecordingChecks()
    dispatcher, store = setup(tmp_path, port=port)
    sales = RecordingSales()
    dispatcher.domains[Owner.SALES_HUMAN] = sales
    result = dispatcher.dispatch(TaskRequest(
        request_text="synthetic copy", intent=Intent.SALES_HUMAN,
        public_commercial_copy=True, public_copy_requirement_ids=["REQ-1"],
        runtime_state_required=True, conversation_or_thread_id="thread-a", runtime_task_id="runtime-task-a",
    ))
    assert result.status == "DONE"
    assert len(sales.contracts) == 1
    assert result.evidence["public_copy_execution_lineage"] == "PASS"
    assert [call[0] for call in port.calls] == list(STAGES)
    assert port.calls[1][2] == port.calls[2][2]
    reopened = SQLiteRuntimeStateStore(tmp_path / "copy.db")
    checks = readback(reopened)
    assert len(checks) == 8 and all(checks.values())
    state = reopened.load("thread-a", "runtime-task-a")
    assert state.action_result_output == result.output
    assert state.action_result_evidence["public_copy_execution_lineage"] == "PASS"
    assert any(row["event_type"] == "CHECKPOINT_COMMITTED"
               for row in store.journal("thread-a", "runtime-task-a"))


class MissingWitnessTrace(TraceBus):
    def __init__(self, missing=STAGES[0]):
        super().__init__(ReadOnlyWitness())
        self.missing = missing

    def emit(self, **kwargs):
        if kwargs["stage"] == self.missing:
            kwargs["stage"] = "not_an_acceptance_witness"
        return super().emit(**kwargs)


@pytest.mark.parametrize("missing", ["public_copy_candidate", *STAGES])
def test_missing_witness_stage(tmp_path, missing):
    result, store = egress(tmp_path, RecordingChecks(), MissingWitnessTrace(missing))
    assert result.output is None
    assert not all(readback(store).values())


@pytest.mark.parametrize(
    "fault", ["candidate", "witness", "invariance", "audit", "coverage", "leak", "proof"],
)
def test_mismatches_fail_closed(tmp_path, fault):
    def corrupt(stage, receipt):
        if fault == "candidate" and stage == STAGES[0]:
            return replace(receipt, exact_candidate_digest=digest("candidate B"))
        if fault == "witness" and stage == "detached_product_oracle":
            return replace(receipt, witness_digest=digest("different witness"))
        if (fault == "invariance" and stage == "disposition_invariance"
                or fault == "audit" and stage == "copy_egress_audit"):
            return replace(receipt, decision="FAIL")
        if stage == STAGES[0]:
            field = {"coverage": "hard_requirement_coverage", "leak": "non_binding_literal_leak_check",
                     "proof": "supporting_proof_serialization"}.get(fault)
            if field:
                return replace(receipt, details={**receipt.details, field: "FAIL"})
        return receipt

    result, store = egress(tmp_path, RecordingChecks(corrupt))
    assert result.output is None and result.final_response_object is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
    assert not all(readback(SQLiteRuntimeStateStore(tmp_path / "copy.db")).values())
    assert any(row["event_type"] == "WITNESS_FINDING" for row in store.journal("thread-a", "runtime-task-a"))


def test_self_asserted_evidence_without_configured_execution_fails(tmp_path):
    result, store = egress(tmp_path, None)
    assert result.output is None
    assert not all(readback(store).values())


def test_post_hoc_events_cannot_repair_earlier_egress(tmp_path):
    dispatcher, store = setup(tmp_path, port=RecordingChecks())
    dispatcher.trace.bind_runtime(store, "thread-a", "runtime-task-a")
    early = dispatcher.trace.emit(task_id="dispatch-a", stage="response_egress", decision="PASS",
                                  metadata={"PUBLIC_COPY_ACCEPTANCE_WITNESS": "PASS"})
    dispatcher._validate_egress(contract(), RecordingSales().run(contract()))
    assert not all(readback(store, terminal_id=early.event_id).values())


def test_ordinary_task_does_not_invoke_checks(tmp_path):
    port = RecordingChecks()
    result, store = egress(tmp_path, port, public=False)
    assert result.status == "DONE" and port.calls == []
    assert not any(row["stage"] in STAGES for row in store.journal("thread-a", "runtime-task-a"))


def test_no_durable_binding_fails(tmp_path):
    dispatcher, _ = setup(tmp_path, port=RecordingChecks())
    result = dispatcher._validate_egress(contract(), RecordingSales().run(contract()))
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"


def test_other_dispatch_cannot_borrow_lineage(tmp_path):
    _, store = egress(tmp_path, RecordingChecks())
    assert not all(readback(store, dispatch_id="dispatch-b").values())


@pytest.mark.parametrize("fault", ["non_json_proof", "exception", "invalid_receipt", "invalid_decision"])
def test_invalid_check_execution_fails_closed(tmp_path, fault):
    def corrupt(stage, receipt):
        if stage == STAGES[0]:
            if fault == "exception":
                raise RuntimeError("synthetic check failure")
            if fault == "non_json_proof":
                return replace(receipt, details={"supporting_proof": object()})
            if fault == "invalid_receipt":
                return replace(receipt, details=["invalid"])
            return replace(receipt, decision="UNKNOWN")
        return receipt
    result, store = egress(tmp_path, RecordingChecks(corrupt))
    assert result.output is None
    assert not all(readback(store).values())


def test_public_copy_cannot_replay_unverified_committed_result(tmp_path):
    dispatcher, store = setup(tmp_path, port=RecordingChecks())
    state = store.load("thread-a", "runtime-task-a").model_copy(update={
        "action_status": "COMPLETED", "action_result_status": "DONE", "next_action_candidate": None,
        "closure_state": "CLOSED", "action_result_output": "unverified old copy",
    })
    store.checkpoint(state, stage="state_after")
    result = dispatcher.dispatch(TaskRequest(
        request_text="synthetic copy", intent=Intent.SALES_HUMAN, public_commercial_copy=True,
        runtime_state_required=True, conversation_or_thread_id="thread-a", runtime_task_id="runtime-task-a",
    ))
    assert result.output is None
    assert result.evidence["blocker_code"] == "PUBLIC_COPY_REPLAY_REQUIRES_NEW_DISPATCH"


@pytest.mark.parametrize("fault", ["candidate_b_egress", "input_refs", "trace_id", "runtime_task"])
def test_terminal_lineage_drift_is_rejected(tmp_path, fault):
    class DriftTrace(TraceBus):
        def emit(self, **kwargs):
            if kwargs["stage"] == "response_egress":
                if fault == "candidate_b_egress":
                    kwargs["metadata"]["exact_candidate_digest"] = digest("candidate B")
                elif fault == "input_refs":
                    kwargs["metadata"]["input_refs"] = ["nonexistent-journal-event"]
                elif fault == "trace_id":
                    self.start_task(kwargs["task_id"])
                else:
                    self._runtime_binding = ("thread-a", "runtime-task-b")
            return super().emit(**kwargs)
    result, _ = egress(tmp_path, RecordingChecks(), DriftTrace(ReadOnlyWitness()))
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
