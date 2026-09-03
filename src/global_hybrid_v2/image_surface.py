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


class ImageSurfaceFingerprint(BaseModel):
    surface_family: str = Field(min_length=1)
    tool_family: ImageToolFamily
    observable_model_revision: str = "UNEXPOSED"
    exposed_reference_controls: list[str] = Field(default_factory=list)
    exposed_edit_controls: list[str] = Field(default_factory=list)
    exposed_locality_controls: list[str] = Field(default_factory=list)
    output_visibility_behavior: str = Field(min_length=1)
    source_binding_receipt_available: bool = False
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
    ) -> ImageRenderOutcome: ...


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
    ) -> ImageRenderOutcome:
        raise RuntimeError("CAPABILITY_BOUNDARY: no controlled image execution port")


class ImageSurfaceController:
    """The sole pre-call admission point for repository-controlled image effects."""

    def __init__(self, port: ImageExecutionPort | None = None):
        self.port = port or UnavailableImageExecutionPort()

    def execute(self, spec: ImageTaskSpec) -> ImageExecutionReceipt:
        fingerprint = self.port.fingerprint()
        expected_evidence = ImageCapabilityEvidence(
            route_family=spec.selected_lane,
            model_revision_or_unexposed=fingerprint.observable_model_revision,
            control_surface=fingerprint.surface_family,
            task_scope=spec.task_scope,
            protected_state_class="|".join(sorted(spec.protected_state)),
        )
        constraints = {
            "allowed_route_families": sorted(item.value for item in spec.allowed_route_families),
            "forbidden_route_families": sorted(item.value for item in spec.forbidden_route_families),
            "output_count": spec.output_count,
            "reference_count": sum(len(value) for value in spec.reference_set.model_dump().values()),
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

        token = str(uuid4())
        try:
            outcome = self.port.invoke(
                manifest=spec.render_manifest,
                tool_family=spec.allowed_tool_family,
                node_token=token,
            )
        except RuntimeError as exc:
            return ImageExecutionReceipt(
                state=ImageExecutionState.CAPABILITY_BOUNDARY,
                enforcement="SOFT_AT_CHATGPT_HOST_BOUNDARY",
                fingerprint=fingerprint,
                render_manifest=spec.render_manifest,
                admitted_tool_family=spec.allowed_tool_family,
                user_constraint_receipt=constraints,
                audit={},
                blocker=str(exc),
            )
        if outcome.actual_tool_family is not spec.allowed_tool_family:
            return self._blocked(
                spec, fingerprint, constraints, "ACTUAL_TOOL_FAMILY_MISMATCH", token, outcome
            )
        non_target = outcome.changed_regions - {spec.render_manifest.current_visual_delta}
        protected_changed = outcome.protected_state_changed & spec.protected_state
        audit = {
            "required_modification_pass": outcome.requested_delta_completed,
            "required_preservation_pass": outcome.preservation_pass and outcome.identity_preserved,
            "non_target_regression_pass": not non_target and not protected_changed,
            "net_uplift_pass": outcome.net_uplift_pass,
            "non_target_changed_regions": sorted(non_target),
            "protected_state_changed": sorted(protected_changed),
        }
        passed = all(
            audit[key]
            for key in (
                "required_modification_pass",
                "required_preservation_pass",
                "non_target_regression_pass",
                "net_uplift_pass",
            )
        )
        return ImageExecutionReceipt(
            state=ImageExecutionState.PASS if passed else ImageExecutionState.FAIL,
            node_token=token,
            enforcement="ENGINEERING_DISPATCHER_CONTROLLED",
            fingerprint=fingerprint,
            render_manifest=spec.render_manifest,
            admitted_tool_family=spec.allowed_tool_family,
            actual_invoked_tool_family=outcome.actual_tool_family,
            user_constraint_receipt=constraints,
            audit=audit,
            blocker=None if passed else "VISUAL_ACCEPTANCE_FAILED",
        )

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
