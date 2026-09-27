"""Server-signed, verifier-issued receipts for the fail-stop RD-021 sequence."""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from global_hybrid_v2.canonical_projection import ProjectionEvent, XlsxProjectionVerifier
from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
from global_hybrid_v2.media_object_probe import MediaObjectDeploymentProbeHttp
from global_hybrid_v2.media_schema_contract import (
    D1MediaMigrationContract,
    D1MediaSchemaReadbackHttp,
    D1MigrationState,
)
from global_hybrid_v2.transactional_vehicle_store import CanonicalReadback


class DeploymentStep(StrEnum):
    CURRENT_STATE_PREFLIGHT = "CURRENT_STATE_PREFLIGHT"
    R2_BINDING_READY = "R2_BINDING_READY"
    D1_MIGRATION = "D1_MIGRATION"
    D1_SCHEMA_READBACK = "D1_SCHEMA_READBACK"
    CANONICAL_XLSX_SCHEMA_MIGRATION = "CANONICAL_XLSX_SCHEMA_MIGRATION"
    XLSX_FRESH_READBACK = "XLSX_FRESH_READBACK"
    RUNTIME_BINDINGS = "RUNTIME_BINDINGS"
    STAGING_MEDIA_READBACK = "STAGING_MEDIA_READBACK"
    STAGING_CREATIVE_REF_READBACK = "STAGING_CREATIVE_REF_READBACK"
    MATCHING_END_TO_END = "MATCHING_END_TO_END"
    PRODUCTION_BEHAVIOR_OBSERVATION = "PRODUCTION_BEHAVIOR_OBSERVATION"


DEPLOYMENT_ORDER = tuple(DeploymentStep)
PASS_STATE = {
    **{step: "READBACK_PASS" for step in DEPLOYMENT_ORDER},
    DeploymentStep.R2_BINDING_READY: "PROBE_PASS",
    DeploymentStep.D1_SCHEMA_READBACK: "APPLIED_READBACK_PASS",
    DeploymentStep.XLSX_FRESH_READBACK: "PROJECTION_READBACK_PASS",
}


@dataclass(frozen=True)
class DeploymentReceipt:
    deployment_id: str
    step: DeploymentStep
    target: str
    source_revision: str
    expected_preimage: str
    result_state: str
    readback_evidence_digest: str
    issued_at: str
    issuer: str
    execution_owner: str
    previous_step_receipt_digest: str | None
    signature: str

    def payload(self) -> bytes:
        return json.dumps({
            key: value.value if isinstance(value, StrEnum) else value
            for key, value in vars(self).items() if key != "signature"
        }, sort_keys=True, separators=(",", ":")).encode()

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.payload() + b"\0" + self.signature.encode()).hexdigest()


