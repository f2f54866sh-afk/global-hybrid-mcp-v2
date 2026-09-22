from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from global_hybrid_v2.image_surface import (
    AuthorizedEditEnvelope,
    IdentitySourceRole,
    IdentityStage,
    ImageExecutionInput,
    ImageLocalityMode,
    ImageOperationMode,
    ImagePortCapabilities,
    ImagePortInputReceipt,
    ImageRenderOutcome,
    ImageSideEffectBudget,
    ImageSurfaceFingerprint,
    ImageToolFamily,
    LocalityEvidenceState,
    NormalizedPoint,
    SpatialBindingReceipt,
    SpatialClipState,
)
from global_hybrid_v2.runtime.dispatcher import TrustedDispatchContext
from global_hybrid_v2.runtime.identity_ingress import TrustedIdentityIngress
from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentitySecondaryRole,
    ImageSlotLifecycle,
    ImageSlotState,
    RuntimeStateError,
    SQLiteRuntimeStateStore,
)
from tests.test_rd014_stage1a_trusted_context import _capability_context
from tests.test_rd_20260913_009_image_binding import (
    _dispatcher,
    _image_spec,
    _request,
)
from tests.test_runtime_state_stage2 import _state


def _digest_lineage(body):
    return {
        **body,
        "lineage_digest": hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _polygon():
    return [
        NormalizedPoint(x=0.1, y=0.1),
        NormalizedPoint(x=0.3, y=0.1),
        NormalizedPoint(x=0.3, y=0.3),
        NormalizedPoint(x=0.1, y=0.3),
    ]


def _envelope():
    return AuthorizedEditEnvelope(
        source_asset_id="scene-base",
        source_sha256="c" * 64,
        region_id="seller-placement",
        mask_asset_id="mask-1",
        mask_sha256="d" * 64,
        target_semantics="INSERT_SELLER_INTO_SCENE",
        spatial_binding=SpatialBindingReceipt(
            target_role="SELLER_PLACEMENT",
            geometry_source="qualified-scene-locator",
            source_frame_id="scene-frame-1",
            source_polygon=_polygon(),
            geometry_confidence=0.99,
            geometry_confidence_sufficient=True,
            transform_chain_digest="transform-1",
            projected_polygon=_polygon(),
            current_artifact_frame_id="scene-frame-1",
            clip_state=SpatialClipState.INSIDE_EXPECTED_BOUNDS,
            binding_valid=True,
            locator_receipt_id="locator-1",
            locator_evidence_state=LocalityEvidenceState.VERIFIED,
        ),
        write_polygon=_polygon(),
    )


class BoundRecordingPort:
    def __init__(self, *, advertised=True, corrupt_receipt=False):
        self.calls = 0
        self.advertised = advertised
        self.corrupt_receipt = corrupt_receipt
        self.requests = []

    def fingerprint(self):
        return ImageSurfaceFingerprint(
            surface_family="RD_TEST",
            tool_family=ImageToolFamily.IMAGE_GENERATION,
            observable_model_revision="UNEXPOSED",
            output_visibility_behavior="one",
            source_binding_receipt_available=True,
            authorized_envelope_enforcement_available=True,
        )

    def describe_capabilities(self):
        roles = set(IdentitySourceRole)
        if not self.advertised:
            roles.remove(IdentitySourceRole.SELLER)
        return ImagePortCapabilities(
            snapshot_id="cap-snapshot-1",
            port_id="recording-port",
            port_version="1",
            supported_operation_modes={ImageOperationMode.TARGETED_EDIT},
            supported_reference_roles=roles,
            max_reference_inputs=8,
            typed_reference_roles=True,
            mask_input=True,
            source_binding_receipt=True,
            outside_region_verification=True,
        )

    def invoke_bound(self, *, request, node_token):
        del node_token
        self.calls += 1
        self.requests.append(request)
        inputs = list(request.inputs)
        if self.corrupt_receipt:
            inputs = [
                ImageExecutionInput(
                    asset_id="caller-substitute",
                    sha256="f" * 64,
                    role=IdentitySourceRole.SELLER,
                ),
                *inputs[1:],
            ]
        return ImageRenderOutcome(
            artifact_id="artifact-77",
            artifact_sha256="e" * 64,
            provider_operation_id="call-77",
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=True,
            changed_regions={"background"},
            protected_state_changed=set(),
            identity_preserved=True,
            preservation_pass=True,
            net_uplift_pass=True,
            source_asset_id="scene-base",
            source_sha256="c" * 64,
            applied_region_id="seller-placement",
            applied_mask_sha256="d" * 64,
            applied_transform_chain_digest="transform-1",
            applied_current_artifact_frame_id="scene-frame-1",
            outside_envelope_changed_pixels=0,
            input_receipt=ImagePortInputReceipt(
                capability_snapshot_id=request.capability_snapshot_id,
                workflow_id=request.workflow_id,
                slot_id=request.slot_id,
                operation_mode=request.operation_mode,
                task_binding=request.task_binding,
                packet_digest=request.packet_digest,
                inputs=inputs,
            ),
        )

    def invoke(self, **_kwargs):
        raise AssertionError("trusted execution must use invoke_bound")


def _setup(tmp_path, *, port=None):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(thread="thread-a", task="task-a"))
    principal = AuthenticatedPrincipal(
        subject="user-1", authentication_source="fake-test"
    )
    selection = TrustedIdentityIngress(store).issue(
        principal=principal,
        conversation_or_thread_id="thread-a",
        runtime_task_id="task-a",
        person_binding="person-1",
        master_asset_id="master-real",
        master_sha256="a" * 64,
        secondary_roles={
            "seller-real": IdentitySecondaryRole.SELLER,
            "scene-base": IdentitySecondaryRole.SCENE_BASE,
            "body-real": IdentitySecondaryRole.BODY,
        },
        secondary_sha256={
            "seller-real": "b" * 64,
            "scene-base": "c" * 64,
            "body-real": "f" * 64,
        },
        excluded_generated_source_ids={"old-generated"},
        generative_only=True,
    )
    spec = _image_spec(
        ImageSideEffectBudget(source_asset_id="scene-base")
    ).model_copy(
        update={
            "identity_trusted_ingress_required": True,
            "identity_stage": IdentityStage.SOURCE_1X1,
            "workflow_id": "workflow-1",
            "slot_id": "slot-1",
            "operation_mode": ImageOperationMode.TARGETED_EDIT,
            "locality_mode": ImageLocalityMode.AUTHORIZED_ENVELOPE,
            "authorized_edit_envelope": _envelope(),
        }
    )
    spec = spec.model_validate(spec.model_dump(mode="json"))
    request = _request(
        spec,
        context=[_capability_context()],
        bound=True,
    ).model_copy(update={"identity_selection_record_id": selection.record_id})
    return (
        store,
        port or BoundRecordingPort(),
        request,
        TrustedDispatchContext("user-1", "fake-test"),
    )


