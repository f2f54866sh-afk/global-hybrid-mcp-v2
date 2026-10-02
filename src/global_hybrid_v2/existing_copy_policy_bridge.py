"""Bounded incumbent policy adapter for the Stage 1 guard port, not a semantic evaluator.

Hard-gate PASS is internal evidence only. Semantic debt always withholds public Copy.
No network, rewrite execution, additional persistence, or policy-authority promotion.
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, ConfigDict

from global_hybrid_v2.public_copy_finalizer import (
    AppOwnedPublicCopySnapshot,
    GuardCheck,
    GuardDecision,
    PublicCopyCandidate,
    PublicCopyGuardReceipt,
    SnapshotState,
    sha256_json,
)

SEMANTIC_DEBT = (
    "NATIVE_TAIWAN_SELLER_VOICE",
    "FREE_FORM_FACTUAL_ENTAILMENT",
    "PARAPHRASED_GENERICITY",
    "SUBJECTIVE_SELLER_NARRATION",
    "CURRENT_SALES_AUTHORITY_VERIFICATION",
    "CONTEXTUAL_LITERAL_PARAPHRASE_AND_NEGATION",
    "SEMANTIC_SUPPORTING_POINT_SEGMENTATION",
)
CONSULTANT_PATTERNS = ("建議你", "建議您", "銷售策略", "賣點定位", "目標客群", "作為AI", "文案策略")
V94_FILLER_PATTERNS = ("很有誠意", "性能氣勢", "都有內容", "值得直接看實車")
PROVENANCE_PATTERNS = ("internal_only_unknowns", "verified_public_facts", "provenance", "來源待查")


def literal(value: str) -> str:
    """NFKC and whitespace/case folding only; never claims semantic equivalence."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def contains(text: str, value: str) -> bool:
    return bool(literal(value)) and literal(value) in literal(text)


def state_digest(snapshot: AppOwnedPublicCopySnapshot) -> str:
    return sha256_json({
        "task_handle": snapshot.task_handle,
        "snapshot_digest": snapshot.snapshot_digest,
        "state": snapshot.state,
        "confirmed_at": snapshot.confirmed_at.isoformat() if snapshot.confirmed_at else None,
    })


def same_state_rewrite_allowed(
    *, attempt: int, previous_state_digest: str, current_state_digest: str,
) -> bool:
    """Interface rule only; caller cannot obtain a rewrite or semantic PASS here."""
    return attempt == 1 and previous_state_digest == current_state_digest


class AcceptanceWitness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract: str = "PUBLIC_COPY_ACCEPTANCE_WITNESS_V1"
    candidate_digest: str
    snapshot_digest: str
    current_state_digest: str
    hard_gate_blockers: tuple[str, ...]
    consumed_proof_refs: tuple[str, ...]
    capability_debt: tuple[str, ...] = SEMANTIC_DEBT


class CopyEgressAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contract: str = "COPY_EGRESS_AUDIT_V2"
    candidate_digest: str
    snapshot_digest: str
    current_state_digest: str
    witness_digest: str
    hard_gate_blockers: tuple[str, ...]
    capability_debt: tuple[str, ...] = SEMANTIC_DEBT


def acceptance_witness(
    snapshot: AppOwnedPublicCopySnapshot, candidate: PublicCopyCandidate, candidate_digest: str,
) -> AcceptanceWitness:
    data = snapshot.snapshot
    policy = data.existing_copy_policy
    values = tuple(field.value for field in candidate.fields)
    text = "\n".join(values)
    blockers: list[str] = []

    def block(code: str, condition: bool) -> None:
        if condition:
            blockers.append(code)

    block("UNCONFIRMED_SNAPSHOT", snapshot.state is not SnapshotState.CONFIRMED)
    block("SNAPSHOT_DIGEST_MISMATCH", sha256_json(data) != snapshot.snapshot_digest)
    block("CANDIDATE_DIGEST_MISMATCH", sha256_json(candidate) != candidate_digest)
    block("REQUESTED_FIELD_SHAPE_MISMATCH", tuple(f.label for f in candidate.fields) != data.requested_fields)
    block("STRUCTURED_FIELD_REPLAY", any(contains(text, item)
                                       for item in data.structured_fields_already_exposed))
    block("ACTIVE_EXCLUSION", any(contains(text, item) for item in data.active_exclusions))
    block("INTERNAL_UNKNOWN_LEAK", any(contains(text, item) for item in data.internal_only_unknowns))
    block("PROVENANCE_LEAK", any(contains(text, item) for item in PROVENANCE_PATTERNS))
    block("REQUIRED_DISCLOSURE_MISSING", any(not contains(text, item)
                                           for item in data.required_material_disclosures))
    block("KNOWN_CONSULTANT_PROSE", any(contains(text, item) for item in CONSULTANT_PATTERNS))
    block("V94_PORTABLE_FILLER", any(contains(text, item) for item in V94_FILLER_PATTERNS))
    # Literal-only inventory catches known feature soup; arbitrary new claims remain debt.
    used_facts = sum(contains(text, fact) for fact in data.verified_public_facts)
    block("MAX_SUPPORTING_POINTS", used_facts > data.max_supporting_points)
    consumed: tuple[str, ...] = ()
    block("EXISTING_COPY_POLICY_MISSING", policy is None)
    if policy is not None:
        block("SURFACE_BOUNDS_SHAPE", len(policy.field_max_chars) != len(values)
              or len(policy.field_max_lines) != len(values))
        block("SURFACE_LENGTH", any(len(value) > bound
                                    for value, bound in zip(values, policy.field_max_chars, strict=False)))
        block("SURFACE_HIERARCHY", any(len(value.splitlines()) > bound
                                       for value, bound in zip(values, policy.field_max_lines, strict=False)))
        block("PRIMARY_REASON_MISSING", not values or not contains(values[0], policy.primary_reason_literal))
        block("LITERAL_REQUIREMENT_MISSING", any(not contains(text, item)
                                                for item in policy.required_literals))
        consumed = tuple(proof.proof_id for proof in policy.supporting_proofs
                         if contains(text, proof.claim) and contains(text, proof.proof_payload))
        full_body = data.copy_scope != "PARTIAL_8891_FIELD_REQUEST"
        block("SUPPORTING_PROOF_NOT_SERIALIZED", full_body and
              (not policy.supporting_proofs or len(consumed) != len(policy.supporting_proofs)))
        block("MAX_SUPPORTING_POINTS", len(consumed) > data.max_supporting_points)
    return AcceptanceWitness(
        candidate_digest=sha256_json(candidate), snapshot_digest=snapshot.snapshot_digest,
        current_state_digest=state_digest(snapshot), hard_gate_blockers=tuple(dict.fromkeys(blockers)),
        consumed_proof_refs=consumed,
    )


