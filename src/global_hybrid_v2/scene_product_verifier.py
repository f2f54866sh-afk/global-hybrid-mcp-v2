"""Qualified, server-owned scene and product verification for targeted edits."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from PIL import Image
from pydantic import BaseModel, Field, model_validator

from global_hybrid_v2.adapters.openai_bound_image import (
    ImageAssetResolver,
    QualifiedOutputVerification,
)
from global_hybrid_v2.image_surface import IdentitySourceRole, ImageExecutionRequest


class SceneVerificationError(RuntimeError):
    """Typed fail-closed scene verification error."""


class SceneDecision(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"


class PinnedModelArtifact(BaseModel):
    backend_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_id: str = Field(min_length=1)
    runtime_version: str = Field(min_length=1)
    preprocessing_version: str = Field(min_length=1)

    def verify_file(self) -> None:
        path = Path(self.artifact_path)
        if not path.is_file():
            raise SceneVerificationError("SCENE_VERIFIER_MODEL_ARTIFACT_MISSING")
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.artifact_sha256:
            raise SceneVerificationError("SCENE_VERIFIER_MODEL_ARTIFACT_MISMATCH")


class MetricResult(BaseModel):
    metric_id: str = Field(min_length=1)
    score: float
    threshold: float
    threshold_version: str = Field(min_length=1)
    threshold_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: SceneDecision
    region_scores: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def threshold_is_bound(self) -> MetricResult:
        body = {
            "metric_id": self.metric_id,
            "threshold": self.threshold,
            "threshold_version": self.threshold_version,
        }
        expected = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.threshold_digest != expected:
            raise ValueError("metric threshold digest mismatch")
        return self


class ProductCheckResult(BaseModel):
    check_id: str = Field(min_length=1)
    decision: SceneDecision
    evidence: dict[str, object] = Field(default_factory=dict)


class RegistrationResult(BaseModel):
    decision: SceneDecision
    algorithm_id: str = Field(min_length=1)
    algorithm_version: str = Field(min_length=1)
    transform: list[float]
    confidence: float = Field(ge=0, le=1)
    registered_output: bytes = Field(exclude=True)


class SceneProductVerifierReceipt(BaseModel):
    receipt_id: str = Field(min_length=1)
    verifier_id: str = Field(min_length=1)
    verifier_version: str = Field(min_length=1)
    parent_scene_asset_id: str = Field(min_length=1)
    parent_scene_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    envelope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mask_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration: dict[str, object]
    outside_pixel_metrics: dict[str, object]
    lpips_artifact: PinnedModelArtifact
    lpips_result: MetricResult
    dinov2_artifact: PinnedModelArtifact
    dinov2_result: MetricResult
    product_checks: list[ProductCheckResult]
    task_binding: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    decision: SceneDecision
    verified_at: datetime
    receipt_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def digest_is_valid(self) -> SceneProductVerifierReceipt:
        body = self.model_dump(mode="json", exclude={"receipt_digest"})
        expected = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.receipt_digest != expected:
            raise ValueError("scene verifier receipt digest mismatch")
        return self


class RegistrationBackend(Protocol):
    def register(self, *, parent: bytes, candidate: bytes) -> RegistrationResult: ...


class PerceptualMetricBackend(Protocol):
    artifact: PinnedModelArtifact

    def compare(self, *, parent: bytes, candidate: bytes, protected_mask: bytes) -> MetricResult: ...


class SemanticMetricBackend(Protocol):
    artifact: PinnedModelArtifact

    def compare(self, *, parent: bytes, candidate: bytes, protected_mask: bytes) -> MetricResult: ...


class ProductCheckBackend(Protocol):
    def check(
        self, *, parent: bytes, candidate: bytes, protected_mask: bytes
    ) -> list[ProductCheckResult]: ...


class SceneReceiptLedger(Protocol):
    def persist_scene_product_verification(self, receipt: dict[str, object]) -> None: ...


class ExactFrameRegistration:
    """Deterministic registration that refuses geometry or crop ambiguity."""

    def register(self, *, parent: bytes, candidate: bytes) -> RegistrationResult:
        with Image.open(io.BytesIO(parent)) as before, Image.open(io.BytesIO(candidate)) as after:
            if before.size != after.size:
                return RegistrationResult(
                    decision=SceneDecision.INDETERMINATE,
                    algorithm_id="exact-frame-registration",
                    algorithm_version="1",
                    transform=[1, 0, 0, 0, 1, 0],
                    confidence=0,
                    registered_output=candidate,
                )
        return RegistrationResult(
            decision=SceneDecision.PASS,
            algorithm_id="exact-frame-registration",
            algorithm_version="1",
            transform=[1, 0, 0, 0, 1, 0],
            confidence=1,
            registered_output=candidate,
        )


class SceneProductVerifierV1:
    REQUIRED_PRODUCT_CHECKS = {
        "vehicle_region_continuity",
        "vehicle_component_substitution",
        "customer_region_preservation",
        "object_count_presence",
        "protected_region_correspondence",
    }

    def __init__(
        self,
        *,
        assets: ImageAssetResolver,
        ledger: SceneReceiptLedger,
        lpips: PerceptualMetricBackend,
        dinov2: SemanticMetricBackend,
        product_checks: ProductCheckBackend,
        registration: RegistrationBackend | None = None,
        pixel_channel_tolerance: int = 0,
        max_outside_changed_ratio: float = 0,
    ):
        lpips.artifact.verify_file()
        dinov2.artifact.verify_file()
        self.assets = assets
        self.ledger = ledger
        self.lpips = lpips
        self.dinov2 = dinov2
        self.product_checks = product_checks
        self.registration = registration or ExactFrameRegistration()
        self.pixel_channel_tolerance = pixel_channel_tolerance
        self.max_outside_changed_ratio = max_outside_changed_ratio

    def verify(
        self, *, request: ImageExecutionRequest, output: bytes, attempt_id: str
    ) -> QualifiedOutputVerification:
        if not attempt_id:
            raise SceneVerificationError("SCENE_VERIFIER_ATTEMPT_BINDING_MISSING")
        envelope = request.locality_envelope
        scene_inputs = [item for item in request.inputs if item.role is IdentitySourceRole.SCENE_BASE]
        if envelope is None or len(scene_inputs) != 1:
            raise SceneVerificationError("SCENE_VERIFIER_PARENT_BINDING_MISSING")
        scene_input = scene_inputs[0]
        parent = self.assets.resolve(scene_input.asset_id)
        mask = self.assets.resolve(envelope.mask_asset_id)
        if (
            hashlib.sha256(parent.content).hexdigest() != scene_input.sha256
            or envelope.source_asset_id != scene_input.asset_id
            or envelope.source_sha256 != scene_input.sha256
        ):
            raise SceneVerificationError("SCENE_VERIFIER_STALE_PARENT_BINDING")
        if hashlib.sha256(mask.content).hexdigest() != envelope.mask_sha256:
            raise SceneVerificationError("SCENE_VERIFIER_MASK_DIGEST_MISMATCH")

        registration = self.registration.register(parent=parent.content, candidate=output)
        output_sha256 = hashlib.sha256(output).hexdigest()
        protected_mask = mask.content
        pixel = self._outside_pixels(parent.content, registration.registered_output, protected_mask)
        hard = SceneDecision(pixel["changed_ratio"] <= self.max_outside_changed_ratio and "PASS" or "FAIL")
        if registration.decision is not SceneDecision.PASS:
            hard = SceneDecision.INDETERMINATE
        lpips_result = self.lpips.compare(
            parent=parent.content,
            candidate=registration.registered_output,
            protected_mask=protected_mask,
        )
        dinov2_result = self.dinov2.compare(
            parent=parent.content,
            candidate=registration.registered_output,
            protected_mask=protected_mask,
        )
        checks = self.product_checks.check(
            parent=parent.content,
            candidate=registration.registered_output,
            protected_mask=protected_mask,
        )
        if {item.check_id for item in checks} != self.REQUIRED_PRODUCT_CHECKS:
            raise SceneVerificationError("SCENE_VERIFIER_PRODUCT_CHECK_SET_MISMATCH")
        decisions = [hard, lpips_result.decision, dinov2_result.decision, *(x.decision for x in checks)]
        decision = (
            SceneDecision.FAIL
            if SceneDecision.FAIL in decisions
            else SceneDecision.INDETERMINATE
            if SceneDecision.INDETERMINATE in decisions
            else SceneDecision.PASS
        )
        envelope_body = envelope.model_dump(mode="json")
        envelope_digest = hashlib.sha256(
            json.dumps(envelope_body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        body = {
            "receipt_id": str(uuid4()),
            "verifier_id": "scene-product-verifier-v1",
            "verifier_version": "1",
            "parent_scene_asset_id": scene_input.asset_id,
            "parent_scene_sha256": scene_input.sha256,
            "candidate_output_sha256": output_sha256,
            "envelope_digest": envelope_digest,
            "mask_sha256": envelope.mask_sha256,
            "registration": registration.model_dump(mode="json", exclude={"registered_output"}),
            "outside_pixel_metrics": {**pixel, "decision": hard.value},
            "lpips_artifact": self.lpips.artifact.model_dump(mode="json"),
            "lpips_result": lpips_result.model_dump(mode="json"),
            "dinov2_artifact": self.dinov2.artifact.model_dump(mode="json"),
            "dinov2_result": dinov2_result.model_dump(mode="json"),
            "product_checks": [item.model_dump(mode="json") for item in checks],
            "task_binding": request.task_binding,
            "workflow_id": request.workflow_id,
            "slot_id": request.slot_id,
            "stage": request.stage.value,
            "attempt_id": attempt_id,
            "decision": decision.value,
            "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        receipt = SceneProductVerifierReceipt.model_validate(
            {
                **body,
                "receipt_digest": hashlib.sha256(
                    json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        )
        self.ledger.persist_scene_product_verification(receipt.model_dump(mode="json"))
        return QualifiedOutputVerification(
            verifier_id=receipt.verifier_id,
            verifier_version=receipt.verifier_version,
            task_binding=request.task_binding,
            workflow_id=request.workflow_id,
            slot_id=request.slot_id,
            output_sha256=output_sha256,
            passed=decision is SceneDecision.PASS,
            evidence={"decision": decision.value, "receipt": receipt.model_dump(mode="json")},
        )

    def _outside_pixels(self, parent: bytes, candidate: bytes, mask: bytes) -> dict[str, object]:
        with Image.open(io.BytesIO(parent)) as a, Image.open(io.BytesIO(candidate)) as b, Image.open(
            io.BytesIO(mask)
        ) as m:
            before, after = a.convert("RGBA"), b.convert("RGBA")
            edit_mask = m.getchannel("A") if "A" in m.getbands() else m.convert("L")
            if before.size != after.size or before.size != edit_mask.size:
                return {"outside_pixels": 0, "outside_changed_pixels": 0, "changed_ratio": 1.0}
            outside = changed = 0
            for x in range(before.width):
                for y in range(before.height):
                    if edit_mask.getpixel((x, y)) == 0:
                        continue
                    outside += 1
                    deltas = zip(
                        before.getpixel((x, y)),
                        after.getpixel((x, y)),
                        strict=True,
                    )
                    if max(abs(left - right) for left, right in deltas) > self.pixel_channel_tolerance:
                        changed += 1
            return {
                "outside_pixels": outside,
                "outside_changed_pixels": changed,
                "changed_ratio": changed / outside if outside else 0.0,
                "channel_tolerance": self.pixel_channel_tolerance,
                "max_changed_ratio": self.max_outside_changed_ratio,
            }
