from datetime import UTC, datetime
from uuid import uuid4

import pytest

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextClass,
    ContextContentRole,
    ContextItem,
    ContextOrigin,
    EffectType,
    Intent,
    TaskRequest,
)
from global_hybrid_v2.image_surface import (
    ImageCapabilityEvidence,
    ImageRenderOutcome,
    ImageRouteFamily,
    ImageSideEffectBudget,
    ImageSurfaceController,
    ImageSurfaceFingerprint,
    ImageTaskSpec,
    ImageToolFamily,
    ReferenceSet,
    RenderManifest,
)
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.state import RuntimeStateError, SQLiteRuntimeStateStore
from global_hybrid_v2.runtime.trace import TraceBus
from tests.test_runtime_state_stage2 import _state


def _reserve(store, *, attempt_id=None, number=1, authorization_id=None, prior=None):
    return store.reserve_image_attempt(
        "thread-a", "task-a", "source-a", attempt_id or str(uuid4()), number,
        authorization_id=authorization_id, prior_terminal_result_id=prior,
    )


def test_explicit_insert_and_terminal_lifecycle_are_durable(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    attempt_id = "attempt-1"
    assert _reserve(store, attempt_id=attempt_id) == 1
    active = store.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert active.active and active.active_attempt_id == attempt_id
    store.complete_image_attempt(
        "thread-a", "task-a", "source-a", attempt_id=attempt_id,
        terminal_result_id="result-1", terminal_status="PASS",
    )
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db").read_image_attempt_state(
        "thread-a", "task-a", "source-a"
    )
    assert not reopened.active
    assert reopened.last_terminal_result_id == "result-1"
    assert reopened.last_terminal_status == "PASS"


