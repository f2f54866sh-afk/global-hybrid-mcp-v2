from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from global_hybrid_v2.contracts import AuthoritySnapshot, EffectType, Intent, TaskRequest
from global_hybrid_v2.image_surface import (
    ImageCapabilityEvidence,
    ImageExecutionState,
    ImageRenderOutcome,
    ImageRouteFamily,
    ImageSurfaceController,
    ImageSurfaceFingerprint,
    ImageTaskSpec,
    ImageToolFamily,
    ReferenceSet,
    RenderManifest,
)
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


class RecordingImagePort:
    def __init__(self, *, tool_family=ImageToolFamily.IMAGE_GENERATION, outcome=None):
        self.calls = []
        self._tool_family = tool_family
        self.outcome = outcome or ImageRenderOutcome(
            artifact_id="candidate-1",
            actual_tool_family=tool_family,
            requested_delta_completed=True,
            identity_preserved=True,
            preservation_pass=True,
            net_uplift_pass=True,
        )

    def fingerprint(self):
        return ImageSurfaceFingerprint(
            surface_family="CONTROLLED_TEST_SURFACE",
            tool_family=self._tool_family,
            observable_model_revision="UNEXPOSED",
            output_visibility_behavior="ONE_VISIBLE_CANDIDATE",
            observed_at=datetime(2026, 9, 3, tzinfo=UTC),
        )

    def invoke(self, *, manifest, tool_family, node_token):
        self.calls.append((manifest, tool_family, node_token))
        return self.outcome


def _spec(**changes):
    evidence = ImageCapabilityEvidence(
        route_family=ImageRouteFamily.GENERATIVE,
        model_revision_or_unexposed="UNEXPOSED",
        control_surface="CONTROLLED_TEST_SURFACE",
        task_scope="same vehicle, replace background",
        protected_state_class="body|headlamp|wheels",
    )
    data = {
        "task_scope": "same vehicle, replace background",
        "reference_set": ReferenceSet(identity_reference=["car-front"]),
        "render_manifest": RenderManifest(
            visual_subject="the supplied vehicle",
            scene_background_target="quiet dealership exterior",
            composition_target="single hero image",
            current_visual_delta="background",
        ),
        "selected_lane": ImageRouteFamily.GENERATIVE,
        "allowed_route_families": {ImageRouteFamily.GENERATIVE},
        "forbidden_route_families": set(),
        "allowed_tool_family": ImageToolFamily.IMAGE_GENERATION,
        "protected_state": {"wheels", "headlamp", "body"},
        "capability_evidence": [evidence],
    }
    data.update(changes)
    return ImageTaskSpec(**data)


def test_rc_img_001_references_do_not_set_output_count_or_collage():
    port = RecordingImagePort()
    references = [f"reference-{index}" for index in range(18)]
    receipt = ImageSurfaceController(port).execute(
        _spec(reference_set=ReferenceSet(identity_reference=references))
    )
    assert receipt.state is ImageExecutionState.PASS
    assert receipt.user_constraint_receipt["reference_count"] == 18
    assert receipt.user_constraint_receipt["output_count"] == 1
    assert port.calls[0][0].composition_target == "single hero image"


def test_rc_img_002_control_metadata_cannot_enter_render_manifest():
    with pytest.raises(ValidationError, match="non-renderable control metadata"):
        RenderManifest(
            visual_subject="vehicle",
            current_visual_delta="background",
            permitted_visible_objects=["analysis checklist"],
        )


def test_rc_img_003_user_rejected_source_route_is_ineligible():
    with pytest.raises(ValidationError, match="selected lane is forbidden"):
        _spec(
            selected_lane=ImageRouteFamily.STRICT_SOURCE_PRESERVING,
            allowed_route_families={ImageRouteFamily.STRICT_SOURCE_PRESERVING},
            forbidden_route_families={ImageRouteFamily.STRICT_SOURCE_PRESERVING},
        )


