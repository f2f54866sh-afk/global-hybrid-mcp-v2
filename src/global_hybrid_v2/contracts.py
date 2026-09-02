from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class Owner(StrEnum):
    GLOBAL = "GLOBAL"
    SALES_HUMAN = "SALES_HUMAN"
    LIBRARY_FACT = "LIBRARY_FACT"
    VISUAL = "VISUAL"
    EXECUTION = "EXECUTION"


class Intent(StrEnum):
    GOVERNANCE = "governance"
    SALES_HUMAN = "sales_human"
    LIBRARY_FACT = "library_fact"
    VISUAL = "visual"
    EXECUTION = "execution"


class EffectType(StrEnum):
    READ_ONLY = "read_only"
    MODEL_INFERENCE = "model_inference"
    EXTERNAL_READ = "external_read"
    EXTERNAL_WRITE = "external_write"
    FILE_WRITE = "file_write"
    IMAGE_GENERATE = "image_generate"


class OutputClassification(StrEnum):
    DIAGNOSIS_ONLY = "DIAGNOSIS_ONLY"
    STATIC_KNOWLEDGE = "STATIC_KNOWLEDGE"
    CURRENT_EXTERNAL_FACT = "CURRENT_EXTERNAL_FACT"
    CURRENT_PLATFORM_CAPABILITY = "CURRENT_PLATFORM_CAPABILITY"
    CURRENT_TOOL_CAPABILITY = "CURRENT_TOOL_CAPABILITY"
    ARCHITECTURE_AFFECTING_ASSUMPTION = "ARCHITECTURE_AFFECTING_ASSUMPTION"
    PERSISTENT_REPAIR_DESIGN = "PERSISTENT_REPAIR_DESIGN"
    MUTATION_REPORT = "MUTATION_REPORT"
    PRIOR_CONTEXT_ABSENCE_CLAIM = "PRIOR_CONTEXT_ABSENCE_CLAIM"


class ResearchAdmissionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class ResearchEvidenceSource(StrEnum):
    CURRENT_CALLABLE_TOOL_RESULT = "CURRENT_CALLABLE_TOOL_RESULT"
    CURRENT_REPOSITORY_READBACK = "CURRENT_REPOSITORY_READBACK"
    CURRENT_RUNTIME_READBACK = "CURRENT_RUNTIME_READBACK"
    CURRENT_OFFICIAL_DOCUMENTATION = "CURRENT_OFFICIAL_DOCUMENTATION"
    CURRENT_WEB_SOURCE = "CURRENT_WEB_SOURCE"
    CURRENT_USER_PROVIDED_OBSERVATION = "CURRENT_USER_PROVIDED_OBSERVATION"


class MaterialChangeReason(StrEnum):
    CODE_CHANGED = "CODE_CHANGED"
    CONFIG_CHANGED = "CONFIG_CHANGED"
    ENVIRONMENT_CHANGED = "ENVIRONMENT_CHANGED"
    INPUT_CHANGED = "INPUT_CHANGED"
    DIAGNOSTIC_INSTRUMENTATION_CHANGED = "DIAGNOSTIC_INSTRUMENTATION_CHANGED"
    DEPENDENCY_STATE_CHANGED = "DEPENDENCY_STATE_CHANGED"
    VERIFIED_TRANSIENT_RETRY_CONDITION = "VERIFIED_TRANSIENT_RETRY_CONDITION"


class TransientRetryEvidence(BaseModel):
    source: ResearchEvidenceSource
    reference: str = Field(min_length=1)
    observed_result: str = Field(min_length=1)
    verified: bool = False


class RetryContext(BaseModel):
    operation_key: str = Field(min_length=1)
    prior_failure_signature: str | None = Field(default=None, min_length=1)
    material_change_reasons: list[str] = Field(default_factory=list)
    transient_retry_evidence: TransientRetryEvidence | None = None


class ContextOrigin(StrEnum):
    CURRENT_USER = "current_user"
    CURRENT_AUTHORITY = "current_authority"
    CURRENT_TOOL_RESULT = "current_tool_result"
    HISTORY = "history"
    ARCHIVE = "archive"
    MEMORY = "memory"
    UNKNOWN = "unknown"


