import pytest
from pydantic import ValidationError

import global_hybrid_v2.image_surface as m

SOURCE_HASH = "a" * 64
MASK_HASH = "b" * 64


def evidence(
    *,
    surface="CONTROLLED_LOCAL_EDIT",
    task="real car plate cover",
    revision="gpt-image-2.5-sunburst-2026-09-08",
):
    return m.ImageCapabilityEvidence(
        route_family=m.ImageRouteFamily.GENERATIVE,
        model_revision_or_unexposed=revision,
        control_surface=surface,
        task_scope=task,
        protected_state_class="body|bumper|grille|lights|trim",
    )


def _polygon():
    return [
        {"x": 0.10, "y": 0.10},
        {"x": 0.25, "y": 0.10},
        {"x": 0.25, "y": 0.17},
        {"x": 0.10, "y": 0.17},
    ]


def envelope(
    *,
    state=m.LocalityEvidenceState.VERIFIED,
    binding_valid=True,
    confidence_sufficient=True,
    clip_state=m.SpatialClipState.INSIDE_EXPECTED_BOUNDS,
):
    return m.AuthorizedEditEnvelope(
        source_asset_id="source-1",
        source_sha256=SOURCE_HASH,
        region_id="plate-front-1",
        mask_asset_id="mask-1",
        mask_sha256=MASK_HASH,
        target_semantics="PRIMARY_SUBJECT_LICENSE_PLATE",
        spatial_binding=m.SpatialBindingReceipt(
            target_role="PRIMARY_PLATE_COVER",
            geometry_source="qualified_plate_locator",
            source_frame_id="source-frame-1",
            source_polygon=_polygon(),
            geometry_confidence=0.99,
            geometry_confidence_sufficient=confidence_sufficient,
            transform_chain_digest="transform-v1",
            projected_polygon=_polygon(),
            current_artifact_frame_id="artifact-frame-1",
            clip_state=clip_state,
            binding_valid=binding_valid,
            locator_receipt_id="locator-1",
            locator_evidence_state=state,
        ),
        write_polygon=_polygon(),
    )


def local_spec(*, env=None):
    env = env or envelope()
    return m.ImageTaskSpec(
        task_scope="real car plate cover",
        reference_set=m.ReferenceSet(identity_reference=["source-1"]),
        render_manifest=m.RenderManifest(
            visual_subject="the supplied vehicle",
            current_visual_delta="plate_cover",
            permitted_visible_objects=["matte black cloth sleeve"],
        ),
        selected_lane=m.ImageRouteFamily.GENERATIVE,
        allowed_route_families={m.ImageRouteFamily.GENERATIVE},
        allowed_tool_family=m.ImageToolFamily.IMAGE_GENERATION,
        protected_state={"body", "bumper", "grille", "lights", "trim"},
        capability_evidence=[evidence()],
        locality_mode=m.ImageLocalityMode.AUTHORIZED_ENVELOPE,
        authorized_edit_envelope=env,
    )


class ControlledPort:
    def __init__(self, *, outcome=None, envelope_enforcement=True, source_binding=True):
        self.calls = 0
        self.outcome = outcome or m.ImageRenderOutcome(
            artifact_id="candidate-1",
            actual_tool_family=m.ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=True,
            changed_regions={"plate_cover"},
            identity_preserved=True,
            preservation_pass=True,
            net_uplift_pass=True,
            source_asset_id="source-1",
            source_sha256=SOURCE_HASH,
            applied_region_id="plate-front-1",
            applied_mask_sha256=MASK_HASH,
            applied_transform_chain_digest="transform-v1",
            applied_current_artifact_frame_id="artifact-frame-1",
            outside_envelope_changed_pixels=0,
        )
        self.envelope_enforcement = envelope_enforcement
        self.source_binding = source_binding

    def fingerprint(self):
        return m.ImageSurfaceFingerprint(
            surface_family="CONTROLLED_LOCAL_EDIT",
            tool_family=m.ImageToolFamily.IMAGE_GENERATION,
            observable_model_revision="gpt-image-2.5-sunburst-2026-09-08",
            exposed_reference_controls=["single_source"],
            exposed_edit_controls=["edit"],
            exposed_locality_controls=["roi", "mask"],
            output_visibility_behavior="ONE_VISIBLE_CANDIDATE",
            source_binding_receipt_available=self.source_binding,
            authorized_envelope_enforcement_available=self.envelope_enforcement,
        )

    def invoke(self, *, manifest, tool_family, node_token, locality_envelope=None):
        self.calls += 1
        assert locality_envelope is not None
        return self.outcome


