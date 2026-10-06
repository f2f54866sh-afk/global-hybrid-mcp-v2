from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimDisposition = Literal["PASS", "FAIL", "HOLD"]
ClaimKind = Literal["FACTUAL", "NON_FACTUAL"]
ClaimSupport = Literal["SUPPORTED", "UNSUPPORTED", "AMBIGUOUS", "NOT_APPLICABLE"]
EvidenceProvenance = Literal[
    "DIRECT_USER",
    "WORKBENCH",
    "DOCUMENT",
    "OEM_REFERENCE",
    "PLATFORM",
    "OTHER_TASK_BOUND",
]


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _normalize_public_form(value: str) -> str:
    # Preserve case, punctuation, numbers and units; normalize only NFC and whitespace.
    return " ".join(unicodedata.normalize("NFC", value).split())


class TaskBoundEvidenceFactV1(BaseModel):
    fact_id: str = Field(min_length=1)
    authority_ref: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    public_safe_forms: list[str] = Field(default_factory=list)
    provenance: EvidenceProvenance
    semantic_scope: str = Field(default="CURRENT_TASK", min_length=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_public_safe_forms(self) -> TaskBoundEvidenceFactV1:
        if any(not _normalize_public_form(form) for form in self.public_safe_forms):
            raise ValueError("PUBLIC_SAFE_FORM_EMPTY")
        return self


class TaskBoundEvidenceManifestV1(BaseModel):
    task_id: str = Field(min_length=1)
    evidence_set_digest: str = Field(min_length=64, max_length=64)
    producer_id: str = Field(min_length=1)
    facts: list[TaskBoundEvidenceFactV1] = Field(default_factory=list)
    manifest_digest: str = Field(min_length=64, max_length=64)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_manifest(self) -> TaskBoundEvidenceManifestV1:
        ids = [fact.fact_id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_EVIDENCE_FACT_ID")
        if self.recompute_digest() != self.manifest_digest:
            raise ValueError("EVIDENCE_MANIFEST_DIGEST_MISMATCH")
        return self

    def digest_payload(self) -> dict:
        return self.model_dump(mode="json", exclude={"manifest_digest"})

    def recompute_digest(self) -> str:
        return _sha256_json(self.digest_payload())

    @classmethod
    def build(
        cls,
        *,
        task_id: str,
        evidence_set_digest: str,
        producer_id: str,
        facts: list[TaskBoundEvidenceFactV1],
    ) -> TaskBoundEvidenceManifestV1:
        manifest = cls.model_construct(
            task_id=task_id,
            evidence_set_digest=evidence_set_digest,
            producer_id=producer_id,
            facts=facts,
            manifest_digest="0" * 64,
        )
        return cls(
            **manifest.model_dump(exclude={"manifest_digest"}),
            manifest_digest=manifest.recompute_digest(),
        )


class ClaimCoverageSegmentV1(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)
    kind: ClaimKind
    authority_fact_ids: list[str] = Field(default_factory=list)
    support: ClaimSupport | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_segment(self) -> ClaimCoverageSegmentV1:
        if self.end <= self.start:
            raise ValueError("CLAIM_SEGMENT_RANGE_INVALID")
        if self.kind == "NON_FACTUAL":
            if self.authority_fact_ids:
                raise ValueError("NON_FACTUAL_SEGMENT_HAS_AUTHORITY")
            if self.support not in {None, "NOT_APPLICABLE"}:
                raise ValueError("NON_FACTUAL_SEGMENT_SUPPORT_INVALID")
        return self


class ClaimCoveragePayloadV1(BaseModel):
    manifest_digest: str | None = None
    segments: list[ClaimCoverageSegmentV1] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ClaimCoverageDecisionV1(BaseModel):
    disposition: ClaimDisposition
    reason_codes: list[str]
    coverage_digest: str = Field(min_length=64, max_length=64)

    model_config = ConfigDict(extra="forbid")


def _semantic_positions(candidate: str) -> set[int]:
    return {index for index, char in enumerate(candidate) if char.isalnum()}


def _validate_surface_coverage(
    candidate: str,
    payload: ClaimCoveragePayloadV1,
    *,
    role: str,
) -> tuple[set[int], dict[int, ClaimKind], list[str]]:
    semantic_positions = _semantic_positions(candidate)
    covered: set[int] = set()
    labels: dict[int, ClaimKind] = {}
    reasons: list[str] = []

    for index, segment in enumerate(payload.segments):
        if segment.end > len(candidate) or candidate[segment.start : segment.end] != segment.text:
            reasons.append(f"{role}:SEGMENT_BINDING_MISMATCH:{index}")
            continue
        for position in range(segment.start, segment.end):
            if position not in semantic_positions:
                continue
            if position in covered:
                reasons.append(f"{role}:SEMANTIC_COVERAGE_OVERLAP:{position}")
                continue
            covered.add(position)
            labels[position] = segment.kind

    missing = sorted(semantic_positions - covered)
    if missing:
        reasons.append(f"{role}:SEMANTIC_COVERAGE_GAP:{missing[0]}")
    return covered, labels, reasons


def evaluate_claim_coverage(
    *,
    candidate: str,
    manifest: TaskBoundEvidenceManifestV1 | None,
    production: ClaimCoveragePayloadV1 | None,
    detached: ClaimCoveragePayloadV1 | None,
) -> ClaimCoverageDecisionV1:
    reasons: list[str] = []
    if manifest is None:
        reasons.append("EVIDENCE_MANIFEST_MISSING")
    if production is None:
        reasons.append("PRODUCTION_CLAIM_COVERAGE_MISSING")
    if detached is None:
        reasons.append("DETACHED_CLAIM_COVERAGE_MISSING")
    if reasons:
        disposition: ClaimDisposition = "HOLD"
        return _decision(candidate, manifest, production, detached, disposition, reasons)

    assert manifest is not None
    assert production is not None
    assert detached is not None

    if production.manifest_digest != manifest.manifest_digest:
        reasons.append("PRODUCTION_MANIFEST_BINDING_MISMATCH")
    if detached.manifest_digest is not None:
        reasons.append("DETACHED_MUST_NOT_RECEIVE_MANIFEST")

    _, production_labels, production_surface_reasons = _validate_surface_coverage(
        candidate,
        production,
        role="PRODUCTION",
    )
    _, detached_labels, detached_surface_reasons = _validate_surface_coverage(
        candidate,
        detached,
        role="DETACHED",
    )
    reasons.extend(production_surface_reasons)
    reasons.extend(detached_surface_reasons)
    if production_surface_reasons or detached_surface_reasons:
        return _decision(candidate, manifest, production, detached, "HOLD", reasons)

    for position in sorted(_semantic_positions(candidate)):
        if production_labels[position] != detached_labels[position]:
            reasons.append(f"CLAIM_CLASSIFICATION_INVARIANCE_HOLD:{position}")
            return _decision(candidate, manifest, production, detached, "HOLD", reasons)

    facts = {fact.fact_id: fact for fact in manifest.facts}
    failed = False
    held = False
    for index, segment in enumerate(production.segments):
        if segment.kind != "FACTUAL":
            continue
        # Model support is diagnostic only. Authority is the materialized safe surface.
        unknown_refs = sorted(set(segment.authority_fact_ids) - facts.keys())
        if unknown_refs:
            held = True
            reasons.append(f"UNKNOWN_AUTHORITY_FACT_ID:{index}:{unknown_refs[0]}")
            continue
        if not segment.authority_fact_ids:
            failed = True
            reasons.append(f"UNBOUND_PUBLIC_CLAIM_ATOM:{index}")
        elif len(segment.authority_fact_ids) != 1:
            held = True
            reasons.append(f"NON_ATOMIC_FACTUAL_SEGMENT:{index}")
        elif not facts[segment.authority_fact_ids[0]].public_safe_forms:
            held = True
            reasons.append(f"PUBLIC_SAFE_FORMS_MISSING:{index}")
        elif _normalize_public_form(segment.text) not in {
            _normalize_public_form(form)
            for form in facts[segment.authority_fact_ids[0]].public_safe_forms
        }:
            failed = True
            reasons.append(f"CLAIM_NOT_ENTAILED_BY_BOUND_FACT:{index}")

    if failed:
        disposition = "FAIL"
    elif held or reasons:
        disposition = "HOLD"
    else:
        disposition = "PASS"
    return _decision(candidate, manifest, production, detached, disposition, reasons)


def _decision(
    candidate: str,
    manifest: TaskBoundEvidenceManifestV1 | None,
    production: ClaimCoveragePayloadV1 | None,
    detached: ClaimCoveragePayloadV1 | None,
    disposition: ClaimDisposition,
    reasons: list[str],
) -> ClaimCoverageDecisionV1:
    body = {
        "candidate": candidate,
        "manifest_digest": None if manifest is None else manifest.manifest_digest,
        "production": None if production is None else production.model_dump(mode="json"),
        "detached": None if detached is None else detached.model_dump(mode="json"),
        "disposition": disposition,
        "reason_codes": reasons,
    }
    return ClaimCoverageDecisionV1(
        disposition=disposition,
        reason_codes=reasons,
        coverage_digest=_sha256_json(body),
    )
