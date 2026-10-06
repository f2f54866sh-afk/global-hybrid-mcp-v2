from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from global_hybrid_v2.governance.public_claim_coverage import (
    ClaimCoveragePayloadV1,
    TaskBoundEvidenceManifestV1,
    evaluate_claim_coverage,
)
from global_hybrid_v2.governance.sales_final_commit import (
    AuthoritativeSalesTaskSnapshotV1,
    Disposition,
    ProductCheckResultV1,
    sha256_json,
    sha256_text,
)

OPENAI_SALES_REQUEST_FAILED = "OPENAI_SALES_REQUEST_FAILED"
OPENAI_SALES_RESPONSE_INCOMPLETE = "OPENAI_SALES_RESPONSE_INCOMPLETE"
OPENAI_SALES_OUTPUT_INVALID = "OPENAI_SALES_OUTPUT_INVALID"
OPENAI_SALES_BINDING_MISMATCH = "OPENAI_SALES_BINDING_MISMATCH"
OPENAI_SALES_CANDIDATE_EMPTY = "OPENAI_SALES_CANDIDATE_EMPTY"

_EvaluatorRole = Literal["production", "detached"]


class OpenAISalesAdapterError(RuntimeError):
    def __init__(self, blocker: str):
        super().__init__(blocker)
        self.blocker = blocker


class _EvaluationPayload(BaseModel):
    snapshot_digest: str = Field(min_length=64, max_length=64)
    candidate_digest: str = Field(min_length=64, max_length=64)
    disposition: Disposition
    reason_codes: list[str] = Field(default_factory=list)
    claim_coverage: ClaimCoveragePayloadV1

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class _EvaluationResult:
    disposition: Disposition
    result_ref: str
    binding_ok: bool
    claim_coverage: ClaimCoveragePayloadV1 | None


def _default_client(api_key: SecretStr) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=api_key.get_secret_value())


