import inspect
import json
import sqlite3

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from global_hybrid_v2.governance.engineering_execution import (
    REQUIRED_DOWNGRADE_MATRIX,
    ArchitectureResearchEvidencePort,
    BoundaryMap,
    EngineeringActor,
    EngineeringExecutionGovernor,
    EngineeringOperationFamily,
    EngineeringRoute,
    EvidenceProducerClass,
    EvidenceReceiptKind,
    ExecutionEvidencePort,
    GovernanceEvidencePort,
    VerifierEvidencePort,
    WriterAdmission,
    WriterCapabilityAttestation,
    WriterCapabilityEvidencePort,
)
from global_hybrid_v2.governance.engineering_execution import (
    TestMatrixEvidencePort as _TestMatrixEvidencePort,
)
from global_hybrid_v2.runtime.state import (
    RuntimeStateError,
    RuntimeStateNotFound,
    SQLiteRuntimeStateStore,
    WriterCapabilityRecord,
    WriterCapabilityState,
)

REPOSITORY = "owner/repo"
EPOCH = "epoch-1"
MUTATIONS = [
    "create_blob", "update_file", "create_tree", "create_commit", "update_ref",
    "pr_mutation", "legacy_mutation", "alternate_connector_mutation", "commit", "push",
]

_PORT_CLASSES = {
    EvidenceProducerClass.SEARCH_EXECUTOR: ArchitectureResearchEvidencePort,
    EvidenceProducerClass.GOVERNANCE_ENGINE: GovernanceEvidencePort,
    EvidenceProducerClass.TEST_MATRIX_COMPILER: _TestMatrixEvidencePort,
    EvidenceProducerClass.TOOL_BROKER: WriterCapabilityEvidencePort,
    EvidenceProducerClass.AUTH_RUNTIME: WriterCapabilityEvidencePort,
    EvidenceProducerClass.EXECUTION_ADAPTER: ExecutionEvidencePort,
    EvidenceProducerClass.VERIFIER: VerifierEvidencePort,
}
_KEYS = {producer: Ed25519PrivateKey.generate() for producer in _PORT_CLASSES}
_IDENTITIES = {
    producer: f"trusted-{producer.value.lower()}" for producer in _PORT_CLASSES
}
_VERIFIERS = {
    _IDENTITIES[producer]: key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    for producer, key in _KEYS.items()
}


class _Writer:
    def __init__(self):
        self.calls = 0

    def mutate(self, *, operation, repository):
        self.calls += 1


class _Selector:
    def __init__(self, writer):
        self.writer = writer
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.writer


def _store(path):
    return SQLiteRuntimeStateStore(
        path, engineering_evidence_verifiers=_VERIFIERS
    )


def _issuer(store, producer_class):
    port_class = _PORT_CLASSES[producer_class]
    kwargs = {
        "producer_identity": _IDENTITIES[producer_class],
        "signing_key": _KEYS[producer_class],
    }
    if port_class is WriterCapabilityEvidencePort:
        kwargs["producer_class"] = producer_class
    return port_class(store, **kwargs)


def _admission(**updates):
    values = {
        "actor": EngineeringActor.ENGINEER,
        "operation": "update_file",
        "repository": REPOSITORY,
        "writer_surface": "github-app",
        "auth_context_id": "auth-1",
        "capability_epoch": EPOCH,
    }
    values.update(updates)
    return WriterAdmission(**values)


def _boundary(supported=True):
    return BoundaryMap(
        producer="trusted tool broker",
        consumer="engineer runtime",
        enforcement_boundary="pre-tool-selection governor",
        evidence_producer="execution adapter",
        side_effect_boundary="repository mutation port",
        protected_input_supported_by_port=supported,
    )


def _binding(problem, reference):
    return {
        "problem_signature": problem,
        "repository": REPOSITORY,
        "capability_epoch": EPOCH,
        "evidence_reference": reference,
    }


