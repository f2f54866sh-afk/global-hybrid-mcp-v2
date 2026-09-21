import pytest

from global_hybrid_v2.governance.engineering_execution import (
    REQUIRED_DOWNGRADE_MATRIX,
    BoundaryMap,
    EngineeringActor,
    EngineeringExecutionGovernor,
    EngineeringOperationFamily,
    EngineeringRoute,
    EvidenceClaim,
    WriterAdmission,
)
from global_hybrid_v2.runtime.state import (
    SQLiteRuntimeStateStore,
    WriterCapabilityRecord,
    WriterCapabilityState,
)

MUTATION_ENDPOINTS = [
    "create_blob",
    "update_file",
    "create_tree",
    "create_commit",
    "update_ref",
    "pr_mutation",
    "PR mutation",
    "code_write",
    "file_write",
    "commit",
    "push",
    "legacy_mutation",
    "alternate_connector_mutation",
]


class _RecordingWriter:
    def __init__(self):
        self.calls = 0

    def mutate(self, *, operation, repository):
        self.calls += 1
        return {"operation": operation, "repository": repository}


class _WriterSelector:
    def __init__(self, writer):
        self.writer = writer
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.writer


def _admission(**updates):
    values = {
        "actor": EngineeringActor.ENGINEER,
        "operation": "update_file",
        "repository": "owner/repo",
        "writer_surface": "github-app",
        "auth_context_id": "auth-1",
        "capability_epoch": "epoch-1",
    }
    values.update(updates)
    return WriterAdmission(**values)


def _attestation(**updates):
    values = {
        "actor": EngineeringActor.ENGINEER,
        "writer_surface": "github-app",
        "repository": "owner/repo",
        "operation_family": EngineeringOperationFamily.REPOSITORY_MUTATION,
        "auth_context_id": "auth-1",
        "capability_epoch": "epoch-1",
        "state": WriterCapabilityState.PROVEN,
        "evidence_producer": "TOOL_BROKER",
        "evidence_reference": "broker-attestation-1",
    }
    values.update(updates)
    return WriterCapabilityRecord(**values)


def _boundary_map(*, port_support=True):
    return BoundaryMap(
        producer="trusted tool broker",
        consumer="engineer runtime",
        enforcement_boundary="pre-tool-selection governor",
        evidence_producer="tool broker",
        side_effect_boundary="repository mutation port",
        protected_input_supported_by_port=port_support,
    )


def _implementation_admission(governor, **updates):
    values = {
        "problem_signature": "ROOT",
        "change_scope": "BOUNDARY",
        "boundary_map": _boundary_map(),
        "downgrade_matrix": set(REQUIRED_DOWNGRADE_MATRIX),
        "evidence_claims": [],
        "external_architecture_convergence": True,
        "material_gap_map_complete": True,
        "target_boundary_frozen": True,
        "test_now_complete": True,
    }
    values.update(updates)
    return governor.admit_primary_implementation(**values)


@pytest.mark.parametrize("operation", MUTATION_ENDPOINTS)
def test_authoring_routes_all_mutation_family_before_writer_selection(tmp_path, operation):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    decision = governor.admit(
        _admission(actor=EngineeringActor.AUTHORING_ENGINEERING, operation=operation)
    )
    assert decision.route is EngineeringRoute.ROUTE_TO_ENGINEER
    assert decision.operation_family is EngineeringOperationFamily.REPOSITORY_MUTATION
    assert decision.writer_tool_selection_count == 0
    assert decision.writer_probe_count == 0
    assert decision.repository_mutation_count == 0


@pytest.mark.parametrize(
    "operation",
    ["repository_read", "repository_search", "diff_readback", "ci_read"],
)
def test_authoring_read_paths_remain_available(tmp_path, operation):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    decision = governor.admit(
        _admission(actor=EngineeringActor.AUTHORING_ENGINEERING, operation=operation)
    )
    assert decision.route is EngineeringRoute.ALLOW_READ
    assert decision.writer_tool_selection_count == 0


