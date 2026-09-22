"""Server-owned OpenAI Images adapter for RD-014 bound execution.

The adapter records the exact transport payload it constructs.  The receipt
attests to adapter egress only; it does not attest to provider-side use of an
input or to identity preservation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from PIL import Image
from pydantic import BaseModel, Field, model_validator

from global_hybrid_v2.image_surface import (
    IdentitySourceRole,
    ImageExecutionInput,
    ImageExecutionRequest,
    ImageOperationMode,
    ImagePortCapabilities,
    ImagePortInputReceipt,
    ImageRenderOutcome,
    ImageSurfaceFingerprint,
    ImageToolFamily,
)


class OpenAIAdapterError(RuntimeError):
    """Typed fail-closed adapter error."""


class ResolvedImageAsset(BaseModel):
    asset_id: str = Field(min_length=1)
    content: bytes
    media_type: str = Field(min_length=1)
    current: bool = True
    generated: bool = False
    authoritative_roles: set[IdentitySourceRole] = Field(default_factory=set)


class ImageAssetResolver(Protocol):
    def resolve(self, asset_id: str) -> ResolvedImageAsset: ...


class OpenAITransportImage(BaseModel):
    asset_id: str
    role: IdentitySourceRole
    source_authority_role: IdentitySourceRole
    sha256: str
    filename: str
    media_type: str
    content: bytes


class OpenAITransportBinding(BaseModel):
    asset_id: str
    role: IdentitySourceRole
    source_authority_role: IdentitySourceRole
    sha256: str


class OpenAIImagesTransportRequest(BaseModel):
    endpoint: str
    model: str
    request_id: str
    operation_mode: ImageOperationMode
    prompt: str
    images: list[OpenAITransportImage]
    mask_asset_id: str | None = None
    mask_sha256: str | None = None
    mask_filename: str | None = None
    mask_media_type: str | None = None
    mask_content: bytes | None = None
    output_settings: dict[str, object] = Field(default_factory=dict)


class OpenAIImagesTransportResult(BaseModel):
    output_bytes: bytes
    reported_output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_operation_id: str | None = None
    provider_response_id: str | None = None


class OpenAIImagesTransport(Protocol):
    def execute(self, request: OpenAIImagesTransportRequest) -> OpenAIImagesTransportResult: ...


class VerificationResult(BaseModel):
    passed: bool
    evidence: dict[str, object] = Field(default_factory=dict)


class QualifiedOutputVerification(BaseModel):
    verifier_id: str = Field(min_length=1)
    verifier_version: str = Field(min_length=1)
    task_binding: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    passed: bool
    evidence: dict[str, object] = Field(default_factory=dict)


class OpenAIAdapterCapabilitySnapshot(BaseModel):
    snapshot_id: str
    adapter_id: str
    adapter_version: str
    generate: bool
    edit: bool
    targeted_edit: bool
    multiple_reference_input: bool
    mask_input: bool
    source_binding_receipt: bool
    output_digest_available: bool
    provider_typed_role_enforcement: bool = False
    provider_digest_binding: bool = False
    exact_mask_enforcement: bool = False


class OutsideEnvelopeVerifier(Protocol):
    def verify(
        self, *, parent: bytes, mask: bytes, output: bytes, tolerance: float
    ) -> VerificationResult: ...


class OutputVerifier(Protocol):
    def verify(
        self, *, request: ImageExecutionRequest, output: bytes, attempt_id: str
    ) -> QualifiedOutputVerification: ...


class FileAssetCatalogEntry(BaseModel):
    asset_id: str
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str
    authoritative_roles: set[IdentitySourceRole]
    current: bool = True
    generated: bool = False


class FileImageAssetResolver:
    """Resolve immutable assets from an application-owned catalog and root."""

    def __init__(self, root: str | Path, entries: list[FileAssetCatalogEntry]):
        self.root = Path(root).resolve()
        self.entries = {entry.asset_id: entry for entry in entries}
        if len(self.entries) != len(entries):
            raise ValueError("duplicate image asset catalog ID")

    def resolve(self, asset_id: str) -> ResolvedImageAsset:
        try:
            entry = self.entries[asset_id]
        except KeyError as exc:
            raise OpenAIAdapterError("IMAGE_ASSET_NOT_FOUND") from exc
        path = (self.root / entry.relative_path).resolve()
        if self.root not in path.parents:
            raise OpenAIAdapterError("IMAGE_ASSET_PATH_ESCAPE")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry.sha256:
            raise OpenAIAdapterError("IMAGE_ASSET_CATALOG_DIGEST_MISMATCH")
        return ResolvedImageAsset(
            asset_id=entry.asset_id,
            content=content,
            media_type=entry.media_type,
            current=entry.current,
            generated=entry.generated,
            authoritative_roles=entry.authoritative_roles,
        )


class OpenAIActualInputReceipt(BaseModel):
    receipt_id: str
    endpoint: str
    model: str
    request_id: str
    attempt_id: str
    workflow_id: str
    slot_id: str
    stage: str
    task_binding: str
    packet_digest: str
    operation_mode: ImageOperationMode
    capability_snapshot_id: str
    ordered_inputs: list[OpenAITransportBinding]
    mask_asset_id: str | None = None
    mask_sha256: str | None = None
    output_settings: dict[str, object]
    prompt_sha256: str
    serialized_metadata_sha256: str
    state: str = "SENT"


class OpenAIOutputLineage(BaseModel):
    lineage_id: str
    receipt_id: str
    workflow_id: str
    slot_id: str
    stage: str
    attempt_id: str
    task_binding: str
    operation_mode: ImageOperationMode
    capability_snapshot_id: str
    packet_digest: str
    parent_scene_asset_id: str | None
    ingredient_asset_ids: list[str]
    output_artifact_id: str
    output_sha256: str
    provider_operation_id: str | None = None
    provider_response_id: str | None = None
    accepted: bool
    verification_evidence: dict[str, object]
    lineage_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def digest_is_bound(self) -> OpenAIOutputLineage:
        payload = self.model_dump(mode="json", exclude={"lineage_digest"})
        expected = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if self.lineage_digest != expected:
            raise ValueError("OpenAI output lineage digest mismatch")
        return self


class OpenAIExecutionLedger(Protocol):
    def begin_openai_image_execution(self, receipt: dict[str, object]) -> None: ...

    def finish_openai_image_execution(
        self, receipt_id: str, *, state: str, lineage: dict[str, object] | None
    ) -> None: ...


class PillowOutsideEnvelopeVerifier:
    """Compare decoded pixels outside the provider mask."""

    def verify(
        self, *, parent: bytes, mask: bytes, output: bytes, tolerance: float
    ) -> VerificationResult:
        import io

        with Image.open(io.BytesIO(parent)) as parent_image, Image.open(
            io.BytesIO(mask)
        ) as mask_image, Image.open(io.BytesIO(output)) as output_image:
            before = parent_image.convert("RGBA")
            after = output_image.convert("RGBA")
            edit_mask = (
                mask_image.getchannel("A")
                if "A" in mask_image.getbands()
                else mask_image.convert("L")
            )
            if before.size != after.size or before.size != edit_mask.size:
                return VerificationResult(
                    passed=False, evidence={"reason": "IMAGE_DIMENSION_MISMATCH"}
                )
            changed = 0
            outside = 0
            max_delta = max(0, min(255, round(tolerance * 255)))
            before_pixels = before.load()
            after_pixels = after.load()
            mask_pixels = edit_mask.load()
            for y in range(before.height):
                for x in range(before.width):
                    # OpenAI edits transparent mask pixels. Opaque pixels are
                    # outside the authorized edit area and must be preserved.
                    if mask_pixels[x, y] == 0:
                        continue
                    outside += 1
                    if (
                        max(
                            abs(a - b)
                            for a, b in zip(
                                before_pixels[x, y], after_pixels[x, y], strict=True
                            )
                        )
                        > max_delta
                    ):
                        changed += 1
            return VerificationResult(
                passed=changed == 0,
                evidence={
                    "outside_pixels": outside,
                    "outside_changed_pixels": changed,
                    "channel_tolerance": tolerance,
                },
            )


@dataclass
class OpenAIHTTPImagesTransport:
    """Direct Images API transport. Tests inject a recording transport."""

    api_key: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 120.0

    def execute(self, request: OpenAIImagesTransportRequest) -> OpenAIImagesTransportResult:
        if request.endpoint != "/images/edits":
            raise OpenAIAdapterError("OPENAI_GENERATE_REFERENCE_ROUTE_NOT_ADMITTED")
        boundary = f"----global-hybrid-{uuid4().hex}"
        body = self._multipart(request, boundary)
        http_request = urllib.request.Request(
            f"{self.base_url}{request.endpoint}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Idempotency-Key": request.request_id,
            },
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read())
                provider_response_id = response.headers.get("x-request-id")
        except (OSError, urllib.error.HTTPError, ValueError) as exc:
            raise OpenAIAdapterError("OPENAI_IMAGE_PROVIDER_OUTCOME_UNKNOWN") from exc
        data = payload.get("data") or []
        if not data or not data[0].get("b64_json"):
            raise OpenAIAdapterError("OPENAI_IMAGE_OUTPUT_MISSING")
        return OpenAIImagesTransportResult(
            output_bytes=base64.b64decode(data[0]["b64_json"], validate=True),
            provider_operation_id=payload.get("id"),
            provider_response_id=provider_response_id,
        )

    @staticmethod
    def _multipart(request: OpenAIImagesTransportRequest, boundary: str) -> bytes:
        chunks: list[bytes] = []

        def field(name: str, value: str) -> None:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                    value.encode(),
                    b"\r\n",
                ]
            )

        def file(name: str, filename: str, media_type: str, content: bytes) -> None:
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    (
                        f'Content-Disposition: form-data; name="{name}"; '
                        f'filename="{filename}"\r\n'
                    ).encode(),
                    f"Content-Type: {media_type}\r\n\r\n".encode(),
                    content,
                    b"\r\n",
                ]
            )

        field("model", request.model)
        field("prompt", request.prompt)
        for key, value in request.output_settings.items():
            field(key, str(value))
        for image in request.images:
            file("image[]", image.filename, image.media_type, image.content)
        if request.mask_content is not None:
            file(
                "mask",
                request.mask_filename or "mask.png",
                request.mask_media_type or "image/png",
                request.mask_content,
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks)


class OpenAIBoundImageExecutionPort:
    PORT_ID = "openai-images-bound-v1"
    PORT_VERSION = "1"
    SNAPSHOT_ID = "openai-images-edits-v1"

    def __init__(
        self,
        *,
        assets: ImageAssetResolver,
        transport: OpenAIImagesTransport,
        ledger: OpenAIExecutionLedger,
        identity_verifier: OutputVerifier,
        scene_product_verifier: OutputVerifier,
        outside_verifier: OutsideEnvelopeVerifier | None = None,
        model: str = "gpt-image-1",
        outside_tolerance: float = 0.0,
    ):
        self.assets = assets
        self.transport = transport
        self.ledger = ledger
        self.identity_verifier = identity_verifier
        self.scene_product_verifier = scene_product_verifier
        self.outside_verifier = outside_verifier or PillowOutsideEnvelopeVerifier()
        self.model = model
        self.outside_tolerance = outside_tolerance

    def fingerprint(self) -> ImageSurfaceFingerprint:
        return ImageSurfaceFingerprint(
            surface_family=self.PORT_ID,
            tool_family=ImageToolFamily.IMAGE_GENERATION,
            observable_model_revision=self.model,
            exposed_reference_controls=["ordered-multipart-images", "server-role-manifest"],
            exposed_edit_controls=["/images/edits"],
            exposed_locality_controls=["mask-bound-to-image-0", "outside-mask-verifier"],
            output_visibility_behavior="OUTPUT_BYTES_SERVER_VISIBLE",
            source_binding_receipt_available=True,
            authorized_envelope_enforcement_available=True,
        )

    def describe_capabilities(self) -> ImagePortCapabilities:
        return ImagePortCapabilities(
            snapshot_id=self.SNAPSHOT_ID,
            port_id=self.PORT_ID,
            port_version=self.PORT_VERSION,
            supported_operation_modes={ImageOperationMode.EDIT, ImageOperationMode.TARGETED_EDIT},
            supported_reference_roles=set(IdentitySourceRole),
            max_reference_inputs=16,
            typed_reference_roles=True,
            mask_input=True,
            source_binding_receipt=True,
            outside_region_verification=True,
        )

    def capability_snapshot(self) -> OpenAIAdapterCapabilitySnapshot:
        return OpenAIAdapterCapabilitySnapshot(
            snapshot_id=self.SNAPSHOT_ID,
            adapter_id=self.PORT_ID,
            adapter_version=self.PORT_VERSION,
            generate=False,
            edit=True,
            targeted_edit=True,
            multiple_reference_input=True,
            mask_input=True,
            source_binding_receipt=True,
            output_digest_available=True,
        )

    def invoke(self, **_kwargs):
        raise OpenAIAdapterError("BOUND_EXECUTION_REQUEST_REQUIRED")

    def invoke_bound(
        self, *, request: ImageExecutionRequest, node_token: str
    ) -> ImageRenderOutcome:
        if request.capability_snapshot_id != self.SNAPSHOT_ID:
            raise OpenAIAdapterError("CAPABILITY_SNAPSHOT_MISMATCH")
        if request.operation_mode not in {ImageOperationMode.EDIT, ImageOperationMode.TARGETED_EDIT}:
            raise OpenAIAdapterError("OPENAI_IMAGE_OPERATION_UNSUPPORTED")
        ordered = self._ordered_inputs(request.inputs)
        resolved = [self._resolve(item) for item in ordered]
        scene = ordered[0]
        envelope = request.locality_envelope
        mask_asset = None
        if request.operation_mode is ImageOperationMode.TARGETED_EDIT:
            if envelope is None or envelope.source_asset_id != scene.asset_id:
                raise OpenAIAdapterError("MASK_PARENT_BINDING_MISMATCH")
            mask_asset = self.assets.resolve(envelope.mask_asset_id)
            self._verify_asset(mask_asset, envelope.mask_sha256, "MASK_DIGEST_MISMATCH")
        elif envelope is not None:
            raise OpenAIAdapterError("EDIT_MODE_ENVELOPE_MISMATCH")

        transport_request = self._transport_request(
            request=request,
            node_token=node_token,
            ordered=ordered,
            resolved=resolved,
            mask=mask_asset,
        )
        receipt = self._actual_input_receipt(request, node_token, transport_request)
        self.ledger.begin_openai_image_execution(receipt.model_dump(mode="json"))
        try:
            result = self.transport.execute(transport_request)
        except Exception:
            self.ledger.finish_openai_image_execution(
                receipt.receipt_id, state="PROVIDER_OUTCOME_UNKNOWN", lineage=None
            )
            raise
        if not result.output_bytes:
            self.ledger.finish_openai_image_execution(
                receipt.receipt_id, state="OUTPUT_MISSING", lineage=None
            )
            raise OpenAIAdapterError("OPENAI_IMAGE_OUTPUT_MISSING")

        output_sha256 = hashlib.sha256(result.output_bytes).hexdigest()
        if (
            result.reported_output_sha256 is not None
            and result.reported_output_sha256 != output_sha256
        ):
            self.ledger.finish_openai_image_execution(
                receipt.receipt_id, state="OUTPUT_DIGEST_MISMATCH", lineage=None
            )
            raise OpenAIAdapterError("OPENAI_IMAGE_OUTPUT_DIGEST_MISMATCH")
        artifact_id = f"sha256:{output_sha256}"
        try:
            identity = self.identity_verifier.verify(
                request=request, output=result.output_bytes, attempt_id=node_token
            )
            scene_result = self.scene_product_verifier.verify(
                request=request, output=result.output_bytes, attempt_id=node_token
            )
            self._verify_output_receipt(identity, request, output_sha256)
            self._verify_output_receipt(scene_result, request, output_sha256)
        except Exception:
            self.ledger.finish_openai_image_execution(
                receipt.receipt_id, state="VERIFIER_EVIDENCE_INVALID", lineage=None
            )
            raise
        outside = VerificationResult(passed=True, evidence={"not_applicable": True})
        if envelope is not None and mask_asset is not None:
            outside = self.outside_verifier.verify(
                parent=resolved[0].content,
                mask=mask_asset.content,
                output=result.output_bytes,
                tolerance=self.outside_tolerance,
            )
        accepted = identity.passed and scene_result.passed and outside.passed
        evidence = {
            "identity": identity.model_dump(mode="json"),
            "scene_product": scene_result.model_dump(mode="json"),
            "outside_envelope": outside.model_dump(mode="json"),
        }
        lineage_body = {
            "lineage_id": str(uuid4()),
            "receipt_id": receipt.receipt_id,
            "workflow_id": request.workflow_id,
            "slot_id": request.slot_id,
            "stage": request.stage.value,
            "attempt_id": node_token,
            "task_binding": request.task_binding,
            "operation_mode": request.operation_mode.value,
            "capability_snapshot_id": request.capability_snapshot_id,
            "packet_digest": request.packet_digest,
            "parent_scene_asset_id": scene.asset_id,
            "ingredient_asset_ids": [item.asset_id for item in ordered[1:]],
            "output_artifact_id": artifact_id,
            "output_sha256": output_sha256,
            "provider_operation_id": result.provider_operation_id,
            "provider_response_id": result.provider_response_id,
            "accepted": accepted,
            "verification_evidence": evidence,
        }
        lineage = OpenAIOutputLineage.model_validate(
            {
                **lineage_body,
                "lineage_digest": hashlib.sha256(
                    json.dumps(
                        lineage_body,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
        )
        self.ledger.finish_openai_image_execution(
            receipt.receipt_id,
            state="ACCEPTED" if accepted else "REJECTED",
            lineage=lineage.model_dump(mode="json"),
        )
        envelope_fields = {}
        if envelope is not None:
            envelope_fields = {
                "source_asset_id": envelope.source_asset_id,
                "source_sha256": envelope.source_sha256,
                "applied_region_id": envelope.region_id,
                "applied_mask_sha256": envelope.mask_sha256,
                "applied_transform_chain_digest": (
                    envelope.spatial_binding.transform_chain_digest
                ),
                "applied_current_artifact_frame_id": (
                    envelope.spatial_binding.current_artifact_frame_id
                ),
                "outside_envelope_changed_pixels": int(
                    outside.evidence.get("outside_changed_pixels", 0)
                ),
            }
        return ImageRenderOutcome(
            artifact_id=artifact_id,
            artifact_sha256=output_sha256,
            provider_operation_id=result.provider_operation_id or result.provider_response_id,
            input_receipt=ImagePortInputReceipt(
                capability_snapshot_id=request.capability_snapshot_id,
                workflow_id=request.workflow_id,
                slot_id=request.slot_id,
                operation_mode=request.operation_mode,
                task_binding=request.task_binding,
                packet_digest=request.packet_digest,
                inputs=request.inputs,
            ),
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=scene_result.passed,
            changed_regions={request.manifest.current_visual_delta} if accepted else set(),
            protected_state_changed=set() if outside.passed else {"OUTSIDE_ENVELOPE"},
            identity_preserved=identity.passed,
            preservation_pass=outside.passed and scene_result.passed,
            net_uplift_pass=accepted,
            **envelope_fields,
        )

    def _resolve(self, source: ImageExecutionInput) -> ResolvedImageAsset:
        asset = self.assets.resolve(source.asset_id)
        self._verify_asset(asset, source.sha256, "SOURCE_DIGEST_MISMATCH")
        if source.role not in asset.authoritative_roles:
            raise OpenAIAdapterError("SOURCE_ROLE_AUTHORITY_MISMATCH")
        if source.role is IdentitySourceRole.ORIGINAL_REAL_MASTER and asset.generated:
            raise OpenAIAdapterError("GENERATED_IMAGE_CANNOT_BE_MASTER")
        return asset

    @staticmethod
    def _verify_asset(asset: ResolvedImageAsset, expected: str, blocker: str) -> None:
        if not asset.current:
            raise OpenAIAdapterError("STALE_SOURCE_ASSET")
        if hashlib.sha256(asset.content).hexdigest() != expected:
            raise OpenAIAdapterError(blocker)

    @staticmethod
    def _ordered_inputs(inputs: list[ImageExecutionInput]) -> list[ImageExecutionInput]:
        by_role: dict[IdentitySourceRole, list[ImageExecutionInput]] = {}
        for item in inputs:
            by_role.setdefault(item.role, []).append(item)
        for required in (
            IdentitySourceRole.SCENE_BASE,
            IdentitySourceRole.ORIGINAL_REAL_MASTER,
        ):
            if len(by_role.get(required, [])) != 1:
                raise OpenAIAdapterError(f"EXACT_{required.value}_REQUIRED")
        if by_role.get(IdentitySourceRole.SELLER):
            raise OpenAIAdapterError("SECONDARY_SELLER_IDENTITY_AUTHORITY_FORBIDDEN")
        order = [
            IdentitySourceRole.SCENE_BASE,
            IdentitySourceRole.ORIGINAL_REAL_MASTER,
            IdentitySourceRole.BODY,
            IdentitySourceRole.TATTOO,
            IdentitySourceRole.POSE,
        ]
        return [item for role in order for item in by_role.get(role, [])]

    @staticmethod
    def _verify_output_receipt(
        result: QualifiedOutputVerification,
        request: ImageExecutionRequest,
        output_sha256: str,
    ) -> None:
        if (
            result.task_binding != request.task_binding
            or result.workflow_id != request.workflow_id
            or result.slot_id != request.slot_id
            or result.output_sha256 != output_sha256
        ):
            raise OpenAIAdapterError("OUTPUT_VERIFIER_BINDING_MISMATCH")

    def _transport_request(
        self,
        *,
        request: ImageExecutionRequest,
        node_token: str,
        ordered: list[ImageExecutionInput],
        resolved: list[ResolvedImageAsset],
        mask: ResolvedImageAsset | None,
    ) -> OpenAIImagesTransportRequest:
        images = [
            OpenAITransportImage(
                asset_id=source.asset_id,
                role=(
                    IdentitySourceRole.SELLER
                    if source.role is IdentitySourceRole.ORIGINAL_REAL_MASTER
                    else source.role
                ),
                source_authority_role=source.role,
                sha256=source.sha256,
                filename=f"{index}-{source.asset_id}{mimetypes.guess_extension(asset.media_type) or '.bin'}",
                media_type=asset.media_type,
                content=asset.content,
            )
            for index, (source, asset) in enumerate(zip(ordered, resolved, strict=True))
        ]
        role_manifest = ", ".join(
            f"image[{index}]={image.role.value}:{image.asset_id}"
            for index, image in enumerate(images)
        )
        prompt = (
            f"{request.manifest.visual_subject}. {request.manifest.current_visual_delta}. "
            f"Server input map: {role_manifest}."
        )
        return OpenAIImagesTransportRequest(
            endpoint="/images/edits",
            model=self.model,
            request_id=node_token,
            operation_mode=request.operation_mode,
            prompt=prompt,
            images=images,
            mask_asset_id=mask.asset_id if mask else None,
            mask_sha256=(hashlib.sha256(mask.content).hexdigest() if mask else None),
            mask_filename=f"mask-{mask.asset_id}.png" if mask else None,
            mask_media_type=mask.media_type if mask else None,
            mask_content=mask.content if mask else None,
            output_settings={"size": "1024x1024", "output_format": "png"},
        )

    @staticmethod
    def _actual_input_receipt(
        request: ImageExecutionRequest,
        node_token: str,
        transport: OpenAIImagesTransportRequest,
    ) -> OpenAIActualInputReceipt:
        metadata = {
            "endpoint": transport.endpoint,
            "model": transport.model,
            "request_id": transport.request_id,
            "operation_mode": transport.operation_mode.value,
            "inputs": [
                {
                    "asset_id": item.asset_id,
                    "role": item.role.value,
                    "source_authority_role": item.source_authority_role.value,
                    "sha256": item.sha256,
                }
                for item in transport.images
            ],
            "mask_asset_id": transport.mask_asset_id,
            "mask_sha256": transport.mask_sha256,
            "output_settings": transport.output_settings,
            "prompt_sha256": hashlib.sha256(transport.prompt.encode()).hexdigest(),
        }
        digest = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return OpenAIActualInputReceipt(
            receipt_id=str(uuid4()),
            endpoint=transport.endpoint,
            model=transport.model,
            request_id=transport.request_id,
            attempt_id=node_token,
            workflow_id=request.workflow_id,
            slot_id=request.slot_id,
            stage=request.stage.value,
            task_binding=request.task_binding,
            packet_digest=request.packet_digest,
            operation_mode=request.operation_mode,
            capability_snapshot_id=request.capability_snapshot_id,
            ordered_inputs=[
                OpenAITransportBinding(
                    asset_id=item.asset_id,
                    role=item.role,
                    source_authority_role=item.source_authority_role,
                    sha256=item.sha256,
                )
                for item in transport.images
            ],
            mask_asset_id=transport.mask_asset_id,
            mask_sha256=transport.mask_sha256,
            output_settings=transport.output_settings,
            prompt_sha256=metadata["prompt_sha256"],
            serialized_metadata_sha256=digest,
        )