def _field(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


class OpenAISalesCandidateGenerator:
    def __init__(
        self,
        *,
        model: str,
        api_key: SecretStr,
        instructions: str,
        client: Any | None = None,
    ) -> None:
        configured_model = model.strip()
        secret = api_key.get_secret_value().strip()
        configured_instructions = instructions.strip()
        if not configured_model:
            raise ValueError("OpenAI Sales candidate model is not configured")
        if not secret:
            raise ValueError("OpenAI API key is not configured")
        if not configured_instructions:
            raise ValueError("OpenAI Sales candidate instructions are not configured")
        self._model = configured_model
        self._instructions = configured_instructions
        self._client = client if client is not None else _default_client(api_key)

    def generate(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> str:
        prompt = {
            "purpose": "GENERATE_EXACT_PUBLIC_SALES_COPY_CANDIDATE",
            "policy_ref": snapshot.sales_execution_policy_ref,
            "instructions": self._instructions,
            "task": {
                "task_class": snapshot.task_class,
                "target_surface": snapshot.target_surface,
                "current_user_request": snapshot.current_user_request,
                "direct_user_hard_requirements": snapshot.direct_user_hard_requirements,
                "vehicle_instance_id": snapshot.vehicle_instance_id,
                "evidence_refs": snapshot.evidence_refs,
            },
            "constraints": [
                "Return only the exact public-copy candidate.",
                "Do not return audit labels, PASS/FAIL claims, receipts, or markdown fences.",
                "Do not invent facts not supported by the supplied task contract.",
            ],
        }
        try:
            response = self._client.responses.create(
                model=self._model,
                input=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception as exc:
            raise OpenAISalesAdapterError(OPENAI_SALES_REQUEST_FAILED) from exc
        if _field(response, "status") != "completed":
            raise OpenAISalesAdapterError(OPENAI_SALES_RESPONSE_INCOMPLETE)
        output_text = _field(response, "output_text")
        if not isinstance(output_text, str):
            raise OpenAISalesAdapterError(OPENAI_SALES_OUTPUT_INVALID)
        if not output_text.strip():
            raise OpenAISalesAdapterError(OPENAI_SALES_CANDIDATE_EMPTY)
        return output_text


class OpenAISalesProductEvaluator:
    """N1C dual evaluator plus app-owned closed-world public-claim coverage."""

    def __init__(
        self,
        *,
        production_model: str,
        detached_model: str,
        api_key: SecretStr,
        production_instructions: str,
        detached_instructions: str,
        client: Any | None = None,
    ) -> None:
        production_model = production_model.strip()
        detached_model = detached_model.strip()
        secret = api_key.get_secret_value().strip()
        production_instructions = production_instructions.strip()
        detached_instructions = detached_instructions.strip()
        if not production_model or not detached_model:
            raise ValueError("OpenAI Sales evaluator models are not configured")
        if not secret:
            raise ValueError("OpenAI API key is not configured")
        if not production_instructions or not detached_instructions:
            raise ValueError("OpenAI Sales evaluator instructions are not configured")
        self._production_model = production_model
        self._detached_model = detached_model
        self._production_instructions = production_instructions
        self._detached_instructions = detached_instructions
        self._client = client if client is not None else _default_client(api_key)

    def evaluate(
        self,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
    ) -> list[ProductCheckResultV1]:
        candidate_digest = sha256_text(candidate)
        manifest = snapshot.task_bound_evidence_manifest
        production = self._evaluate_one(
            role="production",
            model=self._production_model,
            instructions=self._production_instructions,
            snapshot=snapshot,
            candidate=candidate,
            candidate_digest=candidate_digest,
            manifest=manifest,
        )
        detached = self._evaluate_one(
            role="detached",
            model=self._detached_model,
            instructions=self._detached_instructions,
            snapshot=snapshot,
            candidate=candidate,
            candidate_digest=candidate_digest,
            manifest=None,
        )

        context_isolation: Disposition = "PASS" if detached.binding_ok else "HOLD"
        if production.disposition == "HOLD" or detached.disposition == "HOLD":
            invariance: Disposition = "HOLD"
        elif production.disposition == detached.disposition:
            invariance = "PASS"
        else:
            invariance = "FAIL"

        copy_egress: Disposition = (
            "PASS" if production.binding_ok and detached.binding_ok else "HOLD"
        )
        serialization: Disposition = (
            "PASS" if candidate.encode("utf-8").decode("utf-8") == candidate else "HOLD"
        )
        claim_coverage = evaluate_claim_coverage(
            candidate=candidate,
            manifest=manifest,
            production=production.claim_coverage,
            detached=detached.claim_coverage,
        )
        claim_disposition: Disposition = claim_coverage.disposition
        witness = self._witness_disposition(
            production.disposition,
            detached.disposition,
            invariance,
            claim_disposition,
        )

        refs = {
            "PRODUCTION_PRODUCT": production.result_ref,
            "DETACHED_PRODUCT": detached.result_ref,
            "CONTEXT_ISOLATION": f"app:context-isolation:{sha256_text(detached.result_ref)}",
            "DISPOSITION_INVARIANCE": "app:invariance:"
            + sha256_json(
                {
                    "production": production.disposition,
                    "detached": detached.disposition,
                    "production_ref": production.result_ref,
                    "detached_ref": detached.result_ref,
                }
            ),
            "COPY_EGRESS": f"app:copy-egress:{candidate_digest}",
            "PUBLIC_SERIALIZATION": f"app:serialization:{candidate_digest}",
            "PUBLIC_CLAIM_COVERAGE": f"app:claim-coverage:{claim_coverage.coverage_digest}",
            "PUBLIC_ACCEPTANCE_WITNESS": "app:witness:"
            + sha256_json(
                {
                    "production": production.disposition,
                    "detached": detached.disposition,
                    "invariance": invariance,
                    "claim_coverage": claim_disposition,
                    "candidate_digest": candidate_digest,
                }
            ),
        }
        dispositions: dict[str, Disposition] = {
            "PRODUCTION_PRODUCT": production.disposition,
            "DETACHED_PRODUCT": detached.disposition,
            "CONTEXT_ISOLATION": context_isolation,
            "DISPOSITION_INVARIANCE": invariance,
            "COPY_EGRESS": copy_egress,
            "PUBLIC_SERIALIZATION": serialization,
            "PUBLIC_CLAIM_COVERAGE": claim_disposition,
            "PUBLIC_ACCEPTANCE_WITNESS": witness,
        }
        return [
            ProductCheckResultV1(
                check_id=check_id,
                disposition=dispositions[check_id],
                result_ref=refs[check_id],
                snapshot_digest=snapshot.snapshot_digest,
                candidate_digest=candidate_digest,
            )
            for check_id in dispositions
        ]

    def _evaluate_one(
        self,
        *,
        role: _EvaluatorRole,
        model: str,
        instructions: str,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
        candidate_digest: str,
        manifest: TaskBoundEvidenceManifestV1 | None,
    ) -> _EvaluationResult:
        prompt = self._evaluation_prompt(
            role=role,
            instructions=instructions,
            snapshot=snapshot,
            candidate=candidate,
            candidate_digest=candidate_digest,
            manifest=manifest,
        )
        try:
            response = self._client.responses.create(
                model=model,
                input=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception as exc:
            return self._hold_result(role, OPENAI_SALES_REQUEST_FAILED, type(exc).__name__)
        response_id = _field(response, "id")
        result_ref = f"openai:{role}:{response_id}" if response_id else f"openai:{role}:missing-id"
        if _field(response, "status") != "completed":
            return self._hold_result(role, OPENAI_SALES_RESPONSE_INCOMPLETE, result_ref)
        output_text = _field(response, "output_text")
        if not isinstance(output_text, str):
            return self._hold_result(role, OPENAI_SALES_OUTPUT_INVALID, result_ref)
        try:
            payload = _EvaluationPayload.model_validate_json(output_text)
        except ValidationError:
            return self._hold_result(role, OPENAI_SALES_OUTPUT_INVALID, result_ref)
        if (
            payload.snapshot_digest != snapshot.snapshot_digest
            or payload.candidate_digest != candidate_digest
        ):
            return self._hold_result(role, OPENAI_SALES_BINDING_MISMATCH, result_ref)
        return _EvaluationResult(
            disposition=payload.disposition,
            result_ref=result_ref,
            binding_ok=True,
            claim_coverage=payload.claim_coverage,
        )

    @staticmethod
    def _evaluation_prompt(
        *,
        role: _EvaluatorRole,
        instructions: str,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
        candidate_digest: str,
        manifest: TaskBoundEvidenceManifestV1 | None,
    ) -> dict[str, Any]:
        task = {
            "task_class": snapshot.task_class,
            "target_surface": snapshot.target_surface,
            "current_user_request": snapshot.current_user_request,
            "direct_user_hard_requirements": snapshot.direct_user_hard_requirements,
            "vehicle_instance_id": snapshot.vehicle_instance_id,
        }
        claim_constraints = [
            "Claim coverage must cover every alphanumeric or CJK character in the exact candidate.",
            "Each coverage segment must use exact start/end offsets and exact candidate text.",
            "Classify materially testable assertions as FACTUAL and style/opinion only as NON_FACTUAL.",
        ]
        if role == "production":
            task["evidence_refs"] = snapshot.evidence_refs
            task["task_bound_evidence_manifest"] = (
                None if manifest is None else manifest.model_dump(mode="json")
            )
            claim_constraints.extend(
                [
                    "Each FACTUAL segment must be one atomic claim bound to exactly one manifest fact.",
                    "Split year and model into separate hidden segments without changing public Copy.",
                    "FACTUAL text must match a public_safe_form of that exact fact after NFC and "
                    "whitespace normalization. The application verifies this match.",
                    "support is diagnostic only and cannot grant authority or override application checks.",
                    "authority_fact_ids may name only fact_id values present in the supplied manifest.",
                    "For NON_FACTUAL segments use support NOT_APPLICABLE and no authority_fact_ids.",
                ]
            )
        else:
            claim_constraints.extend(
                [
                    "Do not infer support or inspect production evidence.",
                    "For FACTUAL segments use support null and no authority_fact_ids.",
                    "For NON_FACTUAL segments use support NOT_APPLICABLE and no authority_fact_ids.",
                    "claim_coverage.manifest_digest must be null.",
                ]
            )
        return {
            "purpose": f"{role.upper()}_PRODUCT_EVALUATION_ONLY",
            "policy_ref": snapshot.sales_execution_policy_ref,
            "instructions": instructions,
            "snapshot_digest": snapshot.snapshot_digest,
            "candidate_digest": candidate_digest,
            "task": task,
            "candidate": candidate,
            "constraints": [
                "Return JSON only.",
                "Do not return or decide FINAL_OUTPUT_COMMIT.",
                "Do not invent evidence, authority, receipts, or result references.",
                "Disposition must be PASS, FAIL, or HOLD.",
                *claim_constraints,
            ],
            "response_schema": {
                "snapshot_digest": "exact supplied snapshot_digest",
                "candidate_digest": "exact supplied candidate_digest",
                "disposition": "PASS | FAIL | HOLD",
                "reason_codes": ["bounded machine-readable reason codes"],
                "claim_coverage": {
                    "manifest_digest": (
                        "exact supplied manifest digest for production; null for detached"
                    ),
                    "segments": [
                        {
                            "start": "0-based candidate start offset",
                            "end": "0-based exclusive candidate end offset",
                            "text": "exact candidate substring",
                            "kind": "FACTUAL | NON_FACTUAL",
                            "authority_fact_ids": ["manifest fact_id values or empty list"],
                            "support": "SUPPORTED | UNSUPPORTED | AMBIGUOUS | NOT_APPLICABLE | null",
                        }
                    ],
                },
            },
        }

    @staticmethod
    def _hold_result(role: _EvaluatorRole, blocker: str, detail: str) -> _EvaluationResult:
        return _EvaluationResult(
            disposition="HOLD",
            result_ref=f"app:{role}-hold:{blocker}:{sha256_text(detail)}",
            binding_ok=False,
            claim_coverage=None,
        )

    @staticmethod
    def _witness_disposition(*values: Disposition) -> Disposition:
        if "FAIL" in values:
            return "FAIL"
        if "HOLD" in values:
            return "HOLD"
        return "PASS"