def _prepare_primary(store, problem="ROOT", boundary=None):
    boundary = boundary or _boundary()
    governor = EngineeringExecutionGovernor(store)
    governor.register_escape(problem)
    research = _issuer(store, EvidenceProducerClass.SEARCH_EXECUTOR)
    governance = _issuer(store, EvidenceProducerClass.GOVERNANCE_ENGINE)
    matrix = _issuer(store, EvidenceProducerClass.TEST_MATRIX_COMPILER)
    execution = _issuer(store, EvidenceProducerClass.EXECUTION_ADAPTER)
    research_receipt = research.issue_research(
        authoritative_sources=["NIST", "OWASP", "RFC9110"],
        **_binding(problem, "research-1"),
    )
    gap_receipt = governance.issue_material_gap(
        material_gaps=["caller assertion is not trusted evidence"],
        **_binding(problem, "gaps-1"),
    )
    boundary_receipt = governance.issue_boundary_freeze(
        boundary_map=boundary, **_binding(problem, "boundary-1")
    )
    matrix_receipt = matrix.issue_test_now(
        matrix_categories=set(REQUIRED_DOWNGRADE_MATRIX),
        **_binding(problem, "matrix-1"),
    )
    governor.register_architecture_research(
        research_receipt.receipt_id,
        problem_signature=problem, repository=REPOSITORY, capability_epoch=EPOCH,
    )
    governor.register_material_gap(
        gap_receipt.receipt_id,
        problem_signature=problem, repository=REPOSITORY, capability_epoch=EPOCH,
    )
    governor.register_boundary_freeze(
        boundary_receipt.receipt_id,
        problem_signature=problem, repository=REPOSITORY, capability_epoch=EPOCH,
    )
    governor.register_test_now(
        matrix_receipt.receipt_id,
        problem_signature=problem, repository=REPOSITORY, capability_epoch=EPOCH,
    )
    origin = execution.issue_execution_evidence(
        evidence_name="execution-boundary-map",
        execution_binding=problem,
        **_binding(problem, "execution-1"),
    )
    return governor, boundary, origin


@pytest.mark.parametrize("operation", MUTATIONS)
def test_authoring_routes_before_writer_selection(tmp_path, operation):
    governor = EngineeringExecutionGovernor(_store(tmp_path / "db"))
    writer = _Writer()
    selector = _Selector(writer)
    decision = governor.execute_repository_operation(
        _admission(actor=EngineeringActor.AUTHORING_ENGINEERING, operation=operation),
        writer_selector=selector,
    )
    assert decision.route is EngineeringRoute.ROUTE_TO_ENGINEER
    assert selector.calls == writer.calls == 0
    assert decision.writer_tool_selection_count == 0
    assert decision.writer_probe_count == 0
    assert decision.repository_mutation_count == 0


def test_ordinary_authoring_read_path_is_unchanged(tmp_path):
    governor = EngineeringExecutionGovernor(_store(tmp_path / "db"))
    assert governor.admit(
        _admission(
            actor=EngineeringActor.AUTHORING_ENGINEERING,
            operation="repository_read",
        )
    ).route is EngineeringRoute.ALLOW_READ


def test_unknown_writer_capability_never_selects_writer(tmp_path):
    governor = EngineeringExecutionGovernor(_store(tmp_path / "db"))
    writer = _Writer()
    selector = _Selector(writer)
    decision = governor.execute_repository_operation(
        _admission(), writer_selector=selector
    )
    assert decision.status == "UNKNOWN_WRITE_CAPABILITY_DENY"
    assert selector.calls == writer.calls == 0


def test_general_state_store_has_zero_receipt_issuance_authority(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "ordinary.db")
    assert not hasattr(store, "issue_engineering_evidence_receipt")
    with pytest.raises(RuntimeStateError, match="ISSUER_UNTRUSTED"):
        store.persist_engineering_evidence_receipt(
            {
                "receipt_id": "caller-id",
                "receipt_kind": "ARCHITECTURE_RESEARCH",
                "producer_identity": "caller",
                "producer_class": "SEARCH_EXECUTOR",
                "problem_signature": "ROOT",
                "repository": REPOSITORY,
                "capability_epoch": EPOCH,
                "revision": 1,
                "evidence_reference": "caller",
                "issued_at": "2026-09-21T00:00:00+00:00",
                "integrity_signature": "00" * 64,
            }
        )


