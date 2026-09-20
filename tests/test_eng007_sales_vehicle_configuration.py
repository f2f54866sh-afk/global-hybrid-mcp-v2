import pytest

from global_hybrid_v2.contracts import (
    ContractCurrentness,
    DomainContract,
    DomainContractStatus,
    DomainInteractionMode,
    OutputClassification,
    Owner,
    TaskContract,
    VehicleConfigurationQuery,
)
from global_hybrid_v2.domains.sales_vehicle_configuration import (
    SalesVehicleConfigurationDomain,
)


def _query(**changes):
    values = {
        "market": "TW",
        "model_year": 2018,
        "make": "BMW",
        "model": "318I",
        "observed_equipment_keys": [],
        "hard_evidence_refs": [],
    }
    values.update(changes)
    return VehicleConfigurationQuery(**values)


def _configurations():
    return [
        {
            "configuration_id": "base",
            "equipment": [
                {"equipment_key": "SPORT_SEAT", "classification": "OPTION"},
                {"equipment_key": "HARMAN_KARDON", "classification": "PACKAGE"},
            ],
        },
        {
            "configuration_id": "lux",
            "equipment": [
                {"equipment_key": "SPORT_SEAT", "classification": "DISCRIMINATOR"},
                {
                    "equipment_key": "BMW_INDIVIDUAL_STEERING_WHEEL",
                    "classification": "OPTION",
                },
                {"equipment_key": "HARMAN_KARDON", "classification": "PACKAGE"},
            ],
        },
    ]


def _task(*, query=None, owner=Owner.SALES_HUMAN, packets=None):
    query = _query() if query is None else query
    task = TaskContract(
        task_trace_id="trace-current",
        request_text="vehicle config",
        intent="sales_human",
        owner=owner,
        effects=[],
        authority_snapshot_id="snapshot",
        context=[],
        vehicle_configuration_query=query,
    )
    packet = _packet(task, query=query) if packets is None else None
    return task.model_copy(
        update={"domain_contracts": packets if packets is not None else [packet]}
    )


def _packet(
    task,
    *,
    query=None,
    lookup_state="HIT",
    configurations=None,
    status=DomainContractStatus.PASS,
    evidence_role="LIBRARY_REFERENCE_NOT_INSTANCE_PROOF",
    task_trace_id=None,
):
    query = query or task.vehicle_configuration_query
    payload = {
        "library_request_id": "request-1",
        "projection": "vehicle_configuration_reference",
        "contract_version": 1,
        "source_scope": "vehicle config",
        "evidence_role": evidence_role,
        "lookup_state": lookup_state,
        "query": query.model_dump(mode="json"),
        "configurations": _configurations() if configurations is None else configurations,
        "uncertainties": ["bounded-reference-only"],
        "provider_id": "fixture",
        "provider_version": "v1",
    }
    fields = set(payload)
    return DomainContract(
        task_trace_id=task_trace_id or task.task_trace_id,
        provider_owner=Owner.LIBRARY_FACT,
        consumer_owner=Owner.SALES_HUMAN,
        task_scope="vehicle config",
        source_authority_revision="LIBRARY_REV",
        requirement_ids=["VEHICLE_CONFIGURATION_REFERENCE_NEED"],
        required_fields=fields,
        used_fields=fields,
        currentness=ContractCurrentness.CURRENT,
        provenance=["library-authority:LIBRARY_REV", "provider:fixture:v1"],
        status=status,
        interaction_mode=DomainInteractionMode.SERVICE,
        payload=payload,
    )


def test_hit_returns_reference_ready_without_resolving_instance_or_factory():
    task = _task()
    result = SalesVehicleConfigurationDomain().run(task)
    assert result.status == "SALES_VEHICLE_CONFIGURATION_READY"
    assert result.output["state"] == "READY"
    assert result.output["lookup_state"] == "HIT"
    assert result.output["reference_configurations"] == _configurations()
    assert result.output["trim_matrix"] == _configurations()
    assert result.output["instance_trim_state"] == "UNRESOLVED"
    assert result.output["factory_provenance_state"] == "UNRESOLVED"
    assert result.evidence["reference_is_instance_proof"] is False
    assert result.evidence["factory_provenance_resolved"] is False
    assert result.output_classifications == {OutputClassification.DIAGNOSIS_ONLY}