def test_unknown_capability_denies_without_destructive_probe(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    decision = governor.admit(_admission())
    assert decision.status == "UNKNOWN_WRITE_CAPABILITY_DENY"
    assert decision.route is EngineeringRoute.DENY
    assert decision.writer_tool_selection_count == 0
    assert decision.writer_probe_count == 0
    assert decision.repository_mutation_count == 0


@pytest.mark.parametrize(
    ("actor", "capability"),
    [
        (EngineeringActor.AUTHORING_ENGINEERING, "route"),
        (EngineeringActor.ENGINEER, "unknown"),
        (EngineeringActor.ENGINEER, "hard-deny"),
    ],
)
def test_denied_routes_never_select_or_invoke_writer(tmp_path, actor, capability):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    admission = _admission(actor=actor)
    if capability == "hard-deny":
        governor.record_writer_failure(
            admission,
            error="Resource not accessible by integration",
            evidence_producer="ENGINEER_RUNTIME",
            evidence_reference="denial-1",
        )
    writer = _RecordingWriter()
    selector = _WriterSelector(writer)
    decision = governor.execute_repository_operation(
        admission,
        writer_selector=selector,
    )
    assert decision.route in {EngineeringRoute.ROUTE_TO_ENGINEER, EngineeringRoute.DENY}
    assert selector.calls == 0
    assert writer.calls == 0
    assert decision.repository_mutation_count == 0


def test_proven_engineer_capability_invokes_exactly_once(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.attest_writer_capability(_attestation())
    writer = _RecordingWriter()
    selector = _WriterSelector(writer)
    decision = governor.execute_repository_operation(
        _admission(),
        writer_selector=selector,
    )
    assert decision.route is EngineeringRoute.ALLOW_ENGINEER_WRITER
    assert selector.calls == 1
    assert writer.calls == 1
    assert decision.repository_mutation_count == 1


@pytest.mark.parametrize(
    "untrusted_source",
    ["REPO_METADATA_PUSH_TRUE", "MODEL_INFERENCE", "OLD_CHAT", "READ_SUCCESS"],
)
def test_generic_or_inferred_evidence_cannot_attest_writer(tmp_path, untrusted_source):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    with pytest.raises(PermissionError, match="PRODUCER_UNTRUSTED"):
        governor.attest_writer_capability(
            _attestation(evidence_producer=untrusted_source)
        )
    assert governor.admit(_admission()).status == "UNKNOWN_WRITE_CAPABILITY_DENY"


@pytest.mark.parametrize(
    "error",
    ["403", "AccessDenied", "Resource not accessible by integration"],
)
def test_hard_deny_is_operation_family_sticky_across_endpoint_restart_and_new_conversation(
    tmp_path,
    error,
):
    path = tmp_path / f"{error[:3]}.db"
    store = SQLiteRuntimeStateStore(path)
    governor = EngineeringExecutionGovernor(store)
    governor.record_writer_failure(
        _admission(),
        error=error,
        evidence_producer="ENGINEER_RUNTIME",
        evidence_reference="writer-error-1",
    )

    reopened = EngineeringExecutionGovernor(SQLiteRuntimeStateStore(path))
    for endpoint in MUTATION_ENDPOINTS:
        decision = reopened.admit(_admission(operation=endpoint))
        assert decision.status == "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE"
        assert decision.writer_tool_selection_count == 0
        assert decision.repository_mutation_count == 0


def test_hard_deny_covers_alternate_writer_surface_in_same_family(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.record_writer_failure(
        _admission(writer_surface="github-app"),
        error="403",
        evidence_producer="AUTH_LAYER",
        evidence_reference="deny-family",
    )
    alternate = _admission(
        writer_surface="legacy-connector",
        operation="alternate_connector_mutation",
    )
    assert governor.admit(alternate).status == (
        "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE"
    )
    with pytest.raises(
        RuntimeError,
        match="WRITER_HARD_DENY_REQUIRES_CAPABILITY_EPOCH_CHANGE",
    ):
        governor.attest_writer_capability(
            _attestation(writer_surface="legacy-connector")
        )


def test_epoch_change_requires_new_exact_attestation(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.record_writer_failure(
        _admission(),
        error="403",
        evidence_producer="AUTH_LAYER",
        evidence_reference="deny-epoch-1",
    )
    epoch_two = _admission(capability_epoch="epoch-2")
    assert governor.admit(epoch_two).status == "UNKNOWN_WRITE_CAPABILITY_DENY"
    governor.attest_writer_capability(
        _attestation(
            capability_epoch="epoch-2",
            evidence_reference="new-scope-attestation",
        )
    )
    decision = governor.admit(epoch_two)
    assert decision.route is EngineeringRoute.ALLOW_ENGINEER_WRITER
    assert decision.writer_tool_selection_count == 1
    assert decision.writer_probe_count == 0


def test_hard_deny_cannot_be_overwritten_within_same_epoch(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.record_writer_failure(
        _admission(),
        error="AccessDenied",
        evidence_producer="AUTH_LAYER",
        evidence_reference="deny-epoch-1",
    )
    with pytest.raises(
        RuntimeError,
        match="WRITER_HARD_DENY_REQUIRES_CAPABILITY_EPOCH_CHANGE",
    ):
        governor.attest_writer_capability(_attestation())
    assert governor.admit(_admission()).status == (
        "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE"
    )


def test_same_problem_second_escape_freezes_microfix_across_reopen(tmp_path):
    path = tmp_path / "runtime.db"
    governor = EngineeringExecutionGovernor(SQLiteRuntimeStateStore(path))
    first = governor.register_escape("ROOT-A")
    second = governor.register_escape("ROOT-A")
    assert first.microfix_frozen is False
    assert second.microfix_frozen is True

    reopened = EngineeringExecutionGovernor(SQLiteRuntimeStateStore(path))
    decision = _implementation_admission(
        reopened,
        problem_signature="ROOT-A",
        change_scope="FIELD_LEVEL",
    )
    assert decision.route is EngineeringRoute.FREEZE_MICROFIX_ROUTE


def test_alternate_bypass_immediately_freezes_field_patch(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    state = governor.register_escape("ROOT-B", alternate_path=True)
    assert state.microfix_frozen is True
    assert state.alternate_path_seen is True
    decision = _implementation_admission(
        governor,
        problem_signature="ROOT-B",
        change_scope="FIELD_LEVEL",
    )
    assert decision.status == "FREEZE_MICROFIX_AFTER_REPEAT_ESCAPE"


def test_missing_port_contract_is_capability_debt(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.register_escape("ROOT-C")
    decision = _implementation_admission(
        governor,
        problem_signature="ROOT-C",
        boundary_map=_boundary_map(port_support=False),
    )
    assert decision.route is EngineeringRoute.CAPABILITY_DEBT
    assert decision.status == "PORT_CONTRACT_CAPABILITY_DEBT"


def test_downstream_evidence_from_upstream_caller_is_rejected(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.register_escape("ROOT-D")
    decision = _implementation_admission(
        governor,
        problem_signature="ROOT-D",
        evidence_claims=[
            EvidenceClaim(
                evidence_name="sent-input receipt",
                supplied_by="CALLER",
                required_producer="EXECUTION_ADAPTER",
            )
        ],
    )
    assert decision.status == "EVIDENCE_ORIGIN_MISMATCH"


def test_incomplete_matrix_blocks_primary_implementation(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.register_escape("ROOT-E")
    incomplete = set(REQUIRED_DOWNGRADE_MATRIX) - {"restart_reopen"}
    decision = _implementation_admission(
        governor,
        problem_signature="ROOT-E",
        downgrade_matrix=incomplete,
    )
    assert decision.status == "COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE"
    assert decision.writer_tool_selection_count == 0


def test_one_problem_gets_one_consolidated_acceptance(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.register_escape("ROOT-F")
    admitted = _implementation_admission(
        governor,
        problem_signature="ROOT-F",
        evidence_claims=[
            EvidenceClaim(
                evidence_name="writer attestation",
                supplied_by="TOOL_BROKER",
                required_producer="TOOL_BROKER",
            )
        ],
    )
    assert admitted.route is EngineeringRoute.CONSOLIDATED_IMPLEMENTATION
    assert governor.record_consolidated_acceptance(
        "ROOT-F",
        focused_green=True,
        full_green=False,
        ci_green=True,
        independent_readback=True,
    ) == "CONSOLIDATED_ACCEPTANCE_PENDING"
    assert governor.record_consolidated_acceptance(
        "ROOT-F",
        focused_green=True,
        full_green=True,
        ci_green=True,
        independent_readback=True,
    ) == "CANDIDATE_TESTED_READY"
    assert governor.record_consolidated_acceptance(
        "ROOT-F",
        focused_green=True,
        full_green=True,
        ci_green=True,
        independent_readback=True,
    ) == "CONSOLIDATED_ACCEPTANCE_ALREADY_EMITTED"


@pytest.mark.parametrize(
    "missing_gate",
    [
        "external_architecture_convergence",
        "material_gap_map_complete",
        "target_boundary_frozen",
        "test_now_complete",
    ],
)
def test_primary_write_requires_complete_architecture_admission(tmp_path, missing_gate):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    governor.register_escape("ROOT-G")
    decision = _implementation_admission(
        governor,
        problem_signature="ROOT-G",
        **{missing_gate: False},
    )
    assert decision.route is EngineeringRoute.DENY
    assert decision.status == "PRIMARY_IMPLEMENTATION_NOT_ADMITTED"
    assert decision.writer_tool_selection_count == 0


def test_runtime_policy_contains_required_durable_invariants(tmp_path):
    governor = EngineeringExecutionGovernor(
        SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    )
    assert governor.policy.revision == "ENGINEERING_EXECUTION_POLICY_20260921_V1"
    assert set(governor.policy.invariants) == {
        "AUTHORING_ENGINEERING_NO_REPO_MUTATION",
        "MUTATION_ROUTE_TO_ENGINEER_BEFORE_TOOL_SELECTION",
        "NO_DESTRUCTIVE_CAPABILITY_PROBE",
        "UNKNOWN_WRITE_CAPABILITY_DENY",
        "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE",
        "OPERATION_FAMILY_DOWNGRADE_GUARD",
        "FREEZE_MICROFIX_AFTER_REPEAT_ESCAPE",
        "COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE",
        "SINGLE_CONSOLIDATED_ACCEPTANCE",
        "MANDATORY_EXTERNAL_ARCHITECTURE_SEARCH_BEFORE_WRITE",
    }
    assert set(governor.policy.required_downgrade_matrix) == REQUIRED_DOWNGRADE_MATRIX
