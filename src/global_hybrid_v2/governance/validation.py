from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from global_hybrid_v2.contracts import Owner


class FalsificationPath(StrEnum):
    RAW_TOOL_RECEIPT = "RAW_TOOL_RECEIPT"
    DETERMINISTIC_ASSERTION = "DETERMINISTIC_ASSERTION"
    CURRENT_ROOT_READBACK = "CURRENT_ROOT_READBACK"
    CONSUMER_TRACE = "CONSUMER_TRACE"
    ACTUAL_EXECUTION_INPUT = "ACTUAL_EXECUTION_INPUT"
    ACTUAL_OUTPUT_ARTIFACT = "ACTUAL_OUTPUT_ARTIFACT"
    INDEPENDENT_CONTRACT_TEST = "INDEPENDENT_CONTRACT_TEST"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    EXTERNAL_AUTHORITATIVE_EVIDENCE = "EXTERNAL_AUTHORITATIVE_EVIDENCE"
    REAL_BUSINESS_OUTCOME = "REAL_BUSINESS_OUTCOME"
    ROLE_RESTATEMENT = "ROLE_RESTATEMENT"
    OWNER_SELF_CERTIFICATION = "OWNER_SELF_CERTIFICATION"


class EvidenceVerdict(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INCONCLUSIVE = "INCONCLUSIVE"


class ValidationStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class ValidationClaim(StrEnum):
    INDEPENDENTLY_VALIDATED = "INDEPENDENTLY_VALIDATED"
    INTERNALLY_CONSISTENT = "INTERNALLY_CONSISTENT"
    INDEPENDENT_EVIDENCE_PENDING = "INDEPENDENT_EVIDENCE_PENDING"
    PRIMARY_CONCLUSION_CONTRADICTED = "PRIMARY_CONCLUSION_CONTRADICTED"


class FalsificationEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    path: FalsificationPath
    verdict: EvidenceVerdict
    reference: str = Field(min_length=1)
    lineage_id: str = Field(min_length=1)
    source_owner: Owner | None = None


class ValidationReceipt(BaseModel):
    primary_owner: Owner
    primary_conclusion: str = Field(min_length=1)
    status: ValidationStatus
    claim: ValidationClaim
    independent_evidence_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    blocker: str | None = None


class DissimilarValidationGate:
    """Require a materially different evidence path, not a renamed role agreement."""

    NON_INDEPENDENT_PATHS = {
        FalsificationPath.ROLE_RESTATEMENT,
        FalsificationPath.OWNER_SELF_CERTIFICATION,
    }

    def evaluate(
        self,
        *,
        primary_owner: Owner,
        primary_conclusion: str,
        evidence: list[FalsificationEvidence],
    ) -> ValidationReceipt:
        independent: list[FalsificationEvidence] = []
        seen_lineages: set[str] = set()
        for item in evidence:
            if item.path in self.NON_INDEPENDENT_PATHS:
                continue
            if item.lineage_id in seen_lineages:
                continue
            seen_lineages.add(item.lineage_id)
            independent.append(item)

        contradictions = [
            item for item in independent if item.verdict is EvidenceVerdict.CONTRADICTS
        ]
        if contradictions:
            return ValidationReceipt(
                primary_owner=primary_owner,
                primary_conclusion=primary_conclusion,
                status=ValidationStatus.CONTRADICTED,
                claim=ValidationClaim.PRIMARY_CONCLUSION_CONTRADICTED,
                independent_evidence_ids=[item.evidence_id for item in independent],
                contradiction_ids=[item.evidence_id for item in contradictions],
                blocker="FALSIFICATION_PATH_CONTRADICTS_PRIMARY_CONCLUSION",
            )

        supporting = [
            item for item in independent if item.verdict is EvidenceVerdict.SUPPORTS
        ]
        if supporting:
            return ValidationReceipt(
                primary_owner=primary_owner,
                primary_conclusion=primary_conclusion,
                status=ValidationStatus.SUPPORTED,
                claim=ValidationClaim.INDEPENDENTLY_VALIDATED,
                independent_evidence_ids=[item.evidence_id for item in independent],
            )

        claim = (
            ValidationClaim.INTERNALLY_CONSISTENT
            if evidence
            else ValidationClaim.INDEPENDENT_EVIDENCE_PENDING
        )
        return ValidationReceipt(
            primary_owner=primary_owner,
            primary_conclusion=primary_conclusion,
            status=ValidationStatus.UNRESOLVED,
            claim=claim,
            independent_evidence_ids=[item.evidence_id for item in independent],
            blocker="MATERIALLY_INDEPENDENT_EVIDENCE_MISSING",
        )
