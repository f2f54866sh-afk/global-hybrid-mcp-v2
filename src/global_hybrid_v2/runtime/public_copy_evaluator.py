"""Typed semantic evaluator boundary for admitted public-Copy inputs."""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from global_hybrid_v2.contracts import PublicCopyOracleInput


class PublicCopyEvaluationDecision(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class PublicCopyRequirementEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    requirement_id: str = Field(min_length=1)
    decision: PublicCopyEvaluationDecision
    exact_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublicCopyEvaluatorReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: str = Field(min_length=1)
    decision: PublicCopyEvaluationDecision
    exact_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    witness_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    hard_requirement_coverage: tuple[PublicCopyRequirementEvaluation, ...] = ()
    non_binding_literal_leak_disposition: PublicCopyEvaluationDecision | None = None
    supporting_proof_serialization_disposition: PublicCopyEvaluationDecision | None = None
    supporting_proof_refs_consumed: tuple[str, ...] = ()
    product_disposition: PublicCopyEvaluationDecision | None = None
    disposition_invariance_result: PublicCopyEvaluationDecision | None = None
    copy_egress_audit_result: PublicCopyEvaluationDecision | None = None
    unresolved_reasons: tuple[str, ...] = ()
    blocker_codes: tuple[str, ...] = ()
    evaluator_model: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    evaluator_run_id: str = Field(min_length=1)


class PublicCopyEvaluatorRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    stage: str = Field(min_length=1)
    candidate_json: str = Field(min_length=1)
    exact_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    oracle_input: PublicCopyOracleInput
    oracle_input_json: str = Field(min_length=1)
    oracle_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    requirement_ids: tuple[str, ...] = Field(min_length=1)
    witness_json: str | None = None
    witness_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    prior_receipts: tuple[PublicCopyEvaluatorReceipt, ...] = ()


class PublicCopyEvaluatorPort(Protocol):
    def evaluate(self, request: PublicCopyEvaluatorRequest) -> PublicCopyEvaluatorReceipt: ...


class PublicCopyEvaluationError(RuntimeError):
    def __init__(self, blocker: str):
        super().__init__(blocker)
        self.blocker = blocker