def test_retry_requires_exact_sequential_terminal_binding_and_single_use_authorization(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    _reserve(store, attempt_id="attempt-1")
    store.complete_image_attempt(
        "thread-a", "task-a", "source-a", attempt_id="attempt-1",
        terminal_result_id="result-1", terminal_status="FAIL",
    )
    assert _reserve(
        store, attempt_id="attempt-2", number=2, authorization_id="current-user-auth-2",
        prior="result-1",
    ) == 2
    with pytest.raises(RuntimeStateError, match="IMAGE_ATTEMPT_QUOTA_BLOCKED"):
        _reserve(
            store, attempt_id="attempt-replay", number=3,
            authorization_id="current-user-auth-2", prior="result-1",
        )


@pytest.mark.parametrize(
    ("number", "authorization_id", "prior", "error"),
    [
        (3, "fresh-auth", "result-1", "IMAGE_ATTEMPT_NUMBER_MISMATCH"),
        (2, None, "result-1", "IMAGE_RETRY_AUTHORIZATION_REQUIRED"),
        (2, "fresh-auth", "wrong-result", "IMAGE_PRIOR_TERMINAL_RESULT_MISMATCH"),
    ],
)
def test_retry_state_rejects_wrong_number_missing_authorization_and_wrong_result(
    tmp_path, number, authorization_id, prior, error
):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    _reserve(store, attempt_id="attempt-1")
    store.complete_image_attempt(
        "thread-a", "task-a", "source-a", attempt_id="attempt-1",
        terminal_result_id="result-1", terminal_status="FAIL",
    )
    with pytest.raises(RuntimeStateError, match=error):
        _reserve(store, number=number, authorization_id=authorization_id, prior=prior)


def test_duplicate_active_and_completion_mismatch_fail_closed(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    _reserve(store, attempt_id="attempt-1")
    with pytest.raises(RuntimeStateError, match="IMAGE_ATTEMPT_QUOTA_BLOCKED"):
        _reserve(store, attempt_id="attempt-2", number=2, authorization_id="auth", prior="none")
    with pytest.raises(RuntimeStateError, match="IMAGE_ATTEMPT_COMPLETION_BINDING_MISMATCH"):
        store.complete_image_attempt(
            "thread-a", "task-a", "source-a", attempt_id="different",
            terminal_result_id="result-1", terminal_status="FAIL",
        )


class _Authority:
    def resolve(self):
        return AuthoritySnapshot(entries={})


class _RecordingPort:
    def __init__(self):
        self.calls = 0

    def fingerprint(self):
        return ImageSurfaceFingerprint(
            surface_family="RD_TEST", tool_family=ImageToolFamily.IMAGE_GENERATION,
            observable_model_revision="UNEXPOSED", output_visibility_behavior="one",
        )

    def invoke(self, **_kwargs):
        self.calls += 1
        return ImageRenderOutcome(
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=True, identity_preserved=True,
            preservation_pass=True, net_uplift_pass=True,
        )


def _image_spec(budget):
    return ImageTaskSpec(
        task_scope="make image", reference_set=ReferenceSet(identity_reference=["source-a"]),
        render_manifest=RenderManifest(visual_subject="vehicle", current_visual_delta="background"),
        selected_lane=ImageRouteFamily.GENERATIVE,
        allowed_route_families={ImageRouteFamily.GENERATIVE},
        allowed_tool_family=ImageToolFamily.IMAGE_GENERATION, protected_state={"body"},
        capability_evidence=[ImageCapabilityEvidence(
            route_family=ImageRouteFamily.GENERATIVE, model_revision_or_unexposed="UNEXPOSED",
            control_surface="RD_TEST", task_scope="make image", protected_state_class="body",
        )], side_effect_budget=budget,
    )


def _request(spec, *, context=(), bound=False):
    return TaskRequest(
        request_text="make image", intent=Intent.EXECUTION,
        effects=[EffectType.IMAGE_GENERATE], target_system="image", action_class="generate",
        image_task=spec.model_dump(mode="json"), context=list(context),
        runtime_state_required=bound, conversation_or_thread_id="thread-a" if bound else None,
        runtime_task_id="task-a" if bound else None,
    )


def _dispatcher(port, store=None):
    return Dispatcher(
        authority=_Authority(), domains={}, trace=TraceBus(), runtime_state_store=store,
        image_controller=ImageSurfaceController(port),
    )


def test_protected_budget_without_runtime_binding_blocks_before_port_call():
    port = _RecordingPort()
    budget = ImageSideEffectBudget(source_asset_id="source-a")
    result = _dispatcher(port).dispatch(_request(_image_spec(budget)))
    assert result.status == "IMAGE_RUNTIME_STATE_BINDING_REQUIRED"
    assert port.calls == 0


def test_retry_requires_firewall_admitted_current_user_instruction_before_port_call(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(thread="thread-a", task="task-a"))
    _reserve(store, attempt_id="first")
    store.complete_image_attempt(
        "thread-a", "task-a", "source-a", attempt_id="first",
        terminal_result_id="first-result", terminal_status="FAIL",
    )
    port = _RecordingPort()
    budget = ImageSideEffectBudget(
        source_asset_id="source-a", attempt_number=2, authorized_attempt_limit=2,
        authorization="EXPLICIT_USER_EXTENSION", explicit_user_authorization_receipt="not-executable",
        prior_terminal_result_id="first-result",
    )
    context = ContextItem(
        id="not-executable", origin=ContextOrigin.CURRENT_USER,
        context_class=ContextClass.STABLE_USER_PREFERENCE, purpose="preference",
        task_scope="make image", payload="retry", content_role=ContextContentRole.DATA_ONLY,
        provenance=["current-user"],
    )
    result = _dispatcher(port, store).dispatch(_request(_image_spec(budget), context=[context], bound=True))
    assert result.status == "IMAGE_RETRY_AUTHORIZATION_BLOCKED"
    assert port.calls == 0


def test_dispatcher_consumes_fresh_authorization_for_exact_terminal_retry(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(thread="thread-a", task="task-a"))
    _reserve(store, attempt_id="first")
    store.complete_image_attempt(
        "thread-a", "task-a", "source-a", attempt_id="first",
        terminal_result_id="first-result", terminal_status="FAIL",
    )
    budget = ImageSideEffectBudget(
        source_asset_id="source-a", attempt_number=2, authorized_attempt_limit=2,
        authorization="EXPLICIT_USER_EXTENSION", explicit_user_authorization_receipt="fresh-auth",
        prior_terminal_result_id="first-result",
    )
    capability = ContextItem(
        id="capability", origin=ContextOrigin.CURRENT_TOOL_RESULT,
        context_class=ContextClass.CURRENT_CAPABILITY_FACT, purpose="capability",
        task_scope="make image", payload={"target_system": "image", "action_class": "generate"},
        current_binding=True, provenance=["current-port"],
    )
    authorization = ContextItem(
        id="fresh-auth", origin=ContextOrigin.CURRENT_USER,
        context_class=ContextClass.STABLE_USER_PREFERENCE, purpose="retry authorization",
        task_scope="make image", payload="retry this exact source",
        content_role=ContextContentRole.EXECUTABLE_INSTRUCTION, provenance=["current-user"],
    )
    port = _RecordingPort()
    result = _dispatcher(port, store).dispatch(
        _request(_image_spec(budget), context=[capability, authorization], bound=True)
    )
    assert result.status == "PASS"
    assert port.calls == 1
    durable = store.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert durable.attempts == 2 and not durable.active
    assert durable.last_terminal_status == "PASS"
    assert durable.consumed_authorization_ids == ["fresh-auth"]


def _capability():
    return ContextItem(
        id="capability",
        origin=ContextOrigin.CURRENT_TOOL_RESULT,
        context_class=ContextClass.CURRENT_CAPABILITY_FACT,
        purpose="capability",
        task_scope="make image",
        payload={"target_system": "image", "action_class": "generate"},
        current_binding=True,
        provenance=["current-port"],
    )


def test_reserved_and_in_flight_lifecycle_persist_started_at(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    _reserve(store, attempt_id="attempt-1")
    reserved = store.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert reserved.effect_lifecycle == "RESERVED"
    assert reserved.started_at is None
    started_at = datetime.now(UTC)
    store.mark_image_attempt_in_flight(
        "thread-a", "task-a", "source-a", attempt_id="attempt-1", started_at=started_at
    )
    in_flight = store.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert in_flight.effect_lifecycle == "IN_FLIGHT"
    assert in_flight.started_at == started_at


class _InterruptingPort(_RecordingPort):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.observed_lifecycle = None

    def invoke(self, **_kwargs):
        self.calls += 1
        state = self.store.read_image_attempt_state("thread-a", "task-a", "source-a")
        self.observed_lifecycle = state.effect_lifecycle
        raise KeyboardInterrupt("simulated process interruption after external effect")


def test_interrupted_effect_reopens_unknown_and_blocks_fresh_retry(tmp_path):
    path = tmp_path / "runtime.db"
    store = SQLiteRuntimeStateStore(path)
    store.create(_state(thread="thread-a", task="task-a"))
    port = _InterruptingPort(store)
    with pytest.raises(KeyboardInterrupt):
        _dispatcher(port, store).dispatch(
            _request(
                _image_spec(ImageSideEffectBudget(source_asset_id="source-a")),
                context=[_capability()],
                bound=True,
            )
        )
    assert port.calls == 1
    assert port.observed_lifecycle == "IN_FLIGHT"

    reopened = SQLiteRuntimeStateStore(path)
    unknown = reopened.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert unknown.effect_lifecycle == "INTERRUPTED_UNKNOWN"
    assert unknown.attempts == 1
    retry_port = _RecordingPort()
    authorization = ContextItem(
        id="fresh-auth",
        origin=ContextOrigin.CURRENT_USER,
        context_class=ContextClass.STABLE_USER_PREFERENCE,
        purpose="retry authorization",
        task_scope="make image",
        payload="retry this exact source",
        content_role=ContextContentRole.EXECUTABLE_INSTRUCTION,
        provenance=["current-user"],
    )
    budget = ImageSideEffectBudget(
        source_asset_id="source-a",
        attempt_number=2,
        authorized_attempt_limit=2,
        authorization="EXPLICIT_USER_EXTENSION",
        explicit_user_authorization_receipt="fresh-auth",
        prior_terminal_result_id="unknown",
    )
    result = _dispatcher(retry_port, reopened).dispatch(
        _request(_image_spec(budget), context=[_capability(), authorization], bound=True)
    )
    assert result.status == "IMAGE_PRIOR_OUTCOME_UNKNOWN"
    assert retry_port.calls == 0


def test_release_cannot_refund_and_late_reconciliation_terminalizes_unknown(tmp_path):
    path = tmp_path / "runtime.db"
    store = SQLiteRuntimeStateStore(path)
    _reserve(store, attempt_id="attempt-1")
    store.mark_image_attempt_in_flight(
        "thread-a", "task-a", "source-a", attempt_id="attempt-1", started_at=datetime.now(UTC)
    )
    with pytest.raises(RuntimeStateError, match="IMAGE_ATTEMPT_RELEASE_FORBIDDEN"):
        store.release_image_attempt("thread-a", "task-a", "source-a")
    assert store.read_image_attempt_state("thread-a", "task-a", "source-a").attempts == 1
    reopened = SQLiteRuntimeStateStore(path)
    with pytest.raises(RuntimeStateError, match="IMAGE_LATE_RECONCILIATION_EVIDENCE_REQUIRED"):
        reopened.complete_image_attempt(
            "thread-a",
            "task-a",
            "source-a",
            attempt_id="attempt-1",
            terminal_result_id="caller-asserted-absent",
            terminal_status="FAIL",
        )
    reopened.complete_image_attempt(
        "thread-a",
        "task-a",
        "source-a",
        attempt_id="attempt-1",
        terminal_result_id="artifact-late",
        terminal_status="PASS",
        provider_operation_id="call-late",
        artifact_id="artifact-late",
    )
    terminal = reopened.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert terminal.effect_lifecycle == "TERMINAL"
    assert terminal.last_attempt_id == "attempt-1"
    assert terminal.provider_operation_id == "call-late"
    assert terminal.artifact_id == "artifact-late"


class _IdentityPort(_RecordingPort):
    def invoke(self, **_kwargs):
        self.calls += 1
        return ImageRenderOutcome(
            artifact_id="artifact-77",
            provider_operation_id="call-77",
            actual_tool_family=ImageToolFamily.IMAGE_GENERATION,
            requested_delta_completed=True,
            identity_preserved=True,
            preservation_pass=True,
            net_uplift_pass=True,
        )


def test_success_preserves_provider_and_artifact_identity(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    store.create(_state(thread="thread-a", task="task-a"))
    result = _dispatcher(_IdentityPort(), store).dispatch(
        _request(
            _image_spec(ImageSideEffectBudget(source_asset_id="source-a")),
            context=[_capability()],
            bound=True,
        )
    )
    assert result.status == "PASS"
    assert result.output["provider_operation_id"] == "call-77"
    assert result.output["artifact_id"] == "artifact-77"
    durable = store.read_image_attempt_state("thread-a", "task-a", "source-a")
    assert durable.last_terminal_result_id == "artifact-77"
    assert durable.provider_operation_id == "call-77"
    assert durable.artifact_id == "artifact-77"
    assert durable.effect_lifecycle == "TERMINAL"
