"""Synthetic Host oracle ingress only; no real Sales/product/image/publishing effects."""
from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.contracts import (
    ContextClass,
    ContextItem,
    ContextOrigin,
    DomainResult,
    Intent,
    Owner,
    PublicCopyHardRequirement,
    PublicCopySourceKind,
    PublicCopySourceRef,
    TaskRequest,
)
from global_hybrid_v2.governance.public_copy_oracle import (
    PUBLIC_COPY_ORACLE_FRAME_MISMATCH,
    PUBLIC_COPY_ORACLE_INPUT_REQUIRED,
    PUBLIC_COPY_ORACLE_INPUT_STALE,
    PUBLIC_COPY_ORACLE_INPUT_UNVERIFIED,
    PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID,
    PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID,
    PUBLIC_COPY_ORACLE_TASK_SCOPE_MISMATCH,
    PublicCopyOracleGate,
)
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.public_copy import digest
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from tests._public_copy_oracle import TestPublicCopyOracleVerifier, oracle_packet
from tests.test_public_copy_lineage import RecordingChecks, RecordingSales, readback
from tests.test_runtime_state_stage2 import _state
from tests.test_sales_consumption_e2e import _application


def configured(tmp_path, *, verified=True):
    app = _application(tmp_path)
    store = SQLiteRuntimeStateStore(tmp_path / "oracle-edge.db")
    store.create(_state())
    app.dispatcher.runtime_state_store = store
    app.dispatcher.domains[Owner.SALES_HUMAN] = RecordingSales()
    app.dispatcher.public_copy_checks = RecordingChecks()
    if verified:
        app.dispatcher.public_copy_oracle_gate = PublicCopyOracleGate(
            verifier=TestPublicCopyOracleVerifier()
        )
    revision = app.authority.resolve().entries[Owner.SALES_HUMAN].revision
    return app.dispatcher, store, revision


def request(packet=None, **updates):
    values = {
        "request_text": "synthetic copy",
        "intent": Intent.SALES_HUMAN,
        "public_commercial_copy": True,
        "public_copy_requirement_ids": ["REQ-1"],
        "public_copy_generation_id": "generation-1",
        "public_copy_frame_id": "frame-1",
        "public_copy_oracle_input": packet,
        "runtime_state_required": True,
        "conversation_or_thread_id": "thread-a",
        "runtime_task_id": "runtime-task-a",
    }
    values.update(updates)
    return TaskRequest(**values)


@pytest.mark.parametrize(
    ("change", "blocker"),
    [
        ("missing", PUBLIC_COPY_ORACLE_INPUT_REQUIRED),
        ("stale", PUBLIC_COPY_ORACLE_INPUT_STALE),
        ("scope", PUBLIC_COPY_ORACLE_TASK_SCOPE_MISMATCH),
        ("requirements", PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID),
        ("generation", PUBLIC_COPY_ORACLE_FRAME_MISMATCH),
        ("frame", PUBLIC_COPY_ORACLE_FRAME_MISMATCH),
        ("proof_ref", PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID),
    ],
)
def test_invalid_oracle_input_blocks_before_domain(tmp_path, change, blocker):
    dispatcher, _, revision = configured(tmp_path)
    packet = oracle_packet(revision=revision)
    updates = {}
    if change == "missing":
        packet = None
    elif change == "stale":
        packet = oracle_packet(
            revision=revision, valid_until=datetime.now(UTC) - timedelta(seconds=1)
        )
    elif change == "scope":
        packet = oracle_packet(revision=revision, scope="different task")
    elif change == "requirements":
        packet = packet.model_copy(update={
            "hard_requirements": (
                PublicCopyHardRequirement(requirement_id="REQ-1", body="body A"),
                PublicCopyHardRequirement(requirement_id="REQ-1", body="body B"),
            )
        })
    elif change == "generation":
        updates["public_copy_generation_id"] = "generation-2"
    elif change == "frame":
        updates["public_copy_frame_id"] = "frame-2"
    else:
        proof = packet.supporting_proofs[0].model_copy(
            update={"evidence_refs": ("context:missing",)}
        )
        packet = packet.model_copy(update={"supporting_proofs": (proof,)})
    result = dispatcher.dispatch(request(packet, **updates))
    assert result.status == blocker
    assert dispatcher.domains[Owner.SALES_HUMAN].contracts == []