class ContextClass(StrEnum):
    NORMATIVE_AUTHORITY = "NORMATIVE_AUTHORITY"
    STABLE_USER_PREFERENCE = "STABLE_USER_PREFERENCE"
    DOMAIN_HEURISTIC = "DOMAIN_HEURISTIC"
    REFERENCE_POINTER = "REFERENCE_POINTER"
    CASE_HISTORY = "CASE_HISTORY"
    CURRENT_FACT = "CURRENT_FACT"
    CURRENT_CAPABILITY_FACT = "CURRENT_CAPABILITY_FACT"
    STALE_OR_SUPERSEDED_RULE = "STALE_OR_SUPERSEDED_RULE"
    UNKNOWN = "UNKNOWN"


class ContextAdmissionDecision(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    ADVISORY = "ADVISORY"
    RETRIEVAL_HINT = "RETRIEVAL_HINT"
    QUARANTINE = "QUARANTINE"


class ContextAdmissionReason(StrEnum):
    CURRENT_CONTEXT_ACCEPTED = "CURRENT_CONTEXT_ACCEPTED"
    ADVISORY_MEMORY_ACCEPTED = "ADVISORY_MEMORY_ACCEPTED"
    ADVISORY_HISTORY_ACCEPTED = "ADVISORY_HISTORY_ACCEPTED"
    REFERENCE_POINTER_ACCEPTED = "REFERENCE_POINTER_ACCEPTED"
    CASE_HISTORY_NOT_CURRENTLY_BOUND = "CASE_HISTORY_NOT_CURRENTLY_BOUND"
    CASE_HISTORY_CURRENTLY_BOUND = "CASE_HISTORY_CURRENTLY_BOUND"
    LEGACY_AUTHORITY_FORBIDDEN = "LEGACY_AUTHORITY_FORBIDDEN"
    CURRENT_CAPABILITY_REQUIRES_FRESH_EVIDENCE = (
        "CURRENT_CAPABILITY_REQUIRES_FRESH_EVIDENCE"
    )
    STALE_RULE_BLOCKED = "STALE_RULE_BLOCKED"
    MISSING_SCOPE = "MISSING_SCOPE"
    MISSING_PURPOSE = "MISSING_PURPOSE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    UNKNOWN_CONTEXT_CLASS = "UNKNOWN_CONTEXT_CLASS"
    AUTHORITY_METADATA_MISSING = "AUTHORITY_METADATA_MISSING"
    AUTHORITY_REVISION_MISMATCH = "AUTHORITY_REVISION_MISMATCH"
    NORMATIVE_AUTHORITY_REQUIRES_CURRENT_AUTHORITY = (
        "NORMATIVE_AUTHORITY_REQUIRES_CURRENT_AUTHORITY"
    )
    LEGACY_FACT_RETRIEVAL_HINT = "LEGACY_FACT_RETRIEVAL_HINT"
    CURRENT_FACT_REQUIRES_VERIFIED_SOURCE = "CURRENT_FACT_REQUIRES_VERIFIED_SOURCE"
    UNSUPPORTED_CONTEXT_ORIGIN = "UNSUPPORTED_CONTEXT_ORIGIN"


class RetrievalState(StrEnum):
    FOUND = "FOUND"
    NOT_RETRIEVED = "NOT_RETRIEVED"
    COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"
    SOURCE_INACCESSIBLE = "SOURCE_INACCESSIBLE"
    VERIFIED_ABSENT = "VERIFIED_ABSENT"


class RetrievalFalseNegativeReason(StrEnum):
    QUERY_MISMATCH = "QUERY_MISMATCH"
    SOURCE_NOT_SEARCHED = "SOURCE_NOT_SEARCHED"
    TOP_K_TRUNCATION = "TOP_K_TRUNCATION"
    SEMANTIC_DRIFT = "SEMANTIC_DRIFT"
    CONTEXT_FIREWALL_DROP = "CONTEXT_FIREWALL_DROP"
    INDEX_GAP = "INDEX_GAP"
    RETRIEVAL_ROUTE_GAP = "RETRIEVAL_ROUTE_GAP"
    UNKNOWN = "UNKNOWN"


class AuthorityDocumentRole(StrEnum):
    LIVE_AUTHORITY = "LIVE_AUTHORITY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    CANONICAL = "CANONICAL"


class ContextItem(BaseModel):
    id: str
    origin: ContextOrigin
    context_class: ContextClass = ContextClass.UNKNOWN
    purpose: str
    task_scope: str
    payload: Any
    provenance: list[str] = Field(default_factory=list)
    current_binding: bool = False
    authority_owner: Owner | None = None
    authority_revision: str | None = None


class ContextAdmissionReceipt(BaseModel):
    context_id: str
    origin: ContextOrigin
    context_class: ContextClass
    decision: ContextAdmissionDecision
    reason_code: ContextAdmissionReason


class TaskRequest(BaseModel):
    request_text: str = Field(min_length=1)
    intent: Intent
    effects: list[EffectType] = Field(default_factory=lambda: [EffectType.READ_ONLY])
    context: list[ContextItem] = Field(default_factory=list)
    retry_context: RetryContext | None = None


class AuthorityDocument(BaseModel):
    name: str
    role: AuthorityDocumentRole
    revision: str
    path: str
    native_owner: str | None = None
    native_authority_role: str | None = None


class AuthorityEntry(BaseModel):
    owner: Owner
    normative_authority: AuthorityDocument
    authority_partition: str | None = None
    references: list[AuthorityDocument] = Field(default_factory=list)

    @property
    def revision(self) -> str:
        return self.normative_authority.revision

    @property
    def path(self) -> str:
        return self.normative_authority.path


class AuthoritySnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    entries: dict[Owner, AuthorityEntry]


class TaskContract(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    request_text: str
    intent: Intent
    owner: Owner
    effects: list[EffectType]
    authority_snapshot_id: str
    context: list[ContextItem]
    context_admission_receipts: list[ContextAdmissionReceipt] = Field(default_factory=list)
    retry_context: RetryContext | None = None


class ResearchEvidence(BaseModel):
    source: ResearchEvidenceSource
    reference: str = Field(min_length=1)
    observed_result: str = Field(min_length=1)


class ResearchAdmissionReceipt(BaseModel):
    status: ResearchAdmissionStatus
    semantic_key: OutputClassification
    scope: str = Field(min_length=1)
    issued_at: datetime
    valid_until: datetime
    evidence: list[ResearchEvidence] = Field(min_length=1)


class RetrievalReceipt(BaseModel):
    retrieval_key: str = Field(min_length=1)
    state: RetrievalState
    searched_source_classes: list[str] = Field(default_factory=list)
    query_variants: list[str] = Field(default_factory=list)
    coverage_complete: bool = False
    unresolved_source_gap: bool = True
    evidence_references: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_verified_absent(self) -> RetrievalReceipt:
        if self.state is not RetrievalState.VERIFIED_ABSENT:
            return self
        source_classes = [item.strip() for item in self.searched_source_classes if item.strip()]
        query_variants = [item.strip() for item in self.query_variants if item.strip()]
        if (
            not self.coverage_complete
            or self.unresolved_source_gap
            or not source_classes
            or not query_variants
        ):
            raise ValueError(
                "VERIFIED_ABSENT requires complete coverage, no unresolved source gap, "
                "searched source classes, and query variants"
            )
        return self


class RetrievalFalseNegativeEvidence(BaseModel):
    retrieval_key: str = Field(min_length=1)
    prior_negative_claim: bool = False
    later_matching_content_found: bool = False
    reason: RetrievalFalseNegativeReason = RetrievalFalseNegativeReason.UNKNOWN


class DomainResult(BaseModel):
    owner: Owner
    status: str
    output: Any = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    output_classifications: set[OutputClassification] = Field(default_factory=set)
    research_scope: str | None = None
    research_admission_receipts: list[ResearchAdmissionReceipt] = Field(default_factory=list)
    retrieval_key: str | None = None
    retrieval_receipts: list[RetrievalReceipt] = Field(default_factory=list)
    retrieval_false_negative_evidence: list[RetrievalFalseNegativeEvidence] = Field(
        default_factory=list
    )


class TraceEvent(BaseModel):
    trace_id: str
    task_id: str
    stage: str
    owner: Owner | None = None
    decision: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WitnessFinding(BaseModel):
    task_id: str
    severity: str
    code: str
    message: str
