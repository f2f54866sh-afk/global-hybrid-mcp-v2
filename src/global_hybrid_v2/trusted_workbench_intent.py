from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator

from global_hybrid_v2.adapters.controlled_responses import (
    ForcedHostDispatchAdapter as ForcedHostDispatchAdapter,
)
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.contracts import (
    CurrentIdentityProjection,
    DialogueBindingState,
    WorkbenchSyncIntent,
)


class TrustBoundaryError(ValueError):
    pass


class EvidenceBindingState(StrEnum):
    SAFE_ATTRIBUTABLE = "SAFE_ATTRIBUTABLE"
    HOLD_CONFLICT = "HOLD_CONFLICT"


class TrustedWorkbenchEvidenceReceipt(BaseModel):
    """Server-issued evidence receipt. Never accepted unsigned from model/caller input."""

    receipt_id: str = Field(min_length=1)
    task_scope: str = Field(min_length=1)
    vehicle_instance_id: str = Field(min_length=1)
    ai_row: int = Field(ge=2)
    binding_state: EvidenceBindingState
    verified_delta: dict[str, Any]
    evidence_refs: tuple[str, ...] = ()
    issued_at: datetime
    valid_until: datetime
    issuer: str = Field(min_length=1)
    signature: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_window(self):
        if self.issued_at.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("receipt timestamps must be timezone-aware")
        if self.valid_until < self.issued_at:
            raise ValueError("receipt validity precedes issuance")
        return self


class EvidenceReceiptSigner:
    """Server-side signer/verifier for evidence receipts; key never crosses model boundary."""

    def __init__(self, *, key: bytes, issuer: str = "GLOBAL_RUNTIME_VERIFIER_V1") -> None:
        if len(key) < 32:
            raise ValueError("receipt signing key must be at least 32 bytes")
        self._key = key
        self.issuer = issuer

    @staticmethod
    def _payload(data: dict[str, Any]) -> bytes:
        body = {key: value for key, value in data.items() if key != "signature"}
        return json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
        ).encode()

    def sign(self, fields: dict[str, Any]) -> TrustedWorkbenchEvidenceReceipt:
        unsigned = TrustedWorkbenchEvidenceReceipt.model_validate(
            {**fields, "issuer": self.issuer, "signature": "0" * 64}
        )
        canonical = unsigned.model_dump(mode="json")
        digest = hmac.new(self._key, self._payload(canonical), hashlib.sha256).hexdigest()
        return unsigned.model_copy(update={"signature": digest})

    def verify(self, receipt: TrustedWorkbenchEvidenceReceipt, *, now: datetime | None = None) -> None:
        expected = hmac.new(
            self._key,
            self._payload(receipt.model_dump(mode="json")),
            hashlib.sha256,
        ).hexdigest()
        if receipt.issuer != self.issuer or not hmac.compare_digest(receipt.signature, expected):
            raise TrustBoundaryError("UNTRUSTED_WORKBENCH_EVIDENCE_RECEIPT")
        current = now or datetime.now(UTC)
        if current < receipt.issued_at or current > receipt.valid_until:
            raise TrustBoundaryError("STALE_WORKBENCH_EVIDENCE_RECEIPT")


class TrustedWorkbenchIntentProducer:
    """Only compiles an intent from a currently valid server-issued receipt."""

    def __init__(self, verifier: EvidenceReceiptSigner) -> None:
        self.verifier = verifier

    def compile(
        self,
        *,
        receipt: TrustedWorkbenchEvidenceReceipt,
        expected_task_scope: str,
        now: datetime | None = None,
    ) -> WorkbenchSyncIntent:
        self.verifier.verify(receipt, now=now)
        if receipt.task_scope != expected_task_scope:
            raise TrustBoundaryError("WORKBENCH_EVIDENCE_SCOPE_MISMATCH")
        conflict = receipt.binding_state is EvidenceBindingState.HOLD_CONFLICT
        return WorkbenchSyncIntent(
            target_file_id=CANONICAL_WORKBENCH_FILE_ID,
            vehicle_instance_id=receipt.vehicle_instance_id,
            ai_row=receipt.ai_row,
            safe_attribution=not conflict,
            identity_conflict=conflict,
            verified_delta=receipt.verified_delta,
            evidence_refs=receipt.evidence_refs,
            trusted_evidence_receipt_id=receipt.receipt_id,
        )


class CallerTask(BaseModel):
    request_text: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    workbench_sync_intent: dict[str, Any] | None = None
    company_commercial_matching: bool = False
    persistence_receipt: dict[str, Any] | None = None
    current_identity_projection: dict[str, Any] | None = None
    dialogue_binding_state: dict[str, Any] | None = None

    model_config = {"extra": "forbid"}


@dataclass(frozen=True)
class TrustedDispatchEnvelope:
    caller_task: CallerTask
    trusted_workbench_intent: WorkbenchSyncIntent | None
    company_commercial_matching: bool


