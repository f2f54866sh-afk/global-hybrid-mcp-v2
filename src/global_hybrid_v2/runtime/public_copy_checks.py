"""Production semantic PublicCopyChecks backed by a typed evaluator port."""
from __future__ import annotations

import json

from pydantic import ValidationError

from global_hybrid_v2.contracts import PublicCopyOracleInput
from global_hybrid_v2.runtime.public_copy import CopyCheckResult, digest
from global_hybrid_v2.runtime.public_copy_evaluator import (
    PublicCopyEvaluationDecision,
    PublicCopyEvaluationError,
    PublicCopyEvaluatorPort,
    PublicCopyEvaluatorReceipt,
    PublicCopyEvaluatorRequest,
)

PUBLIC_COPY_EVALUATOR_UNAVAILABLE = "PUBLIC_COPY_EVALUATOR_UNAVAILABLE"
PUBLIC_COPY_EVALUATOR_RECEIPT_INVALID = "PUBLIC_COPY_EVALUATOR_RECEIPT_INVALID"
PUBLIC_COPY_EVALUATOR_BINDING_MISMATCH = "PUBLIC_COPY_EVALUATOR_BINDING_MISMATCH"
PUBLIC_COPY_EVALUATOR_STAGE_INVALID = "PUBLIC_COPY_EVALUATOR_STAGE_INVALID"
PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE = "PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE"
PUBLIC_COPY_PRODUCT_DISPOSITION_MISMATCH = "PUBLIC_COPY_PRODUCT_DISPOSITION_MISMATCH"


class UnavailablePublicCopyChecks:
    def __init__(self, blocker: str = PUBLIC_COPY_EVALUATOR_UNAVAILABLE):
        self.blocker = blocker

    def evaluate(self, **kwargs) -> CopyCheckResult:
        candidate_json = kwargs.get("candidate_json", "null")
        return CopyCheckResult(
            decision="FAIL",
            exact_candidate_digest=digest(json.loads(candidate_json)),
            witness_digest=None,
            details={"blocker_codes": [self.blocker], "evaluator_availability": "UNAVAILABLE"},
        )