def test_trusted_selection_reaches_bound_port_and_persists_slot_lineage(tmp_path):
    store, port, request, context = _setup(tmp_path)
    result = _dispatcher(port, store).dispatch(request, trusted_context=context)

    assert result.status == "PASS"
    assert port.calls == 1
    execution = port.requests[0]
    assert execution.operation_mode is ImageOperationMode.TARGETED_EDIT
    assert {item.role for item in execution.inputs} >= {
        IdentitySourceRole.ORIGINAL_REAL_MASTER,
        IdentitySourceRole.SELLER,
        IdentitySourceRole.SCENE_BASE,
    }
    receipt = result.evidence["image_execution_receipt"]
    assert receipt["terminal_result_id"] == "artifact-77"
    assert receipt["asset_lineage"]["provider_operation_id"] == "call-77"
    assert receipt["asset_lineage"]["input_receipt"]["inputs"] == [
        item.model_dump(mode="json") for item in execution.inputs
    ]

    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    slot = reopened.read_image_slot("thread-a", "task-a", "workflow-1", "slot-1")
    assert slot.lifecycle is ImageSlotLifecycle.ACCEPTED
    assert slot.output_artifact_id == "artifact-77"
    assert slot.output_sha256 == "e" * 64
    assert slot.lineage["input_receipt"]["packet_digest"] == execution.packet_digest


def test_missing_advertised_role_holds_before_port_call(tmp_path):
    port = BoundRecordingPort(advertised=False)
    store, port, request, context = _setup(tmp_path, port=port)
    result = _dispatcher(port, store).dispatch(request, trusted_context=context)
    assert result.status == "CAPABILITY_BOUNDARY"
    assert result.output["blocker"] == "BOUND_IMAGE_PORT_CAPABILITY_HOLD"
    assert port.calls == 0


def test_port_input_substitution_is_rejected_and_never_accepted(tmp_path):
    port = BoundRecordingPort(corrupt_receipt=True)
    store, port, request, context = _setup(tmp_path, port=port)
    result = _dispatcher(port, store).dispatch(request, trusted_context=context)
    assert result.status == "CAPABILITY_BOUNDARY"
    assert result.output["blocker"] == "PORT_INPUT_BINDING_RECEIPT_MISMATCH"
    assert port.calls == 1
    slot = store.read_image_slot("thread-a", "task-a", "workflow-1", "slot-1")
    assert slot.lifecycle is ImageSlotLifecycle.IN_FLIGHT
    assert slot.output_artifact_id is None


