from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


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


class AuthorityDocumentRole(StrEnum):
    LIVE_AUTHORITY = "LIVE_AUTHORITY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    CANONICAL = "CANONICAL"


class ContextItem(BaseModel):
    id: str
    origin: ContextOrigin
    purpose: str
    task_scope: str
    payload: Any
    authority_owner: Owner | None = None
    authority_revision: str | None = None


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


class DomainResult(BaseModel):
    owner: Owner
    status: str
    output: Any = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    output_classifications: set[OutputClassification] = Field(default_factory=set)
    research_scope: str | None = None
    research_admission_receipts: list[ResearchAdmissionReceipt] = Field(default_factory=list)


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
