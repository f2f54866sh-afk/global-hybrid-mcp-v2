"""Deterministic admission and acceptance controls for image side effects.

The controller deliberately has no ChatGPT-host integration.  A private ChatGPT
image invocation can bypass this process, so it is recorded as a soft boundary;
only an injected, engineer-controlled port can receive a dispatch token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class ImageRouteFamily(StrEnum):
    GENERATIVE = "GENERATIVE"
    DETERMINISTIC = "DETERMINISTIC"
    STRICT_SOURCE_PRESERVING = "STRICT_SOURCE_PRESERVING"
    SOURCE_ONLY_RETOUCH = "SOURCE_ONLY_RETOUCH"


class ImageToolFamily(StrEnum):
    IMAGE_GENERATION = "IMAGE_GENERATION"
    DETERMINISTIC = "DETERMINISTIC"


class ImageExecutionState(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    CAPABILITY_BOUNDARY = "CAPABILITY_BOUNDARY"


class ImageLocalityMode(StrEnum):
    SOFT_MODEL_GUIDED = "SOFT_MODEL_GUIDED"
    AUTHORIZED_ENVELOPE = "AUTHORIZED_ENVELOPE"


class LocalityEvidenceState(StrEnum):
    VERIFIED = "VERIFIED"
    UNPROVEN = "UNPROVEN"


class SpatialClipState(StrEnum):
    INSIDE_EXPECTED_BOUNDS = "INSIDE_EXPECTED_BOUNDS"
    CLIPPED = "CLIPPED"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"


class ImageRetryAuthorization(StrEnum):
    FIRST_PASS_ONLY = "FIRST_PASS_ONLY"
    EXPLICIT_USER_EXTENSION = "EXPLICIT_USER_EXTENSION"


class ImageSideEffectBudget(BaseModel):
    """Per-source image-call budget supplied by the existing runtime task state.

    This object is not a second state store. It is a typed permit consumed at the
    image execution edge. Attempt 1 is the only default permit. Any later attempt
    must be backed by a current explicit-user authorization receipt.
    """

    source_asset_id: str = Field(min_length=1)
    attempt_number: int = Field(default=1, ge=1)
    authorized_attempt_limit: int = Field(default=1, ge=1)
    authorization: ImageRetryAuthorization = ImageRetryAuthorization.FIRST_PASS_ONLY
    explicit_user_authorization_receipt: str | None = None
    prior_terminal_result_id: str | None = None
    prior_attempt_terminal: bool = True
    unattempted_batch_sources_remaining: int = Field(default=0, ge=0)
    explicit_source_scope_override: bool = False

    @model_validator(mode="after")
    def authorization_is_consistent(self) -> ImageSideEffectBudget:
        if self.authorized_attempt_limit > 1:
            if self.authorization is not ImageRetryAuthorization.EXPLICIT_USER_EXTENSION:
                raise ValueError("retry budget extension requires explicit user authorization")
            if not (self.explicit_user_authorization_receipt or "").strip():
                raise ValueError("retry budget extension requires an authorization receipt")
        elif self.authorization is ImageRetryAuthorization.EXPLICIT_USER_EXTENSION:
            raise ValueError("explicit retry authorization must extend the attempt limit")
        return self


class NormalizedPoint(BaseModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


def _validate_polygon(points: list[NormalizedPoint], *, label: str) -> None:
    tuples = [(point.x, point.y) for point in points]
    area2 = 0.0
    for index, current in enumerate(tuples):
        following = tuples[(index + 1) % len(tuples)]
        area2 += current[0] * following[1] - following[0] * current[1]
    if abs(area2) <= 1e-9:
        raise ValueError(f"{label} polygon must have non-zero area")
    if len(set(tuples)) != len(tuples):
        raise ValueError(f"{label} polygon points must be unique")


class SpatialBindingReceipt(BaseModel):
    """Current REAL_CAR spatial-frame binding projected into the image runtime."""

    target_role: str = Field(min_length=1)
    geometry_source: str = Field(min_length=1)
    source_frame_id: str = Field(min_length=1)
    source_polygon: list[NormalizedPoint] = Field(min_length=3)
    geometry_confidence: float = Field(ge=0.0, le=1.0)
    geometry_confidence_sufficient: bool
    transform_chain_digest: str = Field(min_length=1)
    projected_polygon: list[NormalizedPoint] = Field(min_length=3)
    current_artifact_frame_id: str = Field(min_length=1)
    clip_state: SpatialClipState
    binding_valid: bool
    locator_receipt_id: str = Field(min_length=1)
    locator_evidence_state: LocalityEvidenceState

    @model_validator(mode="after")
    def polygons_are_valid(self) -> SpatialBindingReceipt:
        _validate_polygon(self.source_polygon, label="source binding")
        _validate_polygon(self.projected_polygon, label="projected binding")
        return self


class AuthorizedEditEnvelope(BaseModel):
    """Exact source-bound write authority for a bounded local image edit.

    The write polygon includes only the target plus explicitly authorized
    feather/contact-shadow margin. It is derived from a verified spatial binding;
    the generator is never allowed to infer or expand its own write scope.
    """

    source_asset_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    region_id: str = Field(min_length=1)
    mask_asset_id: str = Field(min_length=1)
    mask_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_semantics: str = Field(min_length=1)
    spatial_binding: SpatialBindingReceipt
    write_polygon: list[NormalizedPoint] = Field(min_length=3)

    @model_validator(mode="after")
    def write_polygon_is_valid(self) -> AuthorizedEditEnvelope:
        _validate_polygon(self.write_polygon, label="authorized edit envelope")
        return self


class ImageSurfaceFingerprint(BaseModel):
    surface_family: str = Field(min_length=1)
    tool_family: ImageToolFamily
    observable_model_revision: str = "UNEXPOSED"
    exposed_reference_controls: list[str] = Field(default_factory=list)
    exposed_edit_controls: list[str] = Field(default_factory=list)
    exposed_locality_controls: list[str] = Field(default_factory=list)
    output_visibility_behavior: str = Field(min_length=1)
    source_binding_receipt_available: bool = False
    authorized_envelope_enforcement_available: bool = False
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def revision_is_explicit_or_unexposed(self) -> ImageSurfaceFingerprint:
        if not self.observable_model_revision.strip():
            raise ValueError("observable model revision must be explicit or UNEXPOSED")
        return self


class ImageCapabilityEvidence(BaseModel):
    route_family: ImageRouteFamily
    model_revision_or_unexposed: str = Field(min_length=1)
    control_surface: str = Field(min_length=1)
    task_scope: str = Field(min_length=1)
    protected_state_class: str = Field(min_length=1)
    current: bool = True


class ReferenceSet(BaseModel):
    identity_reference: list[str] = Field(default_factory=list)
    condition_reference: list[str] = Field(default_factory=list)
    material_reference: list[str] = Field(default_factory=list)
    view_evidence: list[str] = Field(default_factory=list)


class RenderManifest(BaseModel):
    visual_subject: str = Field(min_length=1)
    scene_background_target: str | None = None
    composition_target: str | None = None
    permitted_visible_objects: list[str] = Field(default_factory=list)
    explicitly_authorized_literals: list[str] = Field(default_factory=list)
    current_visual_delta: str = Field(min_length=1)

    @model_validator(mode="after")
    def no_control_metadata(self) -> RenderManifest:
        forbidden = (
            "analysis",
            "checklist",
            "canonical",
            "pass/fail",
            "workflow",
            "diagnostic",
            "witness",
            "engineering instruction",
        )
        content = "\n".join(
            [
                self.visual_subject,
                self.scene_background_target or "",
                self.composition_target or "",
                self.current_visual_delta,
                *self.permitted_visible_objects,
                *self.explicitly_authorized_literals,
            ]
        ).lower()
        if any(item in content for item in forbidden):
            raise ValueError("render manifest contains non-renderable control metadata")
        return self


class ImageTaskSpec(BaseModel):
    task_scope: str = Field(min_length=1)
    reference_set: ReferenceSet
    render_manifest: RenderManifest
    selected_lane: ImageRouteFamily
    allowed_route_families: set[ImageRouteFamily] = Field(min_length=1)
    forbidden_route_families: set[ImageRouteFamily] = Field(default_factory=set)
    allowed_tool_family: ImageToolFamily
    protected_state: set[str] = Field(min_length=1)
    capability_evidence: list[ImageCapabilityEvidence] = Field(min_length=1)
    output_count: int = Field(default=1, ge=1)
    explicit_multi_output_authorized: bool = False
    negative_evidence: list[ImageCapabilityEvidence] = Field(default_factory=list)
    locality_mode: ImageLocalityMode = ImageLocalityMode.SOFT_MODEL_GUIDED
    authorized_edit_envelope: AuthorizedEditEnvelope | None = None
    side_effect_budget: ImageSideEffectBudget | None = None

    @model_validator(mode="after")
    def routes_are_admissible(self) -> ImageTaskSpec:
        if self.selected_lane not in self.allowed_route_families:
            raise ValueError("selected lane is not allowed")
        if self.selected_lane in self.forbidden_route_families:
            raise ValueError("selected lane is forbidden by current user constraint")
        if self.allowed_route_families & self.forbidden_route_families:
            raise ValueError("a route cannot be both allowed and forbidden")
        if self.output_count != 1 and not self.explicit_multi_output_authorized:
            raise ValueError("multiple outputs require explicit current user authorization")
        if (
            self.locality_mode is ImageLocalityMode.AUTHORIZED_ENVELOPE
            and self.authorized_edit_envelope is None
        ):
            raise ValueError("authorized locality mode requires an edit envelope")
        if (
            self.locality_mode is ImageLocalityMode.SOFT_MODEL_GUIDED
            and self.authorized_edit_envelope is not None
        ):
            raise ValueError("soft locality mode cannot carry an authoritative edit envelope")
        return self


class ImageRenderOutcome(BaseModel):
    artifact_id: str | None = None
    actual_tool_family: ImageToolFamily
    requested_delta_completed: bool
    changed_regions: set[str] = Field(default_factory=set)
    protected_state_changed: set[str] = Field(default_factory=set)
    identity_preserved: bool
    preservation_pass: bool
    net_uplift_pass: bool
    source_asset_id: str | None = None
    source_sha256: str | None = None
    applied_region_id: str | None = None
    applied_mask_sha256: str | None = None
    applied_transform_chain_digest: str | None = None
    applied_current_artifact_frame_id: str | None = None
    outside_envelope_changed_pixels: int | None = Field(default=None, ge=0)


class ImageExecutionReceipt(BaseModel):
    state: ImageExecutionState
    node_token: str | None = None
    enforcement: str
    fingerprint: ImageSurfaceFingerprint
    render_manifest: RenderManifest
    admitted_tool_family: ImageToolFamily
    actual_invoked_tool_family: ImageToolFamily | None = None
    user_constraint_receipt: dict[str, object]
    audit: dict[str, object]
    blocker: str | None = None


class ImageExecutionPort(Protocol):
    def fingerprint(self) -> ImageSurfaceFingerprint: ...

    def invoke(
        self,
        *,
        manifest: RenderManifest,
        tool_family: ImageToolFamily,
        node_token: str,
        locality_envelope: AuthorizedEditEnvelope | None = None,
    ) -> ImageRenderOutcome: ...


class ImageInvocationGuard(Protocol):
    """Durable reservation edge invoked only after controller preflight passes."""

    def reserve(self, spec: ImageTaskSpec) -> bool: ...

    def complete(self, *, terminal_result_id: str, terminal_status: str) -> None: ...


@dataclass
class UnavailableImageExecutionPort:
    """Production default until a controlled API adapter is configured."""

    def fingerprint(self) -> ImageSurfaceFingerprint:
        return ImageSurfaceFingerprint(
            surface_family="UNAVAILABLE_ENGINEERING_IMAGE_PORT",
            tool_family=ImageToolFamily.IMAGE_GENERATION,
            observable_model_revision="UNEXPOSED",
            output_visibility_behavior="NO_CALLABLE_OUTPUT",
        )

    def invoke(
        self,
        *,
        manifest: RenderManifest,
        tool_family: ImageToolFamily,
        node_token: str,
        locality_envelope: AuthorizedEditEnvelope | None = None,
    ) -> ImageRenderOutcome:
        del locality_envelope
        raise RuntimeError("CAPABILITY_BOUNDARY: no controlled image execution port")


class ImageSurfaceController:
    """The sole pre-call admission point for repository-controlled image effects."""

    def __init__(
        self,
        port: ImageExecutionPort | None = None,
        invocation_guard: ImageInvocationGuard | None = None,
    ):
        self.port = port or UnavailableImageExecutionPort()
        self.invocation_guard = invocation_guard

    def execute(
        self,
        spec: ImageTaskSpec,
        *,
        invocation_guard: ImageInvocationGuard | None = None,
    ) -> ImageExecutionReceipt:
        fingerprint = self.port.fingerprint()
        expected_evidence = ImageCapabilityEvidence(
            route_family=spec.selected_lane,
            model_revision_or_unexposed=fingerprint.observable_model_revision,
            control_surface=fingerprint.surface_family,
            task_scope=spec.task_scope,
            protected_state_class="|".join(sorted(spec.protected_state)),
        )
        envelope = spec.authorized_edit_envelope
        constraints = {
            "allowed_route_families": sorted(item.value for item in spec.allowed_route_families),
            "forbidden_route_families": sorted(item.value for item in spec.forbidden_route_families),
            "output_count": spec.output_count,
            "reference_count": sum(len(value) for value in spec.reference_set.model_dump().values()),
            "locality_mode": spec.locality_mode.value,
            "authorized_region_id": envelope.region_id if envelope else None,
            "authorized_source_asset_id": envelope.source_asset_id if envelope else None,
            "source_frame_id": (
                envelope.spatial_binding.source_frame_id if envelope else None
            ),
            "current_artifact_frame_id": (
                envelope.spatial_binding.current_artifact_frame_id if envelope else None
            ),
            "transform_chain_digest": (
                envelope.spatial_binding.transform_chain_digest if envelope else None
            ),
            "attempt_number": (
                spec.side_effect_budget.attempt_number if spec.side_effect_budget else 1
            ),
            "authorized_attempt_limit": (
                spec.side_effect_budget.authorized_attempt_limit
                if spec.side_effect_budget
                else 1
            ),
        }
        matching_evidence = [
            item
            for item in spec.capability_evidence
            if self._same_evidence_scope(item, expected_evidence)
        ]
        if not matching_evidence:
            return self._blocked(spec, fingerprint, constraints, "CAPABILITY_EVIDENCE_MISMATCH")
        if not matching_evidence[0].current:
            return self._blocked(spec, fingerprint, constraints, "STALE_CAPABILITY_EVIDENCE")
        if any(item == expected_evidence for item in spec.negative_evidence):
            return self._blocked(spec, fingerprint, constraints, "MATCHING_NEGATIVE_EVIDENCE")
        if spec.selected_lane not in spec.allowed_route_families:
            return self._blocked(spec, fingerprint, constraints, "ROUTE_NOT_ALLOWED")
        if spec.selected_lane in spec.forbidden_route_families:
            return self._blocked(spec, fingerprint, constraints, "USER_REJECTED_ROUTE")
        expected = self._tool_for_lane(spec.selected_lane)
        if expected is not spec.allowed_tool_family:
            return self._blocked(spec, fingerprint, constraints, "PLAN_TOOL_FAMILY_MISMATCH")
        if fingerprint.tool_family is not spec.allowed_tool_family:
            return self._blocked(spec, fingerprint, constraints, "SURFACE_TOOL_FAMILY_MISMATCH")

        budget = spec.side_effect_budget
        if budget is not None:
            if envelope is not None and budget.source_asset_id != envelope.source_asset_id:
                return self._blocked(
                    spec, fingerprint, constraints, "SIDE_EFFECT_BUDGET_SOURCE_MISMATCH"
                )
            if budget.attempt_number > budget.authorized_attempt_limit:
                return self._blocked(
                    spec, fingerprint, constraints, "IMAGE_SIDE_EFFECT_BUDGET_EXHAUSTED"
                )
            if budget.attempt_number > 1:
                if budget.authorization is not ImageRetryAuthorization.EXPLICIT_USER_EXTENSION:
                    return self._blocked(
                        spec, fingerprint, constraints, "AUTONOMOUS_IMAGE_RETRY_FORBIDDEN"
                    )
                if not budget.prior_attempt_terminal:
                    return self._blocked(
                        spec, fingerprint, constraints, "PRIOR_IMAGE_ATTEMPT_NOT_TERMINAL"
                    )
                if (
                    budget.unattempted_batch_sources_remaining > 0
                    and not budget.explicit_source_scope_override
                ):
                    return self._blocked(
                        spec, fingerprint, constraints, "BATCH_COVERAGE_REQUIRED_BEFORE_RETRY"
                    )

        if spec.locality_mode is ImageLocalityMode.AUTHORIZED_ENVELOPE:
            assert envelope is not None
            binding = envelope.spatial_binding
            if binding.locator_evidence_state is not LocalityEvidenceState.VERIFIED:
                return self._blocked(
                    spec, fingerprint, constraints, "LOCALITY_LOCATOR_UNVERIFIED"
                )
            if not binding.binding_valid:
                return self._blocked(
                    spec, fingerprint, constraints, "SPATIAL_BINDING_INVALID"
                )
            if not binding.geometry_confidence_sufficient:
                return self._blocked(
                    spec, fingerprint, constraints, "GEOMETRY_CONFIDENCE_INSUFFICIENT"
                )
            if binding.clip_state is not SpatialClipState.INSIDE_EXPECTED_BOUNDS:
                return self._blocked(
                    spec, fingerprint, constraints, "SPATIAL_BINDING_CLIPPED_OR_OUT_OF_BOUNDS"
                )
            if not fingerprint.source_binding_receipt_available:
                return self._blocked(
                    spec, fingerprint, constraints, "SOURCE_BINDING_RECEIPT_UNAVAILABLE"
                )
            if not fingerprint.authorized_envelope_enforcement_available:
                return self._blocked(
                    spec,
                    fingerprint,
                    constraints,
                    "AUTHORIZED_ENVELOPE_ENFORCEMENT_UNAVAILABLE",
                )

        token = str(uuid4())
        guard = invocation_guard or self.invocation_guard
        if guard is not None and not guard.reserve(spec):
            return self._blocked(spec, fingerprint, constraints, "IMAGE_ATTEMPT_RESERVATION_BLOCKED")
        try:
            if envelope is None:
                outcome = self.port.invoke(
                    manifest=spec.render_manifest,
                    tool_family=spec.allowed_tool_family,
                    node_token=token,
                )
            else:
                outcome = self.port.invoke(
                    manifest=spec.render_manifest,
                    tool_family=spec.allowed_tool_family,
                    node_token=token,
                    locality_envelope=envelope,
                )
        except TypeError as exc:
            if envelope is not None:
                receipt = ImageExecutionReceipt(
                    state=ImageExecutionState.CAPABILITY_BOUNDARY,
                    enforcement="ENGINEERING_DISPATCHER_CONTROLLED",
                    fingerprint=fingerprint,
                    render_manifest=spec.render_manifest,
                    admitted_tool_family=spec.allowed_tool_family,
                    user_constraint_receipt=constraints,
                    audit={},
                    blocker=f"LOCALITY_PORT_CONTRACT_MISMATCH: {type(exc).__name__}",
                )
                if guard is not None:
                    guard.complete(terminal_result_id=token, terminal_status=receipt.state.value)
                return receipt
            if guard is not None:
                guard.complete(terminal_result_id=token, terminal_status="ERROR")
            raise
        except RuntimeError as exc:
            receipt = ImageExecutionReceipt(
                state=ImageExecutionState.CAPABILITY_BOUNDARY,
                enforcement="SOFT_AT_CHATGPT_HOST_BOUNDARY",
                fingerprint=fingerprint,
                render_manifest=spec.render_manifest,
                admitted_tool_family=spec.allowed_tool_family,
                user_constraint_receipt=constraints,
                audit={},
                blocker=str(exc),
            )
            if guard is not None:
                guard.complete(terminal_result_id=token, terminal_status=receipt.state.value)
            return receipt
        if outcome.actual_tool_family is not spec.allowed_tool_family:
            receipt = self._blocked(
                spec, fingerprint, constraints, "ACTUAL_TOOL_FAMILY_MISMATCH", token, outcome
            )
            if guard is not None:
                guard.complete(terminal_result_id=token, terminal_status=receipt.state.value)
            return receipt

        non_target = outcome.changed_regions - {spec.render_manifest.current_visual_delta}
        protected_changed = outcome.protected_state_changed & spec.protected_state
        audit: dict[str, object] = {
            "required_modification_pass": outcome.requested_delta_completed,
            "required_preservation_pass": outcome.preservation_pass and outcome.identity_preserved,
            "non_target_regression_pass": not non_target and not protected_changed,
            "net_uplift_pass": outcome.net_uplift_pass,
            "non_target_changed_regions": sorted(non_target),
            "protected_state_changed": sorted(protected_changed),
        }
        locality_checks: tuple[str, ...] = ()
        if envelope is not None:
            audit.update(
                {
                    "locality_source_binding_pass": (
                        outcome.source_asset_id == envelope.source_asset_id
                        and outcome.source_sha256 == envelope.source_sha256
                    ),
                    "locality_region_binding_pass": (
                        outcome.applied_region_id == envelope.region_id
                        and outcome.applied_mask_sha256 == envelope.mask_sha256
                        and outcome.applied_transform_chain_digest
                        == envelope.spatial_binding.transform_chain_digest
                        and outcome.applied_current_artifact_frame_id
                        == envelope.spatial_binding.current_artifact_frame_id
                    ),
                    "outside_envelope_preservation_pass": (
                        outcome.outside_envelope_changed_pixels == 0
                    ),
                    "outside_envelope_changed_pixels": outcome.outside_envelope_changed_pixels,
                    "locator_receipt_id": envelope.spatial_binding.locator_receipt_id,
                    "target_semantics": envelope.target_semantics,
                    "geometry_confidence": envelope.spatial_binding.geometry_confidence,
                    "source_frame_id": envelope.spatial_binding.source_frame_id,
                    "current_artifact_frame_id": (
                        envelope.spatial_binding.current_artifact_frame_id
                    ),
                    "transform_chain_digest": envelope.spatial_binding.transform_chain_digest,
                }
            )
            locality_checks = (
                "locality_source_binding_pass",
                "locality_region_binding_pass",
                "outside_envelope_preservation_pass",
            )

        required_checks = (
            "required_modification_pass",
            "required_preservation_pass",
            "non_target_regression_pass",
            "net_uplift_pass",
            *locality_checks,
        )
        passed = all(bool(audit[key]) for key in required_checks)
        locality_failed = any(not bool(audit[key]) for key in locality_checks)
        receipt = ImageExecutionReceipt(
            state=ImageExecutionState.PASS if passed else ImageExecutionState.FAIL,
            node_token=token,
            enforcement="ENGINEERING_DISPATCHER_CONTROLLED",
            fingerprint=fingerprint,
            render_manifest=spec.render_manifest,
            admitted_tool_family=spec.allowed_tool_family,
            actual_invoked_tool_family=outcome.actual_tool_family,
            user_constraint_receipt=constraints,
            audit=audit,
            blocker=(
                None
                if passed
                else "LOCALITY_ENVELOPE_ACCEPTANCE_FAILED"
                if locality_failed
                else "VISUAL_ACCEPTANCE_FAILED"
            ),
        )
        if guard is not None:
            guard.complete(terminal_result_id=token, terminal_status=receipt.state.value)
        return receipt

    @staticmethod
    def _tool_for_lane(lane: ImageRouteFamily) -> ImageToolFamily:
        if lane is ImageRouteFamily.DETERMINISTIC:
            return ImageToolFamily.DETERMINISTIC
        return ImageToolFamily.IMAGE_GENERATION

    @staticmethod
    def _same_evidence_scope(
        observed: ImageCapabilityEvidence,
        expected: ImageCapabilityEvidence,
    ) -> bool:
        return (
            observed.route_family == expected.route_family
            and observed.model_revision_or_unexposed == expected.model_revision_or_unexposed
            and observed.control_surface == expected.control_surface
            and observed.task_scope == expected.task_scope
            and observed.protected_state_class == expected.protected_state_class
        )

    @staticmethod
    def _blocked(
        spec: ImageTaskSpec,
        fingerprint: ImageSurfaceFingerprint,
        constraints: dict[str, object],
        blocker: str,
        node_token: str | None = None,
        outcome: ImageRenderOutcome | None = None,
    ) -> ImageExecutionReceipt:
        return ImageExecutionReceipt(
            state=ImageExecutionState.BLOCKED,
            node_token=node_token,
            enforcement="ENGINEERING_DISPATCHER_CONTROLLED",
            fingerprint=fingerprint,
            render_manifest=spec.render_manifest,
            admitted_tool_family=spec.allowed_tool_family,
            actual_invoked_tool_family=(outcome.actual_tool_family if outcome else None),
            user_constraint_receipt=constraints,
            audit={},
            blocker=blocker,
        )
