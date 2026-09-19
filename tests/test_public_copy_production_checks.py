"""Semantic adapter tests use a fake Responses client and synthetic Sales output only."""
from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import SecretStr

from global_hybrid_v2.adapters.openai_public_copy import (
    OpenAIPublicCopyEvaluator,
    configured_public_copy_checks,
)
from global_hybrid_v2.contracts import DomainResult, Intent, Owner, TaskRequest
from global_hybrid_v2.runtime.public_copy import STAGES, digest, serialize
from global_hybrid_v2.runtime.public_copy_checks import (
    ProductionPublicCopyChecks,
    UnavailablePublicCopyChecks,
)
from global_hybrid_v2.settings import Settings
from tests._public_copy_oracle import oracle_packet
from tests.test_public_copy_lineage import readback, setup


class _SemanticSales:
    def __init__(self, output: str, *, self_report_pass: bool = False):
        self.output = output
        self.self_report_pass = self_report_pass

    def run(self, contract):
        evidence = {"PUBLIC_COPY_ACCEPTANCE_WITNESS": "PASS"} if self.self_report_pass else {}
        return DomainResult(owner=contract.owner, status="DONE", output=self.output, evidence=evidence)


class _ScriptedResponses:
    def __init__(self, mode: str = "pass"):
        self.mode = mode
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.mode == "exception":
            raise TimeoutError("synthetic timeout")
        bounded = json.loads(kwargs["input"])
        stage = bounded["stage"]
        if self.mode == "malformed":
            return {"id": "run-malformed", "model": kwargs["model"],
                    "status": "completed", "output_text": "free-form prose"}
        if self.mode == "incomplete":
            return {"id": "run-incomplete", "model": kwargs["model"],
                    "status": "incomplete", "output_text": ""}
        candidate_digest = bounded["exact_candidate_digest"]
        oracle_digest = bounded["oracle_input_digest"]
        witness_digest = bounded["witness_digest"]
        decision = "PASS"
        blockers: list[str] = []
        unresolved: list[str] = []
        coverage = []
        literal = None
        proof = None
        consumed: list[str] = []
        product = None
        invariance = None
        audit = None
        if stage == "public_copy_acceptance_witness":
            coverage = [
                {"requirement_id": requirement_id, "decision": "PASS",
                 "exact_candidate_digest": candidate_digest}
                for requirement_id in bounded["requirement_ids"]
            ]
            literal = proof = "PASS"
            consumed = [
                item["proof_id"] for item in bounded["oracle_input"]["supporting_proofs"]
            ]
            if self.mode.startswith("acceptance_fail:"):
                decision = "FAIL"
                blocker = self.mode.split(":", 1)[1]
                blockers = [blocker]
                unresolved = [blocker]
                coverage = []
                literal = proof = "FAIL"
                consumed = []
        elif stage in {"production_product_oracle", "detached_product_oracle"}:
            product = "PASS"
            if self.mode == "detached_fail" and stage == "detached_product_oracle":
                decision = product = "FAIL"
                blockers = ["DETACHED_PRODUCT_REJECTED"]
        elif stage == "disposition_invariance":
            invariance = "PASS"
        elif stage == "copy_egress_audit":
            audit = "PASS"

        payload = {
            "stage": "wrong_stage" if self.mode == "wrong_stage" else stage,
            "decision": decision,
            "exact_candidate_digest": (
                digest("wrong candidate") if self.mode == "wrong_candidate_digest"
                else candidate_digest
            ),
            "oracle_input_digest": (
                digest("wrong oracle") if self.mode == "wrong_oracle_digest" else oracle_digest
            ),
            "witness_digest": witness_digest,
            "hard_requirement_coverage": coverage,
            "non_binding_literal_leak_disposition": literal,
            "supporting_proof_serialization_disposition": proof,
            "supporting_proof_refs_consumed": consumed,
            "product_disposition": product,
            "disposition_invariance_result": invariance,
            "copy_egress_audit_result": audit,
            "unresolved_reasons": unresolved,
            "blocker_codes": blockers,
        }
        return {
            "id": f"run-{len(self.calls)}-{stage}",
            "model": kwargs["model"],
            "status": "completed",
            "output_text": json.dumps(payload),
        }


class _FakeClient:
    def __init__(self, mode="pass"):
        self.responses = _ScriptedResponses(mode)


