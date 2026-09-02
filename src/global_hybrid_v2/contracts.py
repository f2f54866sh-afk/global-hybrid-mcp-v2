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


class AuthorityDocument(BaseModel):
    name: str
    role: AuthorityDocumentRole
    identity: str
    revision: str
    path: str


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


class DomainResult(BaseModel):
    owner: Owner
    status: str
    output: Any = None
    evidence: dict[str, Any] = Field(default_factory=dict)


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