def test_positive_authorized_envelope_passes():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(local_spec())
    assert receipt.state is m.ImageExecutionState.PASS
    assert receipt.audit["outside_envelope_preservation_pass"] is True
    assert receipt.audit["locality_source_binding_pass"] is True
    assert receipt.audit["locality_region_binding_pass"] is True
    assert port.calls == 1


def test_unverified_locator_blocks_before_side_effect():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec(env=envelope(state=m.LocalityEvidenceState.UNPROVEN))
    )
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "LOCALITY_LOCATOR_UNVERIFIED"
    assert port.calls == 0


def test_missing_envelope_enforcement_blocks_before_side_effect():
    port = ControlledPort(envelope_enforcement=False)
    receipt = m.ImageSurfaceController(port).execute(local_spec())
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "AUTHORIZED_ENVELOPE_ENFORCEMENT_UNAVAILABLE"
    assert port.calls == 0


def test_missing_source_binding_receipt_blocks_before_side_effect():
    port = ControlledPort(source_binding=False)
    receipt = m.ImageSurfaceController(port).execute(local_spec())
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "SOURCE_BINDING_RECEIPT_UNAVAILABLE"
    assert port.calls == 0


def test_outside_envelope_drift_fails():
    outcome = ControlledPort().outcome.model_copy(update={"outside_envelope_changed_pixels": 1})
    receipt = m.ImageSurfaceController(ControlledPort(outcome=outcome)).execute(local_spec())
    assert receipt.state is m.ImageExecutionState.FAIL
    assert receipt.blocker == "LOCALITY_ENVELOPE_ACCEPTANCE_FAILED"
    assert receipt.audit["outside_envelope_preservation_pass"] is False


def test_source_mismatch_fails():
    outcome = ControlledPort().outcome.model_copy(update={"source_sha256": "c" * 64})
    receipt = m.ImageSurfaceController(ControlledPort(outcome=outcome)).execute(local_spec())
    assert receipt.state is m.ImageExecutionState.FAIL
    assert receipt.audit["locality_source_binding_pass"] is False


def test_mask_or_region_mismatch_fails():
    outcome = ControlledPort().outcome.model_copy(update={"applied_mask_sha256": "c" * 64})
    receipt = m.ImageSurfaceController(ControlledPort(outcome=outcome)).execute(local_spec())
    assert receipt.state is m.ImageExecutionState.FAIL
    assert receipt.audit["locality_region_binding_pass"] is False


def test_degenerate_envelope_rejected():
    with pytest.raises(ValidationError, match="non-zero area"):
        m.SpatialBindingReceipt(
            target_role="PRIMARY_PLATE_COVER",
            geometry_source="locator",
            source_frame_id="source-frame",
            source_polygon=[
                {"x": 0.1, "y": 0.1},
                {"x": 0.2, "y": 0.2},
                {"x": 0.3, "y": 0.3},
            ],
            geometry_confidence=0.9,
            geometry_confidence_sufficient=True,
            transform_chain_digest="t",
            projected_polygon=_polygon(),
            current_artifact_frame_id="artifact-frame",
            clip_state=m.SpatialClipState.INSIDE_EXPECTED_BOUNDS,
            binding_valid=True,
            locator_receipt_id="loc",
            locator_evidence_state=m.LocalityEvidenceState.VERIFIED,
        )


def test_invalid_spatial_binding_blocks_before_side_effect():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(local_spec(env=envelope(binding_valid=False)))
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "SPATIAL_BINDING_INVALID"
    assert port.calls == 0


def test_insufficient_geometry_confidence_blocks_before_side_effect():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(local_spec(env=envelope(confidence_sufficient=False)))
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "GEOMETRY_CONFIDENCE_INSUFFICIENT"
    assert port.calls == 0


def test_clipped_spatial_binding_blocks_before_side_effect():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec(env=envelope(clip_state=m.SpatialClipState.CLIPPED))
    )
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "SPATIAL_BINDING_CLIPPED_OR_OUT_OF_BOUNDS"
    assert port.calls == 0


def test_authorized_mode_without_envelope_rejected():
    data = local_spec().model_dump()
    data["authorized_edit_envelope"] = None
    with pytest.raises(ValidationError, match="requires an edit envelope"):
        m.ImageTaskSpec.model_validate(data)


