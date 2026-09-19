from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from global_hybrid_v2.image_surface import (
    ControlledRequestInputLineage,
    IdentityEvidenceState,
    IdentitySource,
    IdentitySourcePacket,
    IdentitySourceRole,
    IdentityStage,
    IdentityStageWitness,
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
    SourcePersonFidelityOracle,
    _identity_packet_digest,
    evaluate_source_person_fidelity,
)


class RecordingPort:
    def __init__(self) -> None:
        self.calls = 0

    def fingerprint(self) -> ImageSurfaceFingerprint:
        return ImageSurfaceFingerprint(
            surface_family="IDENTITY_CONTRACT_TEST_PORT",
            tool_family=ImageToolFamily.IMAGE_GENERATION,
            output_visibility_behavior="ONE_VISIBLE_CANDIDATE",
            observed_at=datetime(2026, 9, 19, tzinfo=UTC),
        )

    def invoke(self, *, manifest, tool_family, node_token) -> ImageRenderOutcome:
        del manifest, tool_family, node_token
        self.calls += 1
        return ImageRenderOutcome(
            artifact_id="candidate",
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=True,
            identity_preserved=True,
            preservation_pass=True,
            net_uplift_pass=True,
        )


def _packet(*, generated_only: bool = False) -> IdentitySourcePacket:
    sources = [
        IdentitySource(
            asset_id="master-real",
            sha256="a" * 64,
            role=IdentitySourceRole.ORIGINAL_REAL_MASTER,
        ),
        IdentitySource(asset_id="body-real", sha256="b" * 64, role=IdentitySourceRole.BODY),
    ]
    draft = IdentitySourcePacket.model_construct(
        task_binding="portrait-task",
        person_binding="person-1",
        version="v1",
        packet_digest="0" * 64,
        identity_critical=True,
        generative_only=generated_only,
        sources=sources,
        excluded_generated_source_ids={"old-generated-output"},
        request_lineage_required=True,
    )
    data = draft.model_dump()
    data["packet_digest"] = _identity_packet_digest(draft)
    return IdentitySourcePacket(**data)


def _lineage(packet: IdentitySourcePacket) -> ControlledRequestInputLineage:
    return ControlledRequestInputLineage(
        task_binding="portrait-task",
        packet_digest=packet.packet_digest,
        selected_lane=ImageRouteFamily.GENERATIVE,
        sent_source_roles={source.asset_id: source.role for source in packet.sources},
        excluded_generated_source_ids=packet.excluded_generated_source_ids,
    )


def _spec(**changes) -> ImageTaskSpec:
    packet = _packet()
    evidence = ImageCapabilityEvidence(
        route_family=ImageRouteFamily.GENERATIVE,
        model_revision_or_unexposed="UNEXPOSED",
        control_surface="IDENTITY_CONTRACT_TEST_PORT",
        task_scope="portrait-task",
        protected_state_class="face|identity",
    )
    data = {
        "task_scope": "portrait-task",
        "reference_set": ReferenceSet(identity_reference=["master-real", "body-real"]),
        "render_manifest": RenderManifest(
            visual_subject="the supplied person",
            current_visual_delta="background",
        ),
        "selected_lane": ImageRouteFamily.GENERATIVE,
        "allowed_route_families": {ImageRouteFamily.GENERATIVE},
        "allowed_tool_family": ImageToolFamily.IMAGE_GENERATION,
        "protected_state": {"face", "identity"},
        "capability_evidence": [evidence],
        "identity_source_packet": packet,
        "controlled_request_input_lineage": _lineage(packet),
    }
    data.update(changes)
    return ImageTaskSpec(**data)


def test_rd014_task_packet_binds_roles_excludes_generated_and_preserves_ordinary_specs():
    spec = _spec()
    assert spec.identity_source_packet is not None
    assert spec.controlled_request_input_lineage is not None
    assert "old-generated-output" not in spec.controlled_request_input_lineage.sent_source_roles


def test_rd014_rejects_stale_packet_roleless_multireference_and_missing_lineage():
    packet = _packet()
    with pytest.raises(ValidationError, match="requires controlled input lineage"):
        _spec(controlled_request_input_lineage=None)
    with pytest.raises(ValidationError, match="typed source roles"):
        _spec(reference_set=ReferenceSet(identity_reference=["master-real", "untyped"]))
    with pytest.raises(ValidationError, match="packet digest mismatch"):
        IdentitySourcePacket(**{**packet.model_dump(), "packet_digest": "c" * 64})


def test_rd014_generative_only_and_stage_progression_fail_closed():
    packet = _packet(generated_only=True)
    with pytest.raises(ValidationError, match="forbids deterministic"):
        _spec(
            identity_source_packet=packet,
            controlled_request_input_lineage=_lineage(packet),
            selected_lane=ImageRouteFamily.DETERMINISTIC,
            allowed_route_families={ImageRouteFamily.DETERMINISTIC},
            allowed_tool_family=ImageToolFamily.DETERMINISTIC,
            capability_evidence=[
                ImageCapabilityEvidence(
                    route_family=ImageRouteFamily.DETERMINISTIC,
                    model_revision_or_unexposed="UNEXPOSED",
                    control_surface="IDENTITY_CONTRACT_TEST_PORT",
                    task_scope="portrait-task",
                    protected_state_class="face|identity",
                )
            ],
        )
    with pytest.raises(ValidationError, match="prior stage"):
        _spec(identity_stage=IdentityStage.MULTI_POSE)
    stage_one = IdentityStageWitness(
        stage=IdentityStage.SOURCE_1X1,
        master_asset_id="master-real",
        packet_digest="f" * 64,
        decision=IdentityEvidenceState.PASS,
    )
    # A witness from a distinct packet cannot advance this task.
    with pytest.raises(ValidationError, match="prior stage"):
        _spec(identity_stage=IdentityStage.MULTI_POSE, lower_stage_witnesses=[stage_one])
    current_packet = _packet()
    stage_one_current = stage_one.model_copy(update={"packet_digest": current_packet.packet_digest})
    assert _spec(
        identity_source_packet=current_packet,
        controlled_request_input_lineage=_lineage(current_packet),
        identity_stage=IdentityStage.MULTI_POSE,
        lower_stage_witnesses=[stage_one_current],
    ).identity_stage is IdentityStage.MULTI_POSE


def test_rd014_fidelity_requires_original_master_and_unproven_conditioning_holds():
    packet = _packet()
    passed = SourcePersonFidelityOracle(
        master_asset_id="master-real",
        master_sha256="a" * 64,
        current_output_id="output-1",
        fidelity=IdentityEvidenceState.PASS,
    )
    assert evaluate_source_person_fidelity(packet, passed) is IdentityEvidenceState.PASS
    wrong_master = passed.model_copy(update={"master_asset_id": "generated-output"})
    assert evaluate_source_person_fidelity(packet, wrong_master) is IdentityEvidenceState.FAIL
    port = RecordingPort()
    receipt = ImageSurfaceController(port).execute(_spec(host_internal_conditioning_required=True))
    assert receipt.state is ImageExecutionState.CAPABILITY_BOUNDARY
    assert receipt.blocker == "INTERNAL_MODEL_CONDITIONING_UNPROVEN"
    assert port.calls == 0