def _checks(mode="pass"):
    client = _FakeClient(mode)
    evaluator = OpenAIPublicCopyEvaluator(
        model="gpt-production-test", detached_model="gpt-detached-test",
        api_key=SecretStr("sk-synthetic"), client=client,
    )
    return ProductionPublicCopyChecks(evaluator), client


def _run(tmp_path, *, mode="pass", output="synthetic candidate A", self_report_pass=False,
         unavailable=False):
    checks, client = _checks(mode)
    if unavailable:
        checks = UnavailablePublicCopyChecks()
    dispatcher, store = setup(tmp_path, port=checks)
    dispatcher.domains[Owner.SALES_HUMAN] = _SemanticSales(
        output, self_report_pass=self_report_pass
    )
    revision = dispatcher.authority.resolve().entries[Owner.SALES_HUMAN].revision
    packet = oracle_packet(revision=revision)
    candidate = {"output": output, "final_response_object": None}
    packet = packet.model_copy(update={
        "terminal_candidate": packet.terminal_candidate.model_copy(update={
            "canonical_json": serialize(candidate), "sha256": digest(candidate),
        })
    })
    result = dispatcher.dispatch(TaskRequest(
        request_text="synthetic copy", intent=Intent.SALES_HUMAN,
        public_commercial_copy=True, public_copy_requirement_ids=["REQ-1"],
        public_copy_generation_id="generation-1", public_copy_frame_id="frame-1",
        public_copy_oracle_input=packet, runtime_state_required=True,
        conversation_or_thread_id="thread-a", runtime_task_id="runtime-task-a",
    ))
    return result, store, client


def test_compliant_candidate_passes_five_separate_evaluations_and_durable_readback(tmp_path):
    result, store, client = _run(tmp_path)
    assert result.status == "DONE"
    assert result.evidence["public_copy_execution_lineage"] == "PASS"
    assert all(readback(store).values())
    calls = client.responses.calls
    assert [json.loads(call["input"])["stage"] for call in calls] == list(STAGES)
    assert len({json.loads(call["input"])["oracle_input_digest"] for call in calls}) == 1
    production = calls[1]
    detached = calls[2]
    assert production["model"] == "gpt-production-test"
    assert detached["model"] == "gpt-detached-test"
    assert production["input"] != detached["input"]
    trace_rows = [row for row in store.journal("thread-a", "runtime-task-a")
                  if row["stage"] in STAGES]
    assert len(trace_rows) == 5
    assert all(row["payload"]["metadata"]["details"]["evaluator_receipt"]["evaluator_run_id"]
               for row in trace_rows)


@pytest.mark.parametrize(
    ("output", "blocker"),
    [
        ("candidate missing requirement", "HARD_REQUIREMENT_MISSING"),
        ("calibration only", "NON_BINDING_LITERAL_LEAK"),
        ("generic brand value", "SUPPORTING_PROOF_GENERIC_ONLY"),
        ("candidate omits proof", "SUPPORTING_PROOF_NOT_SERIALIZED"),
        ("unsupported public claim", "UNSUPPORTED_CLAIM"),
    ],
)
def test_semantic_acceptance_failures_suppress_public_output(tmp_path, output, blocker):
    result, store, _ = _run(tmp_path, mode=f"acceptance_fail:{blocker}", output=output)
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
    assert not all(readback(store).values())


def test_production_and_detached_disagreement_fails_invariance(tmp_path):
    result, store, _ = _run(tmp_path, mode="detached_fail")
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
    assert not all(readback(store).values())


@pytest.mark.parametrize(
    "mode",
    [
        "wrong_candidate_digest", "wrong_oracle_digest", "wrong_stage",
        "malformed", "incomplete", "exception",
    ],
)
def test_invalid_or_unavailable_evaluator_output_fails_closed(tmp_path, mode):
    result, store, _ = _run(tmp_path, mode=mode)
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
    assert not all(readback(store).values())


def test_unavailable_evaluator_and_domain_self_report_cannot_pass(tmp_path):
    result, store, _ = _run(tmp_path, unavailable=True, self_report_pass=True)
    assert result.output is None
    assert result.evidence["public_copy_execution_lineage"] == "FAIL"
    assert not all(readback(store).values())


def test_production_configuration_defaults_to_explicit_unavailable_adapter():
    configured = configured_public_copy_checks(Settings())
    assert isinstance(configured, UnavailablePublicCopyChecks)
    assert "disabled" in configured.blocker