class ProductionPublicCopyChecks:
    def __init__(self, evaluator: PublicCopyEvaluatorPort):
        self._evaluator = evaluator

    def evaluate(
        self, *, stage: str, candidate_json: str, witness_json: str | None,
        requirement_ids: tuple[str, ...], oracle_input_json: str,
        oracle_input_digest: str, prior_stage_results_json: str = "[]",
    ) -> CopyCheckResult:
        candidate_digest = digest(json.loads(candidate_json))
        witness_digest = digest(json.loads(witness_json)) if witness_json else None
        try:
            oracle = PublicCopyOracleInput.model_validate_json(oracle_input_json)
            prior = self._prior_receipts(prior_stage_results_json)
            request = PublicCopyEvaluatorRequest(
                stage=stage,
                candidate_json=candidate_json,
                exact_candidate_digest=candidate_digest,
                oracle_input=oracle,
                oracle_input_json=oracle_input_json,
                oracle_input_digest=oracle_input_digest,
                requirement_ids=requirement_ids,
                witness_json=witness_json,
                witness_digest=witness_digest,
                prior_receipts=prior,
            )
            receipt = self._evaluator.evaluate(request)
            blocker = self._validate_receipt(request, receipt)
        except PublicCopyEvaluationError as exc:
            return self._failure(candidate_digest, witness_digest, exc.blocker)
        except (TypeError, ValueError, ValidationError, json.JSONDecodeError):
            return self._failure(
                candidate_digest, witness_digest, PUBLIC_COPY_EVALUATOR_RECEIPT_INVALID
            )
        if blocker:
            return self._failure(candidate_digest, witness_digest, blocker, receipt=receipt)
        return CopyCheckResult(
            decision=receipt.decision.value,
            exact_candidate_digest=receipt.exact_candidate_digest,
            witness_digest=receipt.witness_digest,
            details=self._details(receipt),
        )

    @staticmethod
    def _prior_receipts(value: str) -> tuple[PublicCopyEvaluatorReceipt, ...]:
        raw = json.loads(value)
        if not isinstance(raw, list):
            raise ValueError("prior stage results must be a list")
        receipts = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("prior stage result must be an object")
            details = item.get("details")
            if not isinstance(details, dict) or "evaluator_receipt" not in details:
                continue
            receipts.append(PublicCopyEvaluatorReceipt.model_validate(details["evaluator_receipt"]))
        return tuple(receipts)

    @classmethod
    def _validate_receipt(
        cls, request: PublicCopyEvaluatorRequest, receipt: PublicCopyEvaluatorReceipt,
    ) -> str | None:
        if receipt.stage != request.stage:
            return PUBLIC_COPY_EVALUATOR_STAGE_INVALID
        if (
            receipt.exact_candidate_digest != request.exact_candidate_digest
            or receipt.oracle_input_digest != request.oracle_input_digest
            or receipt.witness_digest != request.witness_digest
        ):
            return PUBLIC_COPY_EVALUATOR_BINDING_MISMATCH
        if receipt.decision is PublicCopyEvaluationDecision.PASS and (
            receipt.unresolved_reasons or receipt.blocker_codes
        ):
            return PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE
        if receipt.decision is PublicCopyEvaluationDecision.FAIL and not (
            receipt.unresolved_reasons or receipt.blocker_codes
        ):
            return PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE

        if request.stage == "public_copy_acceptance_witness":
            if receipt.decision is PublicCopyEvaluationDecision.FAIL:
                return None
            coverage = {item.requirement_id: item for item in receipt.hard_requirement_coverage}
            if (
                len(coverage) != len(receipt.hard_requirement_coverage)
                or set(coverage) != set(request.requirement_ids)
                or any(
                    item.decision is not PublicCopyEvaluationDecision.PASS
                    or item.exact_candidate_digest != request.exact_candidate_digest
                    for item in coverage.values()
                )
                or receipt.non_binding_literal_leak_disposition
                is not PublicCopyEvaluationDecision.PASS
                or receipt.supporting_proof_serialization_disposition
                is not PublicCopyEvaluationDecision.PASS
                or set(receipt.supporting_proof_refs_consumed)
                != {item.proof_id for item in request.oracle_input.supporting_proofs}
            ):
                return PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE
        elif request.stage in {"production_product_oracle", "detached_product_oracle"}:
            if receipt.product_disposition is not receipt.decision:
                return PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE
        elif request.stage == "disposition_invariance":
            by_stage = {item.stage: item for item in request.prior_receipts}
            production = by_stage.get("production_product_oracle")
            detached = by_stage.get("detached_product_oracle")
            consistent = (
                production is not None
                and detached is not None
                and production.decision is detached.decision
                and production.product_disposition is detached.product_disposition
            )
            if (
                not consistent
                or receipt.disposition_invariance_result is not PublicCopyEvaluationDecision.PASS
                or receipt.decision is not PublicCopyEvaluationDecision.PASS
            ):
                return PUBLIC_COPY_PRODUCT_DISPOSITION_MISMATCH
        elif request.stage == "copy_egress_audit":
            if (
                receipt.copy_egress_audit_result is not PublicCopyEvaluationDecision.PASS
                or receipt.decision is not PublicCopyEvaluationDecision.PASS
            ):
                return PUBLIC_COPY_EVALUATOR_SEMANTIC_INCOMPLETE
        else:
            return PUBLIC_COPY_EVALUATOR_STAGE_INVALID
        return None

    @staticmethod
    def _details(receipt: PublicCopyEvaluatorReceipt) -> dict:
        coverage = {
            item.requirement_id: {
                "decision": item.decision.value,
                "exact_candidate_digest": item.exact_candidate_digest,
            }
            for item in receipt.hard_requirement_coverage
        }
        details = {
            "evaluator_receipt": receipt.model_dump(mode="json"),
            "unresolved_reasons": list(receipt.unresolved_reasons),
            "blocker_codes": list(receipt.blocker_codes),
        }
        if receipt.stage == "public_copy_acceptance_witness":
            details.update({
                "public_copy_acceptance_witness": receipt.decision.value,
                "hard_requirement_coverage": coverage,
                "non_binding_literal_leak_check": (
                    receipt.non_binding_literal_leak_disposition.value
                    if receipt.non_binding_literal_leak_disposition else "FAIL"
                ),
                "supporting_proof_serialization": (
                    receipt.supporting_proof_serialization_disposition.value
                    if receipt.supporting_proof_serialization_disposition else "FAIL"
                ),
                "supporting_proof": {
                    "consumed_refs": list(receipt.supporting_proof_refs_consumed),
                    "evaluator_run_id": receipt.evaluator_run_id,
                },
            })
        elif receipt.stage == "disposition_invariance":
            details["disposition_invariance"] = (
                receipt.disposition_invariance_result.value
                if receipt.disposition_invariance_result else "FAIL"
            )
        elif receipt.stage == "copy_egress_audit":
            details["copy_egress_audit"] = (
                receipt.copy_egress_audit_result.value
                if receipt.copy_egress_audit_result else "FAIL"
            )
        return details

    @classmethod
    def _failure(
        cls, candidate_digest: str, witness_digest: str | None, blocker: str,
        *, receipt: PublicCopyEvaluatorReceipt | None = None,
    ) -> CopyCheckResult:
        details = {
            "blocker_codes": [blocker],
            "unresolved_reasons": [],
        }
        if receipt is not None:
            details["evaluator_receipt"] = receipt.model_dump(mode="json")
        return CopyCheckResult(
            decision="FAIL",
            exact_candidate_digest=candidate_digest,
            witness_digest=witness_digest,
            details=details,
        )
