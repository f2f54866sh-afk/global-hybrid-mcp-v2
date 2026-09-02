from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from global_hybrid_v2.application import create_application
from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    ContractCurrentness,
    DomainContract,
    DomainContractStatus,
    DomainInteractionMode,
    DomainResult,
    EffectType,
    Intent,
    LibraryAccessKind,
    LibraryAccessRequest,
    Owner,
    RiskClass,
    TaskContract,
    TaskRequest,
)
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.domain_contract import (
    DomainContractError,
    DomainContractGate,
)
from global_hybrid_v2.governance.effects import EffectGate
from global_hybrid_v2.governance.fitness import SystemFitnessFunctions
from global_hybrid_v2.governance.library_boundary import (
    LibraryBoundaryError,
    LibraryReadWriteBoundary,
)
from global_hybrid_v2.governance.risk import TaskRiskClassifier
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


def _entry(owner: Owner, *, revision: str | None = None) -> AuthorityEntry:
    document = AuthorityDocument(
        name=owner.value,
        role=AuthorityDocumentRole.LIVE_AUTHORITY,
        revision=revision or f"{owner.value}_CURRENT",
        path=f"{owner.value}.md",
    )
    return AuthorityEntry(owner=owner, normative_authority=document)


def _snapshot() -> AuthoritySnapshot:
    entries = {owner: _entry(owner) for owner in Owner}
    real_car = AuthorityDocument(
        name="REAL_CAR",
        role=AuthorityDocumentRole.CANONICAL,
        revision="REAL_CAR_CURRENT",
        path="REAL_CAR_統一正式指令.md",
    )
    entries[Owner.VISUAL] = AuthorityEntry(
        owner=Owner.VISUAL,
        normative_authority=real_car,
        authority_partition="VISUAL_JUDGE",
    )
    entries[Owner.EXECUTION] = AuthorityEntry(
        owner=Owner.EXECUTION,
        normative_authority=real_car,
        authority_partition="EXECUTION_LAB",
    )
    sales_reference = AuthorityDocument(
        name="SALES_HUMAN_REFERENCE",
        role=AuthorityDocumentRole.REFERENCE_ONLY,
        revision="SALES_HUMAN_REFERENCE_CURRENT",
        path="SALES_HUMAN_CANONICAL.md",
    )
    entries[Owner.SALES_HUMAN] = AuthorityEntry(
        owner=Owner.SALES_HUMAN,
        normative_authority=entries[Owner.SALES_HUMAN].normative_authority,
        references=[sales_reference],
    )
    return AuthoritySnapshot(entries=entries)


class _StaticAuthority(AuthorityResolver):
    def __init__(self, snapshot: AuthoritySnapshot):
        self.snapshot = snapshot

    def resolve(self) -> AuthoritySnapshot:
        return self.snapshot


class _DoneDomain:
    def __init__(self):
        self.contracts: list[TaskContract] = []

    def run(self, contract: TaskContract) -> DomainResult:
        self.contracts.append(contract)
        return DomainResult(owner=contract.owner, status="DONE", output={"ok": True})


def _passing_contract(**updates: object) -> DomainContract:
    data: dict[str, object] = {
        "task_trace_id": "trace-1",
        "provider_owner": Owner.LIBRARY_FACT,
        "consumer_owner": Owner.SALES_HUMAN,
        "task_scope": "vehicle fact projection",
        "source_authority_revision": "LIBRARY_FACT_CURRENT",
        "requirement_ids": ["REQ-1"],
        "required_fields": {"vehicle_id", "verified_year"},
        "optional_fields": {"market_price"},
        "used_fields": {"vehicle_id", "verified_year"},
        "blocked_foreign_fields": {"internal_conflict_notes"},
        "currentness": ContractCurrentness.CURRENT,
        "provenance": ["library-fact:vehicle-1"],
        "status": DomainContractStatus.PASS,
        "interaction_mode": DomainInteractionMode.SERVICE,
        "payload": {"vehicle_id": "vehicle-1", "verified_year": 2024},
    }
    data.update(updates)
    return DomainContract.model_validate(data)


def test_domain_contract_is_consumer_driven_and_authority_bound():
    contract = _passing_contract()

    admission = DomainContractGate().admit(
        contract,
        consumer=Owner.SALES_HUMAN,
        authority=_snapshot(),
    )

    assert admission.decision == "PASS"
    assert admission.provider_owner is Owner.LIBRARY_FACT
    assert contract.payload["verified_year"] == 2024


def test_domain_contract_rejects_foreign_field_consumption_and_revision_drift():
    with pytest.raises(ValidationError, match="undeclared contract fields"):
        _passing_contract(used_fields={"vehicle_id", "internal_conflict_notes"})

    with pytest.raises(DomainContractError, match="authority revision mismatch"):
        DomainContractGate().admit(
            _passing_contract(source_authority_revision="STALE"),
            consumer=Owner.SALES_HUMAN,
            authority=_snapshot(),
        )