def test_verifier_registry_is_composition_owned_and_sealed(tmp_path):
    empty_path = tmp_path / "ordinary.db"
    SQLiteRuntimeStateStore(empty_path)
    with pytest.raises(RuntimeStateError, match="REGISTRY_SEALED"):
        _store(empty_path)

    trusted_path = tmp_path / "trusted.db"
    _store(trusted_path)
    attacker_verifiers = dict(_VERIFIERS)
    attacker_verifiers[_IDENTITIES[EvidenceProducerClass.SEARCH_EXECUTOR]] = (
        Ed25519PrivateKey.generate().public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    with pytest.raises(RuntimeStateError, match="REGISTRY_SEALED"):
        SQLiteRuntimeStateStore(
            trusted_path,
            engineering_evidence_verifiers=attacker_verifiers,
        )


def test_caller_generated_signing_key_cannot_impersonate_producer(tmp_path):
    store = _store(tmp_path / "db")
    attacker = ArchitectureResearchEvidencePort(
        store,
        producer_identity=_IDENTITIES[EvidenceProducerClass.SEARCH_EXECUTOR],
        signing_key=Ed25519PrivateKey.generate(),
    )
    with pytest.raises(RuntimeStateError, match="INTEGRITY_MISMATCH"):
        attacker.issue_research(
            authoritative_sources=["NIST", "OWASP", "RFC9110"],
            **_binding("ROOT", "attacker"),
        )


def test_producer_specific_ports_cannot_cross_issue(tmp_path):
    store = _store(tmp_path / "db")
    search = _issuer(store, EvidenceProducerClass.SEARCH_EXECUTOR)
    broker = _issuer(store, EvidenceProducerClass.TOOL_BROKER)
    governance = _issuer(store, EvidenceProducerClass.GOVERNANCE_ENGINE)
    assert not hasattr(search, "issue_writer_capability")
    assert not hasattr(broker, "issue_research")
    assert not hasattr(governance, "issue_execution_evidence")
    with pytest.raises(RuntimeStateError, match="PRODUCER_KIND_MISMATCH"):
        search._issue(
            EvidenceReceiptKind.WRITER_CAPABILITY,
            problem_signature="ROOT",
            repository=REPOSITORY,
            capability_epoch=EPOCH,
            evidence_reference="private-method-is-not-authority",
            details={
                "actor": EngineeringActor.ENGINEER.value,
                "writer_surface": "github-app",
                "auth_context_id": "auth-1",
                "operation_family": "REPOSITORY_MUTATION",
                "capability_state": "PROVEN",
            },
            model=WriterCapabilityAttestation,
        )


def test_primary_api_has_no_caller_completion_booleans():
    parameters = inspect.signature(
        EngineeringExecutionGovernor.admit_primary_implementation
    ).parameters
    for field in (
        "external_architecture_convergence",
        "material_gap_map_complete",
        "target_boundary_frozen",
        "test_now_complete",
    ):
        assert field not in parameters


def test_no_research_receipt_blocks_primary_implementation(tmp_path):
    governor = EngineeringExecutionGovernor(_store(tmp_path / "db"))
    governor.register_escape("NO-RESEARCH")
    decision = governor.admit_primary_implementation(
        problem_signature="NO-RESEARCH", repository=REPOSITORY,
        capability_epoch=EPOCH, change_scope="BOUNDARY", boundary_map=_boundary(),
        downgrade_matrix=set(REQUIRED_DOWNGRADE_MATRIX),
        required_evidence_receipt_ids=["caller-string"],
    )
    assert decision.status == "PRIMARY_IMPLEMENTATION_NOT_ADMITTED"


def test_positive_trusted_receipt_path(tmp_path):
    store = _store(tmp_path / "db")
    governor, boundary, origin = _prepare_primary(store)
    decision = governor.admit_primary_implementation(
        problem_signature="ROOT", repository=REPOSITORY, capability_epoch=EPOCH,
        change_scope="BOUNDARY", boundary_map=boundary,
        downgrade_matrix=set(REQUIRED_DOWNGRADE_MATRIX),
        required_evidence_receipt_ids=[origin.receipt_id],
    )
    assert decision.route is EngineeringRoute.CONSOLIDATED_IMPLEMENTATION


def test_empty_evidence_list_is_capability_debt(tmp_path):
    governor, boundary, _ = _prepare_primary(
        _store(tmp_path / "db")
    )
    decision = governor.admit_primary_implementation(
        problem_signature="ROOT", repository=REPOSITORY, capability_epoch=EPOCH,
        change_scope="BOUNDARY", boundary_map=boundary,
        downgrade_matrix=set(REQUIRED_DOWNGRADE_MATRIX),
        required_evidence_receipt_ids=[],
    )
    assert decision.route is EngineeringRoute.CAPABILITY_DEBT
    assert decision.status == "MISSING_REQUIRED_EVIDENCE_PRODUCER"


def test_caller_produced_downstream_evidence_is_rejected(tmp_path):
    store = _store(tmp_path / "db")
    governor, boundary, _ = _prepare_primary(store)
    decision = governor.admit_primary_implementation(
        problem_signature="ROOT", repository=REPOSITORY, capability_epoch=EPOCH,
        change_scope="BOUNDARY", boundary_map=boundary,
        downgrade_matrix=set(REQUIRED_DOWNGRADE_MATRIX),
        required_evidence_receipt_ids=["caller-produced-receipt"],
    )
    assert decision.status == "EVIDENCE_ORIGIN_MISMATCH"


def test_forged_research_receipt_integrity_fails(tmp_path):
    path = tmp_path / "db"
    store = _store(path)
    governor = EngineeringExecutionGovernor(store)
    governor.register_escape("FORGED")
    receipt = _issuer(
        store, EvidenceProducerClass.SEARCH_EXECUTOR
    ).issue_research(
        authoritative_sources=["NIST", "OWASP", "RFC9110"],
        **_binding("FORGED", "research"),
    )
    with sqlite3.connect(path) as connection:
        payload = json.loads(connection.execute(
            "SELECT payload FROM engineering_evidence_receipt WHERE receipt_id=?",
            (receipt.receipt_id,),
        ).fetchone()[0])
        payload["authoritative_sources"] = ["caller", "fake", "sources"]
        connection.execute(
            "UPDATE engineering_evidence_receipt SET payload=? WHERE receipt_id=?",
            (json.dumps(payload), receipt.receipt_id),
        )
    with pytest.raises(RuntimeStateError, match="INTEGRITY_MISMATCH"):
        governor.register_architecture_research(
            receipt.receipt_id, problem_signature="FORGED",
            repository=REPOSITORY, capability_epoch=EPOCH,
        )


def test_wrong_problem_binding_and_stale_research_are_rejected(tmp_path):
    store = _store(tmp_path / "db")
    governor = EngineeringExecutionGovernor(store)
    governor.register_escape("ROOT")
    issuer = _issuer(store, EvidenceProducerClass.SEARCH_EXECUTOR)
    old = issuer.issue_research(
        authoritative_sources=["NIST", "OWASP", "RFC9110"],
        **_binding("ROOT", "old"),
    )
    issuer.issue_research(
        authoritative_sources=["NIST", "OWASP", "Kubernetes"],
        **_binding("ROOT", "new"),
    )
    with pytest.raises(RuntimeStateError, match="STALE"):
        governor.register_architecture_research(
            old.receipt_id, problem_signature="ROOT",
            repository=REPOSITORY, capability_epoch=EPOCH,
        )
    wrong = issuer.issue_research(
        authoritative_sources=["NIST", "OWASP", "RFC9110"],
        **_binding("OTHER", "wrong"),
    )
    with pytest.raises(RuntimeStateError, match="BINDING_MISMATCH"):
        governor.register_architecture_research(
            wrong.receipt_id, problem_signature="ROOT",
            repository=REPOSITORY, capability_epoch=EPOCH,
        )


def test_writer_attestation_is_trusted_bound_and_single_use(tmp_path):
    store = _store(tmp_path / "db")
    governor = EngineeringExecutionGovernor(store)
    admission = _admission()
    attestation = _issuer(
        store, EvidenceProducerClass.TOOL_BROKER
    ).issue_writer_capability(admission, evidence_reference="broker-call-1")
    governor.attest_writer_capability(attestation.receipt_id, admission=admission)
    assert governor.admit(admission).route is EngineeringRoute.ALLOW_ENGINEER_WRITER
    with pytest.raises(RuntimeStateError, match="REPLAYED"):
        governor.attest_writer_capability(attestation.receipt_id, admission=admission)


@pytest.mark.parametrize(
    "change",
    [
        {"repository": "other/repo"},
        {"actor": EngineeringActor.AUTHORING_ENGINEERING},
        {"auth_context_id": "other-auth"},
        {"capability_epoch": "epoch-2"},
        {"writer_surface": "legacy-connector"},
    ],
)
def test_writer_attestation_wrong_binding_is_rejected(tmp_path, change):
    store = _store(tmp_path / "db")
    original = _admission()
    receipt = _issuer(
        store, EvidenceProducerClass.AUTH_RUNTIME
    ).issue_writer_capability(original, evidence_reference="auth-1")
    with pytest.raises((RuntimeStateError, RuntimeStateNotFound)):
        EngineeringExecutionGovernor(store).attest_writer_capability(
            receipt.receipt_id, admission=_admission(**change)
        )


def test_forged_writer_attestation_and_direct_record_do_not_admit(tmp_path):
    store = _store(tmp_path / "db")
    governor = EngineeringExecutionGovernor(store)
    with pytest.raises(RuntimeStateNotFound):
        governor.attest_writer_capability("forged", admission=_admission())
    caller_record = WriterCapabilityRecord(
        actor=EngineeringActor.ENGINEER, writer_surface="github-app",
        repository=REPOSITORY,
        operation_family=EngineeringOperationFamily.REPOSITORY_MUTATION,
        auth_context_id="auth-1", capability_epoch=EPOCH,
        state=WriterCapabilityState.PROVEN, evidence_producer="TOOL_BROKER",
        evidence_reference="caller-forged",
    )
    with pytest.raises((TypeError, sqlite3.Error)):
        governor.attest_writer_capability(caller_record, admission=_admission())
    assert governor.admit(_admission()).status == "UNKNOWN_WRITE_CAPABILITY_DENY"


def test_hard_deny_is_family_sticky_across_reopen_and_alternate_path(tmp_path):
    path = tmp_path / "db"
    store = _store(path)
    admission = _admission()
    receipt = _issuer(
        store, EvidenceProducerClass.AUTH_RUNTIME
    ).issue_writer_capability(
        admission,
        state=WriterCapabilityState.HARD_DENY,
        evidence_reference="deny-1",
    )
    EngineeringExecutionGovernor(store).attest_writer_capability(
        receipt.receipt_id, admission=admission
    )
    reopened = EngineeringExecutionGovernor(_store(path))
    alternate = _admission(
        writer_surface="legacy-connector", operation="alternate_connector_mutation"
    )
    writer = _Writer()
    selector = _Selector(writer)
    decision = reopened.execute_repository_operation(
        alternate, writer_selector=selector
    )
    assert decision.status == "HARD_DENY_STICKY_UNTIL_CAPABILITY_EPOCH_CHANGE"
    assert selector.calls == writer.calls == 0


def test_receipt_derived_convergence_survives_reopen(tmp_path):
    path = tmp_path / "db"
    governor, boundary, origin = _prepare_primary(_store(path))
    del governor
    reopened = EngineeringExecutionGovernor(_store(path))
    decision = reopened.admit_primary_implementation(
        problem_signature="ROOT", repository=REPOSITORY, capability_epoch=EPOCH,
        change_scope="BOUNDARY", boundary_map=boundary,
        downgrade_matrix=set(REQUIRED_DOWNGRADE_MATRIX),
        required_evidence_receipt_ids=[origin.receipt_id],
    )
    assert decision.route is EngineeringRoute.CONSOLIDATED_IMPLEMENTATION


def test_repeat_escape_and_alternate_path_freeze_microfix(tmp_path):
    governor = EngineeringExecutionGovernor(_store(tmp_path / "db"))
    governor.register_escape("REPEAT")
    assert governor.register_escape("REPEAT").microfix_frozen
    assert governor.register_escape("ALTERNATE", alternate_path=True).microfix_frozen


def test_incomplete_matrix_and_port_contract_block(tmp_path):
    store = _store(tmp_path / "db")
    governor, boundary, origin = _prepare_primary(store)
    incomplete = set(REQUIRED_DOWNGRADE_MATRIX) - {"restart_reopen"}
    decision = governor.admit_primary_implementation(
        problem_signature="ROOT", repository=REPOSITORY, capability_epoch=EPOCH,
        change_scope="BOUNDARY", boundary_map=boundary,
        downgrade_matrix=incomplete,
        required_evidence_receipt_ids=[origin.receipt_id],
    )
    assert decision.status == "COMPLETE_MATRIX_BEFORE_PRIMARY_WRITE"
    debt_governor, unsupported, evidence = _prepare_primary(
        _store(tmp_path / "debt.db"),
        problem="DEBT", boundary=_boundary(False),
    )
    debt = debt_governor.admit_primary_implementation(
        problem_signature="DEBT", repository=REPOSITORY, capability_epoch=EPOCH,
        change_scope="BOUNDARY", boundary_map=unsupported,
        downgrade_matrix=set(REQUIRED_DOWNGRADE_MATRIX),
        required_evidence_receipt_ids=[evidence.receipt_id],
    )
    assert debt.status == "PORT_CONTRACT_CAPABILITY_DEBT"


def test_policy_and_receipt_types_are_runtime_consumed(tmp_path):
    governor = EngineeringExecutionGovernor(_store(tmp_path / "db"))
    assert {
        "MANDATORY_EXTERNAL_ARCHITECTURE_SEARCH_BEFORE_WRITE",
        "CALLER_ASSERTION_NOT_TRUSTED_EVIDENCE",
        "EVIDENCE_PRODUCER_OWNERSHIP",
        "CLIENT_DOWNGRADE_INVARIANT",
        "UNATTESTED_EVIDENCE_DENY",
        "STATE_STORE_ACCESS_NOT_RECEIPT_ISSUER_ACCESS",
        "PRODUCER_SPECIFIC_SIGNING_AUTHORITY",
        "GOVERNOR_CONSUMES_EVIDENCE_ONLY",
    } <= set(governor.policy.invariants)
    assert set(governor.policy.required_downgrade_matrix) == REQUIRED_DOWNGRADE_MATRIX