def test_rc_img_004_lane_and_surface_tool_family_mismatch_blocks_before_call():
    port = RecordingImagePort(tool_family=ImageToolFamily.DETERMINISTIC)
    receipt = ImageSurfaceController(port).execute(_spec())
    assert receipt.state is ImageExecutionState.BLOCKED
    assert receipt.blocker == "SURFACE_TOOL_FAMILY_MISMATCH"
    assert port.calls == []


def test_rc_img_005_non_target_identity_drift_fails_acceptance():
    port = RecordingImagePort(
        outcome=ImageRenderOutcome(
            artifact_id="drifted",
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=True,
            changed_regions={"background", "wheels", "headlamp"},
            protected_state_changed={"wheels", "headlamp"},
            identity_preserved=False,
            preservation_pass=False,
            net_uplift_pass=True,
        )
    )
    receipt = ImageSurfaceController(port).execute(_spec())
    assert receipt.state is ImageExecutionState.FAIL
    assert receipt.audit["non_target_regression_pass"] is False
    assert receipt.audit["protected_state_changed"] == ["headlamp", "wheels"]


def test_rc_img_006_preservation_without_requested_delta_is_not_pass():
    port = RecordingImagePort(
        outcome=ImageRenderOutcome(
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=False,
            identity_preserved=True,
            preservation_pass=True,
            net_uplift_pass=True,
        )
    )
    receipt = ImageSurfaceController(port).execute(_spec())
    assert receipt.state is ImageExecutionState.FAIL
    assert receipt.audit["required_modification_pass"] is False


def test_rc_img_007_matching_negative_evidence_blocks_prompt_only_retry():
    port = RecordingImagePort()
    fingerprint = port.fingerprint()
    negative = {
        "route_family": ImageRouteFamily.GENERATIVE,
        "model_revision_or_unexposed": fingerprint.observable_model_revision,
        "control_surface": fingerprint.surface_family,
        "task_scope": "same vehicle, replace background",
        "protected_state_class": "body|headlamp|wheels",
    }
    receipt = ImageSurfaceController(port).execute(_spec(negative_evidence=[negative]))
    assert receipt.state is ImageExecutionState.BLOCKED
    assert receipt.blocker == "MATCHING_NEGATIVE_EVIDENCE"
    assert port.calls == []


def test_rc_img_008_unexposed_surface_never_fabricates_model_identifier():
    receipt = ImageSurfaceController(RecordingImagePort()).execute(_spec())
    assert receipt.fingerprint.observable_model_revision == "UNEXPOSED"


def test_stale_or_wrong_scope_capability_evidence_fails_closed():
    stale = ImageCapabilityEvidence(
        route_family=ImageRouteFamily.GENERATIVE,
        model_revision_or_unexposed="UNEXPOSED",
        control_surface="CONTROLLED_TEST_SURFACE",
        task_scope="same vehicle, replace background",
        protected_state_class="body|headlamp|wheels",
        current=False,
    )
    receipt = ImageSurfaceController(RecordingImagePort()).execute(
        _spec(capability_evidence=[stale])
    )
    assert receipt.state is ImageExecutionState.BLOCKED
    assert receipt.blocker == "STALE_CAPABILITY_EVIDENCE"


def test_image_effect_uses_the_existing_single_dispatcher_path():
    class FixedAuthority:
        def resolve(self):
            return AuthoritySnapshot(entries={})

    port = RecordingImagePort()
    dispatcher = Dispatcher(
        authority=FixedAuthority(),
        domains={},
        trace=TraceBus(),
        image_controller=ImageSurfaceController(port),
    )
    result = dispatcher.dispatch(
        TaskRequest(
            request_text="出圖",
            intent=Intent.EXECUTION,
            effects=[EffectType.IMAGE_GENERATE],
            image_task=_spec().model_dump(mode="json"),
        )
    )
    assert result.status == "PASS"
    assert len(port.calls) == 1