class DeploymentReceiptAuthority:
    """The signing key stays with server-side verifiers, never model arguments."""

    def __init__(self, *, signing_key: bytes, issuer: str, execution_owner: str) -> None:
        if len(signing_key) < 32 or not issuer or not execution_owner:
            raise ValueError("DEPLOYMENT_RECEIPT_AUTHORITY_INVALID")
        self.__key = signing_key
        self.issuer = issuer
        self.execution_owner = execution_owner

    def verify(self, receipt: DeploymentReceipt) -> bool:
        if not isinstance(receipt, DeploymentReceipt):
            return False
        expected = hmac.new(self.__key, receipt.payload(), hashlib.sha256).hexdigest()
        return (receipt.issuer == self.issuer and receipt.execution_owner == self.execution_owner
                and hmac.compare_digest(expected, receipt.signature))

    def _seal(self, *, deployment_id: str, step: DeploymentStep, target: str,
              source_revision: str, expected_preimage: str, result_state: str,
              readback_evidence_digest: str,
              previous_step_receipt_digest: str | None) -> DeploymentReceipt:
        if (not deployment_id or not target or not source_revision or not expected_preimage
            or not result_state or len(readback_evidence_digest) != 64):
            raise ValueError("DEPLOYMENT_RECEIPT_EVIDENCE_INCOMPLETE")
        unsigned = DeploymentReceipt(
            deployment_id, step, target, source_revision, expected_preimage, result_state,
            readback_evidence_digest, datetime.now(UTC).isoformat(), self.issuer,
            self.execution_owner, previous_step_receipt_digest, "",
        )
        signature = hmac.new(self.__key, unsigned.payload(), hashlib.sha256).hexdigest()
        return DeploymentReceipt(**{**vars(unsigned), "signature": signature})

    def from_d1_postmigration(self, contract: D1MediaMigrationContract,
                              readback: D1MediaSchemaReadbackHttp, *, deployment_id: str,
                              target: str, source_revision: str, expected_preimage: str,
                              previous_step_receipt_digest: str) -> DeploymentReceipt:
        if type(contract) is not D1MediaMigrationContract or type(readback) is not D1MediaSchemaReadbackHttp:
            raise ValueError("D1_READBACK_EXECUTOR_INVALID")
        result = contract.postmigration(readback.snapshot())
        if (result.state is not D1MigrationState.APPLIED_READBACK_PASS
            or not result.schema_fingerprint):
            raise ValueError("D1_READBACK_RECEIPT_NOT_VERIFIED")
        return self._seal(
            deployment_id=deployment_id, step=DeploymentStep.D1_SCHEMA_READBACK,
            target=target, source_revision=source_revision, expected_preimage=expected_preimage,
            result_state=result.state.value, readback_evidence_digest=result.schema_fingerprint,
            previous_step_receipt_digest=previous_step_receipt_digest,
        )

    def from_xlsx_readback(self, verifier: XlsxProjectionVerifier, *,
                           event: ProjectionEvent | None = None,
                           state: CanonicalReadback | None = None,
                           task_id: str | None = None, deployment_id: str,
                           target: str, source_revision: str, expected_preimage: str,
                           previous_step_receipt_digest: str) -> DeploymentReceipt:
        if type(verifier) is not XlsxProjectionVerifier or event is None or state is None:
            raise ValueError("XLSX_READBACK_EXECUTOR_INVALID")
        if verifier.file_id != CANONICAL_WORKBENCH_FILE_ID:
            raise ValueError("XLSX_READBACK_RECEIPT_NOT_VERIFIED")
        digest = verifier.verify(event, state)
        return self._seal(
            deployment_id=deployment_id, step=DeploymentStep.XLSX_FRESH_READBACK,
            target=target, source_revision=source_revision, expected_preimage=expected_preimage,
            result_state="PROJECTION_READBACK_PASS", readback_evidence_digest=digest,
            previous_step_receipt_digest=previous_step_receipt_digest,
        )

    def from_r2_probe(self, probe: MediaObjectDeploymentProbeHttp, *, raw: bytes,
                      deployment_id: str,
                      target: str, source_revision: str, expected_preimage: str,
                      previous_step_receipt_digest: str | None) -> DeploymentReceipt:
        if type(probe) is not MediaObjectDeploymentProbeHttp:
            raise ValueError("R2_PROBE_EXECUTOR_INVALID")
        result = probe.probe(raw, deployment_id=deployment_id)
        if (result.state != "PROBE_PASS" or result.deployment_id != deployment_id
            or not result.cleanup_readback_digest):
            raise ValueError("R2_CLEANUP_RECEIPT_NOT_VERIFIED")
        return self._seal(
            deployment_id=deployment_id, step=DeploymentStep.R2_BINDING_READY,
            target=target, source_revision=source_revision, expected_preimage=expected_preimage,
            result_state=result.state, readback_evidence_digest=result.cleanup_readback_digest,
            previous_step_receipt_digest=previous_step_receipt_digest,
        )


@dataclass(frozen=True)
class DeploymentProgress:
    deployment_id: str
    target: str
    source_revision: str
    expected_preimage: str
    receipts: tuple[DeploymentReceipt, ...] = ()
    hold: str | None = None

    @property
    def next_step(self) -> DeploymentStep | None:
        if self.hold or len(self.receipts) == len(DEPLOYMENT_ORDER):
            return None
        return DEPLOYMENT_ORDER[len(self.receipts)]

    def record(
        self, receipt: DeploymentReceipt, *, authority: DeploymentReceiptAuthority,
    ) -> DeploymentProgress:
        previous = None
        for index, prior in enumerate(self.receipts):
            if (not isinstance(prior, DeploymentReceipt)
                or prior.step is not DEPLOYMENT_ORDER[index]
                or prior.deployment_id != self.deployment_id or prior.target != self.target
                or prior.source_revision != self.source_revision
                or prior.expected_preimage != self.expected_preimage
                or prior.previous_step_receipt_digest != previous
                or prior.result_state != PASS_STATE[prior.step] or not authority.verify(prior)):
                raise ValueError("HOLD_DEPLOYMENT_PRIOR_RECEIPT_INVALID")
            previous = prior.digest
        if (self.hold or not isinstance(receipt, DeploymentReceipt)
            or receipt.step is not self.next_step or receipt.deployment_id != self.deployment_id
            or receipt.target != self.target or receipt.source_revision != self.source_revision
            or receipt.expected_preimage != self.expected_preimage
            or receipt.previous_step_receipt_digest != previous
            or not authority.verify(receipt)):
            raise ValueError("HOLD_DEPLOYMENT_SEQUENCE_CONFLICT")
        if receipt.result_state != PASS_STATE[receipt.step]:
            return DeploymentProgress(
                self.deployment_id, self.target, self.source_revision, self.expected_preimage,
                self.receipts, f"{receipt.step.value}:{receipt.result_state}",
            )
        return DeploymentProgress(
            self.deployment_id, self.target, self.source_revision, self.expected_preimage,
            (*self.receipts, receipt),
        )