def test_observed_equipment_is_supporting_only_and_preserves_unmatched_key():
    query = _query(
        observed_equipment_keys=[
            "SPORT_SEAT",
            "BMW_INDIVIDUAL_STEERING_WHEEL",
            "HARMAN_KARDON",
            "UNKNOWN_VISIBLE_FEATURE",
        ]
    )
    result = SalesVehicleConfigurationDomain().run(_task(query=query))
    matches = {item["equipment_key"]: item for item in result.output["observed_equipment_matches"]}
    assert matches["SPORT_SEAT"]["matched_configuration_ids"] == ["base", "lux"]
    assert matches["SPORT_SEAT"]["reference_classifications"] == ["OPTION", "DISCRIMINATOR"]
    assert matches["HARMAN_KARDON"]["matched_configuration_ids"] == ["base", "lux"]
    assert matches["UNKNOWN_VISIBLE_FEATURE"]["matched_configuration_ids"] == []
    assert matches["UNKNOWN_VISIBLE_FEATURE"]["reference_classifications"] == []
    assert all(
        item["evidence_role"] == "SUPPORTING_REFERENCE_MATCH_ONLY"
        for item in matches.values()
    )
    assert result.output["instance_trim_state"] == "UNRESOLVED"
    assert result.output["factory_provenance_state"] == "UNRESOLVED"


def test_hard_evidence_and_explicit_trim_do_not_self_adjudicate():
    query = _query(
        trim="Luxury",
        hard_evidence_refs=["VIN:TEST", "BUILD_SHEET:TEST"],
    )
    result = SalesVehicleConfigurationDomain().run(_task(query=query))
    assert result.output["hard_evidence_refs"] == ["VIN:TEST", "BUILD_SHEET:TEST"]
    assert result.output["trim_matrix"] == []
    assert result.output["instance_trim_state"] == "UNRESOLVED"
    assert result.output["factory_provenance_state"] == "UNRESOLVED"


@pytest.mark.parametrize(
    "lookup_state",
    ["PARTIAL", "MISS", "STALE", "CONFLICT", "PROVIDER_UNAVAILABLE"],
)
def test_non_hit_lookup_states_are_preserved_as_gap(lookup_state):
    task = _task()
    packet = _packet(task, lookup_state=lookup_state)
    result = SalesVehicleConfigurationDomain().run(
        task.model_copy(update={"domain_contracts": [packet]})
    )
    assert result.status == "SALES_VEHICLE_CONFIGURATION_GAP"
    assert result.output["state"] == "GAP"
    assert result.output["lookup_state"] == lookup_state
    assert result.output_classifications == {OutputClassification.DIAGNOSIS_ONLY}


def test_hit_without_configurations_is_gap():
    task = _task()
    packet = _packet(task, configurations=[])
    result = SalesVehicleConfigurationDomain().run(
        task.model_copy(update={"domain_contracts": [packet]})
    )
    assert result.status == "SALES_VEHICLE_CONFIGURATION_GAP"
    assert result.output["state"] == "GAP"


def test_packet_provenance_and_consumption_evidence_are_preserved():
    task = _task()
    packet = task.domain_contracts[0]
    result = SalesVehicleConfigurationDomain().run(task)
    assert result.evidence["library_request_id"] == "request-1"
    assert result.evidence["library_packet_id"] == packet.contract_id
    assert result.evidence["projection"] == "vehicle_configuration_reference"
    assert result.evidence["source_authority_revision"] == "LIBRARY_REV"
    assert result.evidence["provenance"] == packet.provenance
    assert result.evidence["lookup_state"] == "HIT"
    assert result.evidence["actual_consumed_context"] == sorted(packet.used_fields)


def test_owner_query_and_packet_cardinality_fail_closed():
    domain = SalesVehicleConfigurationDomain()
    with pytest.raises(ValueError):
        domain.run(_task(owner=Owner.VISUAL))
    missing_query = _task().model_copy(update={"vehicle_configuration_query": None})
    with pytest.raises(ValueError):
        domain.run(missing_query)
    with pytest.raises(ValueError):
        domain.run(_task(packets=[]))
    task = _task()
    with pytest.raises(ValueError):
        domain.run(task.model_copy(update={"domain_contracts": task.domain_contracts * 2}))


def test_packet_status_role_task_and_query_bindings_fail_closed():
    domain = SalesVehicleConfigurationDomain()
    task = _task()
    invalid_packets = [
        _packet(task, status=DomainContractStatus.HOLD),
        _packet(task, evidence_role="WRONG_ROLE"),
        _packet(task, task_trace_id="foreign-trace"),
        _packet(task, query=_query(model_year=2017)),
    ]
    for packet in invalid_packets:
        with pytest.raises(ValueError):
            domain.run(task.model_copy(update={"domain_contracts": [packet]}))
