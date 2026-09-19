"""Terminal Copy execution adapter; persistence belongs exclusively to TraceBus.

The port is trusted application configuration, never a field in a domain result.
It supplies executions of existing product checks, not a replacement Sales policy.
No production port is installed by default.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from global_hybrid_v2.contracts import TaskContract
    from global_hybrid_v2.runtime.trace import TraceBus

STAGES = (
    "public_copy_acceptance_witness",
    "production_product_oracle",
    "detached_product_oracle",
    "disposition_invariance",
    "copy_egress_audit",
)


def serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(serialize(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CopyCheckResult:
    decision: str
    exact_candidate_digest: str
    witness_digest: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class PublicCopyChecks(Protocol):
    def evaluate(
        self, *, stage: str, candidate_json: str, witness_json: str | None,
        requirement_ids: tuple[str, ...], oracle_input_json: str,
        oracle_input_digest: str,
    ) -> CopyCheckResult: ...


def execute_checks(
    trace: TraceBus, contract: TaskContract, candidate: Any, port: PublicCopyChecks | None,
) -> dict[str, Any]:
    if (
        contract.public_copy_oracle_input is None
        or contract.public_copy_oracle_input_digest is None
        or contract.public_copy_oracle_admission_event_id is None
    ):
        raise ValueError("PUBLIC_COPY_ORACLE_INPUT_NOT_ADMITTED")
    candidate_json = serialize(candidate)
    candidate_digest = digest(candidate)
    expected = contract.public_copy_oracle_input.terminal_candidate
    if candidate_json != expected.canonical_json or candidate_digest != expected.sha256:
        raise ValueError("PUBLIC_COPY_TERMINAL_CANDIDATE_MISMATCH")
    oracle_input_json = serialize(contract.public_copy_oracle_input.model_dump(mode="json"))
    if digest(json.loads(oracle_input_json)) != contract.public_copy_oracle_input_digest:
        raise ValueError("PUBLIC_COPY_ORACLE_INPUT_DIGEST_MISMATCH")
    base = {
        "public_commercial_copy": True,
        "exact_candidate_digest": candidate_digest,
        "oracle_input_digest": contract.public_copy_oracle_input_digest,
        "generation_id": contract.public_copy_oracle_input.generation_id,
        "frame_id": contract.public_copy_oracle_input.frame_id,
    }
    candidate_event = trace.emit(
        task_id=contract.task_id, stage="public_copy_candidate", decision="PASS",
        owner=contract.owner,
        metadata={
            **base, "candidate": candidate,
            "requirement_ids": contract.public_copy_requirement_ids,
            "input_refs": [contract.public_copy_oracle_admission_event_id],
        },
    )
    refs = [contract.public_copy_oracle_admission_event_id, candidate_event.event_id]
    witness_json = None
    witness_digest = None
    for stage in STAGES:
        try:
            if port is None:
                raise RuntimeError("PUBLIC_COPY_CHECKS_NOT_CONFIGURED")
            receipt = port.evaluate(
                stage=stage, candidate_json=candidate_json, witness_json=witness_json,
                requirement_ids=tuple(contract.public_copy_requirement_ids),
                oracle_input_json=oracle_input_json,
                oracle_input_digest=contract.public_copy_oracle_input_digest,
            )
            if not isinstance(receipt, CopyCheckResult) or not isinstance(receipt.details, dict):
                raise TypeError("PUBLIC_COPY_CHECK_RECEIPT_INVALID")
            if receipt.decision not in {"PASS", "FAIL"}:
                raise ValueError("PUBLIC_COPY_CHECK_DISPOSITION_INVALID")
            # Round-trip before emission: non-JSON proofs cannot enter the journal as PASS.
            details = json.loads(serialize(receipt.details))
            metadata = {**base, "exact_candidate_digest": receipt.exact_candidate_digest,
                        "witness_digest": receipt.witness_digest, "details": details,
                        "input_refs": list(refs)}
            decision = receipt.decision
            if stage == STAGES[0]:
                witness_json = serialize({"exact_candidate_digest": receipt.exact_candidate_digest,
                                          "details": details})
                witness_digest = digest(json.loads(witness_json))
                metadata["witness_digest"] = witness_digest
        except Exception as exc:
            decision = "FAIL"
            metadata = {**base, "witness_digest": witness_digest, "input_refs": list(refs),
                        "error": type(exc).__name__,
                        "blocker": "PUBLIC_COPY_CHECKS_NOT_CONFIGURED" if port is None
                        else "PUBLIC_COPY_CHECK_EXECUTION_FAILED"}
        event = trace.emit(task_id=contract.task_id, stage=stage, decision=decision,
                           owner=contract.owner, metadata=metadata)
        refs.append(event.event_id)
    return {**base, "witness_digest": witness_digest, "input_refs": refs}