def test_lookalike_context_and_domain_self_report_cannot_supply_packet(tmp_path):
    dispatcher, _, _ = configured(tmp_path)
    lookalike = ContextItem(
        id="lookalike", origin=ContextOrigin.CURRENT_USER,
        context_class=ContextClass.STABLE_USER_PREFERENCE,
        purpose="synthetic lookalike", task_scope="synthetic copy",
        payload={"packet_id": "fake", "hard_requirements": [{"requirement_id": "REQ-1"}]},
        provenance=["synthetic:user"], current_binding=True,
    )

    class SelfReportingSales(RecordingSales):
        def run(self, contract):
            self.contracts.append(contract)
            return DomainResult(
                owner=Owner.SALES_HUMAN, status="DONE", output="candidate",
                evidence={"public_copy_oracle_input": {"packet_id": "self-asserted"}},
            )

    domain = SelfReportingSales()
    dispatcher.domains[Owner.SALES_HUMAN] = domain
    result = dispatcher.dispatch(request(None, context=[lookalike]))
    assert result.status == PUBLIC_COPY_ORACLE_INPUT_REQUIRED
    assert domain.contracts == []


def test_default_verifier_fails_closed(tmp_path):
    dispatcher, _, revision = configured(tmp_path, verified=False)
    result = dispatcher.dispatch(request(oracle_packet(revision=revision)))
    assert result.status == PUBLIC_COPY_ORACLE_INPUT_UNVERIFIED
    assert dispatcher.domains[Owner.SALES_HUMAN].contracts == []


def test_terminal_candidate_must_match_admitted_packet(tmp_path):
    dispatcher, _, revision = configured(tmp_path)
    packet = oracle_packet(revision=revision)
    packet = packet.model_copy(update={
        "terminal_candidate": packet.terminal_candidate.model_copy(update={
            "canonical_json": "{\"final_response_object\":null,\"output\":\"candidate B\"}",
            "sha256": digest({"output": "candidate B", "final_response_object": None}),
        })
    })
    result = dispatcher.dispatch(request(packet))
    assert result.output is None
    assert result.evidence["blocker_code"] == "PUBLIC_COPY_TERMINAL_CANDIDATE_MISMATCH"


def test_unadmitted_current_context_proof_ref_blocks(tmp_path):
    dispatcher, _, revision = configured(tmp_path)
    packet = oracle_packet(revision=revision)
    packet = packet.model_copy(update={
        "source_refs": packet.source_refs + (
            PublicCopySourceRef(
                ref_id="context:not-admitted", kind=PublicCopySourceKind.CURRENT_CONTEXT,
                context_id="not-admitted",
            ),
        ),
        "supporting_proofs": (
            packet.supporting_proofs[0].model_copy(
                update={"evidence_refs": ("context:not-admitted",)}
            ),
        ),
    })
    result = dispatcher.dispatch(request(packet))
    assert result.status == PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID


def test_oracle_digest_drift_between_product_stages_fails_lineage(tmp_path):
    dispatcher, store, revision = configured(tmp_path)

    class DriftTrace(TraceBus):
        def emit(self, **kwargs):
            if kwargs["stage"] == "detached_product_oracle":
                kwargs["metadata"]["oracle_input_digest"] = digest("replacement packet")
            return super().emit(**kwargs)

    dispatcher.trace = DriftTrace(ReadOnlyWitness())
    result = dispatcher.dispatch(request(oracle_packet(revision=revision)))
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
    assert not all(readback(store).values())


def test_ordinary_request_ignores_absent_oracle_edge(tmp_path):
    dispatcher, _, _ = configured(tmp_path, verified=False)
    result = dispatcher.dispatch(TaskRequest(request_text="ordinary task", intent=Intent.SALES_HUMAN))
    assert result.status == "DONE"