def test_ordinary_soft_legacy_port_unchanged():
    class LegacyPort:
        def __init__(self):
            self.calls = 0

        def fingerprint(self):
            return m.ImageSurfaceFingerprint(
                surface_family="LEGACY",
                tool_family=m.ImageToolFamily.IMAGE_GENERATION,
                observable_model_revision="UNEXPOSED",
                output_visibility_behavior="ONE",
            )

        def invoke(self, *, manifest, tool_family, node_token):
            self.calls += 1
            return m.ImageRenderOutcome(
                actual_tool_family=tool_family,
                requested_delta_completed=True,
                identity_preserved=True,
                preservation_pass=True,
                net_uplift_pass=True,
            )

    ev = m.ImageCapabilityEvidence(
        route_family=m.ImageRouteFamily.GENERATIVE,
        model_revision_or_unexposed="UNEXPOSED",
        control_surface="LEGACY",
        task_scope="background",
        protected_state_class="body",
    )
    spec = m.ImageTaskSpec(
        task_scope="background",
        reference_set=m.ReferenceSet(identity_reference=["car"]),
        render_manifest=m.RenderManifest(visual_subject="car", current_visual_delta="background"),
        selected_lane=m.ImageRouteFamily.GENERATIVE,
        allowed_route_families={m.ImageRouteFamily.GENERATIVE},
        allowed_tool_family=m.ImageToolFamily.IMAGE_GENERATION,
        protected_state={"body"},
        capability_evidence=[ev],
    )
    port = LegacyPort()
    receipt = m.ImageSurfaceController(port).execute(spec)
    assert receipt.state is m.ImageExecutionState.PASS
    assert port.calls == 1


def budget(*, attempt=1, limit=1, explicit=False, terminal=True, pending=0, override=False):
    return m.ImageSideEffectBudget(
        source_asset_id="source-1",
        attempt_number=attempt,
        authorized_attempt_limit=limit,
        authorization=(
            m.ImageRetryAuthorization.EXPLICIT_USER_EXTENSION
            if explicit
            else m.ImageRetryAuthorization.FIRST_PASS_ONLY
        ),
        explicit_user_authorization_receipt="user-current-turn-retry-1" if explicit else None,
        prior_attempt_terminal=terminal,
        unattempted_batch_sources_remaining=pending,
        explicit_source_scope_override=override,
    )


def test_first_pass_budget_allows_exactly_one_side_effect():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(update={"side_effect_budget": budget()})
    )
    assert receipt.state is m.ImageExecutionState.PASS
    assert receipt.user_constraint_receipt["attempt_number"] == 1
    assert receipt.user_constraint_receipt["authorized_attempt_limit"] == 1
    assert port.calls == 1


def test_second_attempt_without_user_authorization_is_blocked_before_side_effect():
    port = ControlledPort()
    raw = budget().model_dump()
    raw["attempt_number"] = 2
    # Keep the default first-pass-only authorization to model an autonomous retry.
    retry_budget = m.ImageSideEffectBudget.model_construct(**raw)
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(update={"side_effect_budget": retry_budget})
    )
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "IMAGE_SIDE_EFFECT_BUDGET_EXHAUSTED"
    assert port.calls == 0


def test_explicit_user_authorized_second_attempt_is_allowed_once():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(update={"side_effect_budget": budget(attempt=2, limit=2, explicit=True)})
    )
    assert receipt.state is m.ImageExecutionState.PASS
    assert port.calls == 1


def test_third_attempt_exceeding_explicit_limit_is_blocked():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(update={"side_effect_budget": budget(attempt=3, limit=2, explicit=True)})
    )
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "IMAGE_SIDE_EFFECT_BUDGET_EXHAUSTED"
    assert port.calls == 0


def test_retry_waits_for_prior_result_terminal_audit():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(
            update={"side_effect_budget": budget(attempt=2, limit=2, explicit=True, terminal=False)}
        )
    )
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "PRIOR_IMAGE_ATTEMPT_NOT_TERMINAL"
    assert port.calls == 0


def test_batch_coverage_blocks_retry_while_unattempted_sources_remain():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(
            update={"side_effect_budget": budget(attempt=2, limit=2, explicit=True, pending=3)}
        )
    )
    assert receipt.state is m.ImageExecutionState.BLOCKED
    assert receipt.blocker == "BATCH_COVERAGE_REQUIRED_BEFORE_RETRY"
    assert port.calls == 0


def test_explicit_user_scope_override_can_retry_one_source_before_batch_coverage():
    port = ControlledPort()
    receipt = m.ImageSurfaceController(port).execute(
        local_spec().model_copy(
            update={"side_effect_budget": budget(attempt=2, limit=2, explicit=True, pending=3, override=True)}
        )
    )
    assert receipt.state is m.ImageExecutionState.PASS
    assert port.calls == 1
