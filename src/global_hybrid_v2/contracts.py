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


class RiskClass(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class DomainInteractionMode(StrEnum):
    SERVICE = "SERVICE"
    TEMPORARY_COLLABORATION = "TEMPORARY_COLLABORATION"


class DomainContractStatus(StrEnum):
    DRAFT = "DRAFT"
    PASS = "PASS"
    HOLD = "HOLD"
    REJECTED = "REJECTED"


class ContractCurrentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class LibraryAccessKind(StrEnum):
    READ_PROJECTION = "READ_PROJECTION"
    FACT_NEED_SIGNAL = "FACT_NEED_SIGNAL"
    COMMIT_FACT = "COMMIT_FACT"


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


class ResearchProviderAvailability(StrEnum):
    CALLABLE = "CALLABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ResearchExecutionStatus(StrEnum):
    PASS = "PASS"
    FAILED = "FAILED"


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
    EXTERNAL_SOURCE = "external_source"
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
    UNTRUSTED_EXTERNAL_EVIDENCE = "UNTRUSTED_EXTERNAL_EVIDENCE"
    UNKNOWN = "UNKNOWN"


class ContextContentRole(StrEnum):
    DATA_ONLY = "DATA_ONLY"
    EXECUTABLE_INSTRUCTION = "EXECUTABLE_INSTRUCTION"


class ContextAuthorityEffect(StrEnum):
    NO_AUTHORITY_EFFECT = "NO_AUTHORITY_EFFECT"
    CURRENT_AUTHORITY = "CURRENT_AUTHORITY"
    EXPLICIT_USER_AUTHORIZATION = "EXPLICIT_USER_AUTHORIZATION"


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
    CURRENT_CAPABILITY_REQUIRES_FRESH_EVIDENCE = "CURRENT_CAPABILITY_REQUIRES_FRESH_EVIDENCE"
    STALE_RULE_BLOCKED = "STALE_RULE_BLOCKED"
    MISSING_SCOPE = "MISSING_SCOPE"
    MISSING_PURPOSE = "MISSING_PURPOSE"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    UNKNOWN_CONTEXT_CLASS = "UNKNOWN_CONTEXT_CLASS"
    AUTHORITY_METADATA_MISSING = "AUTHORITY_METADATA_MISSING"
    AUTHORITY_REVISION_MISMATCH = "AUTHORITY_REVISION_MISMATCH"
    NORMATIVE_AUTHORITY_REQUIRES_CURRENT_AUTHORITY = "NORMATIVE_AUTHORITY_REQUIRES_CURRENT_AUTHORITY"
    LEGACY_FACT_RETRIEVAL_HINT = "LEGACY_FACT_RETRIEVAL_HINT"
    CURRENT_FACT_REQUIRES_VERIFIED_SOURCE = "CURRENT_FACT_REQUIRES_VERIFIED_SOURCE"
    UNSUPPORTED_CONTEXT_ORIGIN = "UNSUPPORTED_CONTEXT_ORIGIN"
    UNTRUSTED_EVIDENCE_DATA_ONLY = "UNTRUSTED_EVIDENCE_DATA_ONLY"
    EXTERNAL_INSTRUCTION_IGNORED = "EXTERNAL_INSTRUCTION_IGNORED"
    QUARANTINE_EXTERNAL_DIRECTIVE = "QUARANTINE_EXTERNAL_DIRECTIVE"


class CurrentIdentityProjection(BaseModel):
    """Ephemeral, host-supplied current identity map for one MCP task."""

    mapping_version: str = Field(min_length=1)
    identities: dict[str, str] = Field(min_length=1)
    issued_at: datetime
    valid_until: datetime

    @model_validator(mode="after")
    def validate_current_window(self) -> CurrentIdentityProjection:
        if self.issued_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("identity projection timestamps must be timezone-aware")
        if self.valid_until < self.issued_at:
            raise ValueError("identity projection validity precedes issuance")
        if any(not alias.strip() or not target.strip() for alias, target in self.identities.items()):
            raise ValueError("identity projection aliases and targets must be non-blank")
        return self


class DialogueBindingState(BaseModel):
    """Ephemeral host binding for the exact dialogue referent consumed by this task."""

    mapping_version: str = Field(min_length=1)
    requested_identity_alias: str = Field(min_length=1)
    resolved_referent_id: str = Field(min_length=1)
    issued_at: datetime
    valid_until: datetime
    material_ambiguity: bool = False

    @model_validator(mode="after")
    def validate_current_window(self) -> DialogueBindingState:
        if self.issued_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("dialogue binding timestamps must be timezone-aware")
        if self.valid_until < self.issued_at:
            raise ValueError("dialogue binding validity precedes issuance")
        return self


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
    content_role: ContextContentRole = ContextContentRole.DATA_ONLY
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
    admitted_content_role: ContextContentRole = ContextContentRole.DATA_ONLY
    authority_effect: ContextAuthorityEffect = ContextAuthorityEffect.NO_AUTHORITY_EFFECT
    raw_evidence_stored_for_audit: bool = False
    directive_detected: bool = False
    directive_quarantined: bool = False
    persistence_effect: bool = False
    raw_evidence_sha256: str | None = None
    quarantined_paths: list[str] = Field(default_factory=list)


class TaskRequest(BaseModel):
    request_text: str = Field(min_length=1)
    intent: Intent
    effects: list[EffectType] = Field(default_factory=lambda: [EffectType.READ_ONLY])
    context: list[ContextItem] = Field(default_factory=list)
    retry_context: RetryContext | None = None
    risk_class: RiskClass | None = None
    target_system: str | None = None
    action_class: str | None = None
    current_identity_projection: CurrentIdentityProjection | None = None
    dialogue_binding_state: DialogueBindingState | None = None


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


class DomainContract(BaseModel):
    """Owner-neutral envelope for an explicit cross-domain handoff.

    The payload remains provider-owned.  GLOBAL validates only this envelope and
    the fields the consumer declares that it consumed.
    """

    task_trace_id: str = Field(min_length=1)
    contract_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: int = Field(default=1, ge=1)
    provider_owner: Owner
    consumer_owner: Owner
    task_scope: str = Field(min_length=1)
    source_authority_revision: str = Field(min_length=1)
    requirement_ids: list[str] = Field(min_length=1)
    required_fields: set[str] = Field(default_factory=set)
    optional_fields: set[str] = Field(default_factory=set)
    used_fields: set[str] = Field(default_factory=set)
    blocked_foreign_fields: set[str] = Field(default_factory=set)
    currentness: ContractCurrentness
    provenance: list[str] = Field(min_length=1)
    status: DomainContractStatus = DomainContractStatus.DRAFT
    interaction_mode: DomainInteractionMode = DomainInteractionMode.SERVICE
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cross_domain_envelope(self) -> DomainContract:
        if self.provider_owner is self.consumer_owner:
            raise ValueError("cross-domain contract requires distinct provider and consumer")

        field_groups = {
            "required_fields": self.required_fields,
            "optional_fields": self.optional_fields,
            "used_fields": self.used_fields,
            "blocked_foreign_fields": self.blocked_foreign_fields,
        }
        for label, values in field_groups.items():
            if any(not value.strip() for value in values):
                raise ValueError(f"{label} cannot contain blank field names")

        if self.required_fields & self.optional_fields:
            raise ValueError("required and optional contract fields must be disjoint")
        if (self.required_fields | self.optional_fields) & self.blocked_foreign_fields:
            raise ValueError("allowed and blocked foreign fields must be disjoint")

        declared = self.required_fields | self.optional_fields
        if not self.used_fields <= declared:
            raise ValueError("consumer used undeclared contract fields")
        if self.used_fields & self.blocked_foreign_fields:
            raise ValueError("consumer used blocked foreign fields")
        if not self.used_fields <= set(self.payload):
            raise ValueError("consumer used fields absent from payload")

        if self.status is DomainContractStatus.PASS:
            if not self.required_fields <= set(self.payload):
                raise ValueError("passing contract is missing required fields")
            if self.currentness is not ContractCurrentness.CURRENT:
                raise ValueError("passing contract must be current")
            if not all(item.strip() for item in self.provenance):
                raise ValueError("passing contract requires non-blank provenance")
        return self


class LibraryAccessRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    contract_version: int = Field(default=1, ge=1)
    actor_owner: Owner
    access_kind: LibraryAccessKind
    task_scope: str = Field(min_length=1)
    projection: str | None = None
    required_fields: set[str] = Field(default_factory=set)


class TaskContract(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    task_trace_id: str = Field(default_factory=lambda: str(uuid4()))
    contract_id: str = Field(default_factory=lambda: str(uuid4()))
    request_text: str
    intent: Intent
    owner: Owner
    effects: list[EffectType]
    authority_snapshot_id: str
    context: list[ContextItem]
    context_admission_receipts: list[ContextAdmissionReceipt] = Field(default_factory=list)
    retry_context: RetryContext | None = None
    risk_class: RiskClass = RiskClass.R0
    current_mapping_version: str | None = None
    resolved_referent_id: str | None = None
    domain_contracts: list[DomainContract] = Field(default_factory=list)
    research_admission_receipts: list[ResearchAdmissionReceipt] = Field(default_factory=list)
    research_execution_receipts: list[ResearchExecutionReceipt] = Field(default_factory=list)


class ResearchEvidence(BaseModel):
    source: ResearchEvidenceSource
    reference: str = Field(min_length=1)
    observed_result: str = Field(min_length=1)
    authority_effect: ContextAuthorityEffect = ContextAuthorityEffect.NO_AUTHORITY_EFFECT


class ResearchAdmissionReceipt(BaseModel):
    status: ResearchAdmissionStatus
    semantic_key: OutputClassification
    scope: str = Field(min_length=1)
    issued_at: datetime
    valid_until: datetime
    evidence: list[ResearchEvidence] = Field(min_length=1)


class ResearchCoverage(BaseModel):
    complete: bool = False
    covered_semantic_keys: set[OutputClassification] = Field(default_factory=set)
    unresolved_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_complete_coverage(self) -> ResearchCoverage:
        if self.complete and self.unresolved_gaps:
            raise ValueError("complete research coverage cannot contain unresolved gaps")
        return self


class ResearchRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = Field(min_length=1)
    original_owner: Owner
    original_task_scope: str = Field(min_length=1)
    research_scope: str = Field(min_length=1)
    required_semantic_keys: list[OutputClassification] = Field(min_length=1)
    queries: list[str] = Field(min_length=1)
    allowed_source_classes: list[ResearchEvidenceSource] = Field(min_length=1)
    authority_revision: str = Field(min_length=1)
    attempt: int = Field(ge=1)
    retrieval_strategy: str = Field(min_length=1)


class ResearchExecutionReceipt(BaseModel):
    request_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    status: ResearchExecutionStatus
    queries_executed: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    coverage: ResearchCoverage = Field(default_factory=ResearchCoverage)
    error: str | None = None
    blocker: str | None = None

    @model_validator(mode="after")
    def validate_execution_receipt(self) -> ResearchExecutionReceipt:
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("research execution timestamps must be timezone-aware")
        if self.completed_at < self.started_at:
            raise ValueError("research execution completion precedes start")
        if self.status is ResearchExecutionStatus.PASS and (not self.queries_executed or not self.evidence):
            raise ValueError("successful research execution requires queries and evidence")
        if self.status is ResearchExecutionStatus.FAILED and not (self.error or self.blocker):
            raise ValueError("failed research execution requires an error or blocker")
        return self


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
    research_execution_receipts: list[ResearchExecutionReceipt] = Field(default_factory=list)
    retrieval_key: str | None = None
    retrieval_receipts: list[RetrievalReceipt] = Field(default_factory=list)
    retrieval_false_negative_evidence: list[RetrievalFalseNegativeEvidence] = Field(default_factory=list)
    research_evidence_packet: dict[str, Any] | None = None
    final_response_object: dict[str, Any] | None = None
    turn_contract: dict[str, Any] | None = None
    action_plan: dict[str, Any] | None = None


class TraceEvent(BaseModel):
    trace_id: str
    task_id: str
    span_id: str | None = None
    parent_span_id: str | None = None
    span_owner: str | None = None
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


TaskContract.model_rebuild()