class TrustedDispatchCompiler:
    """Separates caller payload from server-owned completion state."""

    def __init__(self, producer: TrustedWorkbenchIntentProducer) -> None:
        self.producer = producer

    @staticmethod
    def reject_privileged_caller_fields(caller_task: CallerTask) -> None:
        if caller_task.workbench_sync_intent is not None:
            raise TrustBoundaryError("CALLER_WORKBENCH_INTENT_FORBIDDEN")
        if caller_task.persistence_receipt is not None:
            raise TrustBoundaryError("CALLER_PERSISTENCE_RECEIPT_FORBIDDEN")
        if caller_task.company_commercial_matching:
            raise TrustBoundaryError("CALLER_COMPANY_COMMERCIAL_MATCH_FORBIDDEN")
        if (
            caller_task.current_identity_projection is not None
            or caller_task.dialogue_binding_state is not None
        ):
            raise TrustBoundaryError("CALLER_HOST_STATE_FORBIDDEN")

    def compile(
        self,
        *,
        caller_task: CallerTask,
        task_scope: str,
        evidence_receipt: TrustedWorkbenchEvidenceReceipt | None,
        now: datetime | None = None,
    ) -> TrustedDispatchEnvelope:
        self.reject_privileged_caller_fields(caller_task)
        trusted = None
        matching = False
        if evidence_receipt is not None:
            if caller_task.intent != "sales_human":
                raise TrustBoundaryError("WORKBENCH_OWNER_MISMATCH")
            trusted = self.producer.compile(
                receipt=evidence_receipt,
                expected_task_scope=task_scope,
                now=now,
            )
            matching = True
        return TrustedDispatchEnvelope(
            caller_task=caller_task,
            trusted_workbench_intent=trusted,
            company_commercial_matching=matching,
        )


class HostCurrentStateResolver(Protocol):
    def resolve(
        self, *, conversation_id: str, turn_id: str, request_text: str,
    ) -> dict[str, Any]: ...


class EvidenceReceiptProvider(Protocol):
    def resolve(
        self, *, task_scope: str, request_text: str,
    ) -> TrustedWorkbenchEvidenceReceipt | None: ...


class HostBindingCapabilityDebt(RuntimeError):
    pass


class ResolvedHostState(BaseModel):
    current_identity_projection: CurrentIdentityProjection
    dialogue_binding_state: DialogueBindingState
    source_ref: str = Field(min_length=1)


@dataclass(frozen=True)
class ServerResolvedDispatch:
    caller_task: CallerTask
    task_scope: str
    host_state: ResolvedHostState
    trusted_workbench_intent: WorkbenchSyncIntent | None
    company_commercial_matching: bool


class TrustedHostTaskCompiler:
    """Server-side join: host state + evidence receipt are resolved outside model arguments."""

    def __init__(
        self,
        *,
        dispatch_compiler: TrustedDispatchCompiler,
        host_state_resolver: HostCurrentStateResolver | None,
        evidence_provider: EvidenceReceiptProvider | None,
    ) -> None:
        self.dispatch_compiler = dispatch_compiler
        self.host_state_resolver = host_state_resolver
        self.evidence_provider = evidence_provider

    def compile(
        self,
        *,
        caller_task: CallerTask,
        conversation_id: str,
        turn_id: str,
        now: datetime | None = None,
    ) -> ServerResolvedDispatch:
        self.dispatch_compiler.reject_privileged_caller_fields(caller_task)
        if self.host_state_resolver is None:
            raise HostBindingCapabilityDebt("HOST_CURRENT_STATE_RESOLVER_UNAVAILABLE")
        if self.evidence_provider is None:
            raise HostBindingCapabilityDebt("TRUSTED_EVIDENCE_PROVIDER_UNAVAILABLE")
        if not conversation_id.strip() or not turn_id.strip():
            raise TrustBoundaryError("HOST_TASK_SCOPE_REQUIRED")
        task_scope = f"conversation:{conversation_id}:turn:{turn_id}"
        host_raw = self.host_state_resolver.resolve(
            conversation_id=conversation_id,
            turn_id=turn_id,
            request_text=caller_task.request_text,
        )
        host_state = ResolvedHostState.model_validate(host_raw)
        evidence_receipt = self.evidence_provider.resolve(
            task_scope=task_scope,
            request_text=caller_task.request_text,
        )
        trusted = self.dispatch_compiler.compile(
            caller_task=caller_task,
            task_scope=task_scope,
            evidence_receipt=evidence_receipt,
            now=now,
        )
        return ServerResolvedDispatch(
            caller_task=caller_task,
            task_scope=task_scope,
            host_state=host_state,
            trusted_workbench_intent=trusted.trusted_workbench_intent,
            company_commercial_matching=trusted.company_commercial_matching,
        )