def copy_egress_audit(
    snapshot: AppOwnedPublicCopySnapshot, candidate: PublicCopyCandidate,
    witness: AcceptanceWitness, witness_digest: str,
) -> CopyEgressAudit:
    # Re-execute hard gates on the exact current candidate/state, not a prior PASS flag.
    expected = acceptance_witness(snapshot, candidate, sha256_json(candidate))
    blockers = list(expected.hard_gate_blockers)
    if witness != expected or witness_digest != sha256_json(witness):
        blockers.append("WITNESS_BINDING_MISMATCH")
    return CopyEgressAudit(
        candidate_digest=sha256_json(candidate), snapshot_digest=snapshot.snapshot_digest,
        current_state_digest=state_digest(snapshot), witness_digest=sha256_json(witness),
        hard_gate_blockers=tuple(dict.fromkeys(blockers)),
    )


def commit_fence(
    snapshot: AppOwnedPublicCopySnapshot, candidate: PublicCopyCandidate,
    witness: AcceptanceWitness, audit: CopyEgressAudit,
) -> tuple[str, ...]:
    expected = copy_egress_audit(snapshot, candidate, witness, sha256_json(witness))
    blockers = list(expected.hard_gate_blockers)
    if audit != expected:
        blockers.append("COMMIT_FENCE_BINDING_MISMATCH")
    return tuple(dict.fromkeys(blockers))


class ExistingCopyPolicyBridge:
    """Implements the existing Stage 1 PublicCopyGuard protocol without any model calls."""

    def evaluate(self, *, snapshot, candidate, candidate_digest) -> PublicCopyGuardReceipt:
        witness = acceptance_witness(snapshot, candidate, candidate_digest)
        audit = copy_egress_audit(snapshot, candidate, witness, sha256_json(witness))
        blockers = commit_fence(snapshot, candidate, witness, audit)
        hard_pass = not blockers
        return PublicCopyGuardReceipt(
            decision=GuardDecision.FAIL, candidate_digest=sha256_json(candidate),
            snapshot_digest=snapshot.snapshot_digest,
            requested_field_shape=GuardCheck.FAIL if "REQUESTED_FIELD_SHAPE_MISMATCH" in blockers
            else GuardCheck.PASS,
            claim_safety=GuardCheck.FAIL, native_seller_voice=GuardCheck.FAIL,
            internal_unknown_suppression=GuardCheck.FAIL if "INTERNAL_UNKNOWN_LEAK" in blockers
            or "PROVENANCE_LEAK" in blockers else GuardCheck.PASS,
            structured_field_redundancy=GuardCheck.FAIL if "STRUCTURED_FIELD_REPLAY" in blockers
            else GuardCheck.PASS,
            supporting_point_minimization=GuardCheck.FAIL if "MAX_SUPPORTING_POINTS" in blockers
            else GuardCheck.PASS,
            material_disclosure=GuardCheck.FAIL if "REQUIRED_DISCLOSURE_MISSING" in blockers
            else GuardCheck.PASS,
            blocker_codes=(*blockers, "UNRESOLVED_SEMANTIC_CAPABILITY_DEBT"),
            reasons=("Hard-gate PASS is not semantic acceptance; public Copy remains withheld.",),
            deterministic_hard_gates=GuardCheck.PASS if hard_pass else GuardCheck.FAIL,
            capability_debt=SEMANTIC_DEBT, acceptance_witness_digest=sha256_json(witness),
            copy_egress_audit_digest=sha256_json(audit),
        )