def test_scene_base_must_bind_exact_authorized_edit_parent(tmp_path):
    store, port, request, context = _setup(tmp_path)
    payload = deepcopy(request.image_task)
    payload["authorized_edit_envelope"]["source_asset_id"] = "other-scene"
    payload["side_effect_budget"]["source_asset_id"] = "other-scene"
    result = _dispatcher(port, store).dispatch(
        request.model_copy(update={"image_task": payload}),
        trusted_context=context,
    )
    assert result.status == "CAPABILITY_BOUNDARY"
    assert result.output["blocker"] == "SCENE_BASE_ENVELOPE_BINDING_MISMATCH"
    assert port.calls == 0


def test_caller_direct_authority_still_blocks_before_bound_port(tmp_path):
    store, port, request, context = _setup(tmp_path)
    payload = deepcopy(request.image_task)
    payload["identity_source_packet"] = {"master": "caller-master"}
    result = _dispatcher(port, store).dispatch(
        request.model_copy(update={"image_task": payload}),
        trusted_context=context,
    )
    assert result.status == "IDENTITY_DIRECT_AUTHORITY_BYPASS_BLOCKED"
    assert port.calls == 0


def test_rejected_slot_allows_only_sequential_retry_with_same_scene_parent(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    base = ImageSlotState(
        conversation_or_thread_id="thread-a",
        runtime_task_id="task-a",
        workflow_id="workflow-1",
        slot_id="slot-1",
        stage="1X1_NEAR_FRONTAL",
        operation_mode="TARGETED_EDIT",
        attempt_number=1,
        lifecycle=ImageSlotLifecycle.PLANNED,
        parent_asset_id="scene-base",
        parent_sha256="c" * 64,
    )
    store.begin_image_slot(base, attempt_id="attempt-1", capability_snapshot_id="cap-1")
    store.complete_image_slot(
        "thread-a",
        "task-a",
        "workflow-1",
        "slot-1",
        attempt_id="attempt-1",
        terminal_status="FAIL",
        lineage=_digest_lineage(
            {
                "attempt_id": "attempt-1",
                "workflow_id": "workflow-1",
                "slot_id": "slot-1",
                "accepted": False,
                "output_artifact_id": "rejected-1",
                "output_sha256": "d" * 64,
            }
        ),
    )
    retried = store.begin_image_slot(
        base.model_copy(update={"attempt_number": 2}),
        attempt_id="attempt-2",
        capability_snapshot_id="cap-2",
    )
    assert retried.lifecycle is ImageSlotLifecycle.IN_FLIGHT
    assert retried.attempt_number == 2


def test_slot_retry_and_completion_bindings_fail_closed(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    state = ImageSlotState(
        conversation_or_thread_id="thread-a",
        runtime_task_id="task-a",
        workflow_id="workflow-1",
        slot_id="slot-1",
        stage="1X1_NEAR_FRONTAL",
        operation_mode="TARGETED_EDIT",
        attempt_number=1,
        lifecycle=ImageSlotLifecycle.PLANNED,
        parent_asset_id="scene-base",
        parent_sha256="c" * 64,
    )
    store.begin_image_slot(state, attempt_id="attempt-1", capability_snapshot_id="cap-1")
    with pytest.raises(RuntimeStateError, match="IMAGE_SLOT_PRIOR_OUTCOME_UNKNOWN"):
        store.begin_image_slot(
            state.model_copy(update={"attempt_number": 2}),
            attempt_id="attempt-2",
            capability_snapshot_id="cap-2",
        )
    with pytest.raises(RuntimeStateError, match="IMAGE_SLOT_COMPLETION_BINDING_MISMATCH"):
        store.complete_image_slot(
            "thread-a",
            "task-a",
            "workflow-1",
            "slot-1",
            attempt_id="wrong-attempt",
            terminal_status="PASS",
            lineage={
                "attempt_id": "wrong-attempt",
                "workflow_id": "workflow-1",
                "slot_id": "slot-1",
                "accepted": True,
            },
        )


def test_persisted_lineage_tamper_fails_reopen_readback(tmp_path):
    store, port, request, context = _setup(tmp_path)
    assert _dispatcher(port, store).dispatch(request, trusted_context=context).status == "PASS"
    with store._connect() as connection:
        row = connection.execute(
            "SELECT payload FROM image_workflow_slot WHERE workflow_id=? AND slot_id=?",
            ("workflow-1", "slot-1"),
        ).fetchone()
        payload = json.loads(row[0])
        payload["lineage"]["output_artifact_id"] = "forged-output"
        connection.execute(
            "UPDATE image_workflow_slot SET payload=? WHERE workflow_id=? AND slot_id=?",
            (json.dumps(payload), "workflow-1", "slot-1"),
        )
    with pytest.raises(ValueError, match="lineage digest mismatch"):
        SQLiteRuntimeStateStore(tmp_path / "runtime.db").read_image_slot(
            "thread-a", "task-a", "workflow-1", "slot-1"
        )