def test_library_write_plane_is_exclusive_but_signals_and_projections_are_read_only():
    boundary = LibraryReadWriteBoundary()
    with pytest.raises(LibraryBoundaryError, match="only LIBRARY_FACT"):
        boundary.authorize(
            LibraryAccessRequest(
                actor_owner=Owner.SALES_HUMAN,
                access_kind=LibraryAccessKind.COMMIT_FACT,
                task_scope="change vehicle year",
            )
        )

    signal = boundary.authorize(
        LibraryAccessRequest(
            actor_owner=Owner.VISUAL,
            access_kind=LibraryAccessKind.FACT_NEED_SIGNAL,
            task_scope="missing vehicle color evidence",
        )
    )
    projection = boundary.authorize(
        LibraryAccessRequest(
            actor_owner=Owner.EXECUTION,
            access_kind=LibraryAccessKind.READ_PROJECTION,
            task_scope="instance rendering",
            projection="execution_instance_projection",
        )
    )

    assert signal.allowed and not signal.mutation_allowed
    assert projection.allowed and not projection.mutation_allowed


def test_policy_decision_is_distinct_from_pre_domain_enforcement():
    decision = EffectGate().decide(Owner.VISUAL, [EffectType.EXTERNAL_WRITE])

    assert not decision.allowed
    assert decision.policy_decision_point == "GLOBAL_EFFECT_POLICY"
    assert decision.enforcement_point == "DISPATCHER_PRE_DOMAIN"


@pytest.mark.parametrize(
    ("effects", "expected"),
    [
        ([EffectType.READ_ONLY], RiskClass.R0),
        ([EffectType.MODEL_INFERENCE], RiskClass.R1),
        ([EffectType.EXTERNAL_READ], RiskClass.R2),
        ([EffectType.IMAGE_GENERATE], RiskClass.R3),
        ([EffectType.FILE_WRITE], RiskClass.R4),
        ([EffectType.EXTERNAL_WRITE], RiskClass.R4),
    ],
)
def test_risk_class_uses_only_required_effect_floor(effects, expected):
    request = TaskRequest(
        request_text="bounded operation",
        intent=Intent.EXECUTION,
        effects=effects,
    )
    assert TaskRiskClassifier().classify(request) is expected


def test_application_fitness_attaches_read_only_witness_to_exact_owner_topology():
    application = create_application()

    assert application.composition_fitness is not None
    assert application.composition_fitness.passed
    assert isinstance(application.trace.witness, ReadOnlyWitness)

    authority_fitness = SystemFitnessFunctions.evaluate_authority(_snapshot())
    assert authority_fitness.passed


def test_governed_task_has_unique_trace_owner_spans_and_no_prompt_dump(capsys):
    domain = _DoneDomain()
    trace = TraceBus(witness=ReadOnlyWitness())
    dispatcher = Dispatcher(
        authority=_StaticAuthority(_snapshot()),
        domains={Owner.EXECUTION: domain},
        trace=trace,
    )
    request = TaskRequest(
        request_text="private prompt content must not enter trace",
        intent=Intent.EXECUTION,
        effects=[EffectType.READ_ONLY],
    )

    dispatcher.dispatch(request)
    dispatcher.dispatch(request)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    task_ids = {event["task_id"] for event in events}

    assert len(task_ids) == 2
    traces_by_task = {
        task_id: {event["trace_id"] for event in events if event["task_id"] == task_id}
        for task_id in task_ids
    }
    assert all(len(trace_ids) == 1 for trace_ids in traces_by_task.values())
    assert len({next(iter(trace_ids)) for trace_ids in traces_by_task.values()}) == 2

    first_task = next(iter(task_ids))
    first_task_events = [event for event in events if event["task_id"] == first_task]
    assert {event["span_owner"] for event in first_task_events} >= {
        "GLOBAL",
        "EXECUTION",
        "WITNESS",
    }
    domain_complete = next(
        event
        for event in first_task_events
        if event["stage"] == "closure" and event["decision"] == "DONE"
    )
    assert domain_complete["metadata"]["input_contract_id"]
    assert domain_complete["metadata"]["authority_revision"] == "REAL_CAR_CURRENT"
    assert domain_complete["metadata"]["consumed_fields"] == []
    assert domain_complete["metadata"]["output_id"]
    assert "private prompt content" not in json.dumps(events)


def test_fitness_rejects_missing_owner_and_unattached_witness():
    report = SystemFitnessFunctions.evaluate_composition(
        domains={Owner.GLOBAL: NotConfiguredDomain(Owner.GLOBAL)},
        trace=TraceBus(),
    )

    assert not report.passed
    assert {check.name for check in report.checks if not check.passed} == {
        "CURRENT_OWNER_TOPOLOGY",
        "WITNESS_ALWAYS_ATTACHED",
        "WITNESS_ZERO_MUTATION_API",
    }


def test_signed_authority_artifacts_are_checkout_byte_stable():
    attributes = set(Path(".gitattributes").read_text(encoding="utf-8").splitlines())
    assert "/authority/current/registry.json -text" in attributes
    assert "/authority/current/activation.json -text" in attributes
    assert b"\r\n" not in Path("authority/current/registry.json").read_bytes()
