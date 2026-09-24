import json

from global_hybrid_v2.contracts import Owner, TaskRequest
from global_hybrid_v2.domains.library_projection import LibraryProjectionDomain
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.runtime.dispatcher import (
    NOT_EXECUTED_UPSTREAM_BLOCK,
    SNAPSHOT_COMPILATION_FAIL,
)
from tests.test_sales_consumption_e2e import _application


def _vehicle_request(request_text="2018 BMW 318I vehicle configuration lookup"):
    return TaskRequest.model_validate(
        {
            "request_text": request_text,
            "intent": "sales_human",
            "effects": ["read_only"],
            "vehicle_configuration_query": {
                "market": "TW",
                "model_year": 2018,
                "make": "BMW",
                "model": "318I",
            },
        }
    )


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


class CapturingLibraryProjectionDomain(LibraryProjectionDomain):
    def __init__(self):
        super().__init__()
        self.packet = None

    def project(self, request, *, task, authority):
        self.packet = super().project(request, task=task, authority=authority)
        return self.packet


def test_typed_vehicle_request_compiles_library_packet_without_media_consumption(
    tmp_path, capsys
):
    application = _application(tmp_path)
    library = CapturingLibraryProjectionDomain()
    application.dispatcher.domains[Owner.LIBRARY_FACT] = library

    result = application.dispatcher.dispatch(_vehicle_request())
    events = _events(capsys)
    stages = [event["stage"] for event in events]

    assert result.status == "SALES_VEHICLE_CONFIGURATION_GAP"
    assert result.output["state"] == "GAP"
    assert result.output["lookup_state"] == "PROVIDER_UNAVAILABLE"
    assert not any(
        finding.code == "RUNTIME_CONSUMPTION_PROOF_INCOMPLETE"
        for finding in application.trace.findings
    )
    required = [
        "current_authority",
        "task_contract",
        "owner_route",
        "firewall",
        "library_request",
        "library_boundary",
        "library_packet",
        "snapshot_compiled",
    ]
    assert [stages.index(stage) for stage in required] == sorted(
        stages.index(stage) for stage in required
    )
    request_event = next(event for event in events if event["stage"] == "library_request")
    boundary = next(event for event in events if event["stage"] == "library_boundary")
    packet_event = next(event for event in events if event["stage"] == "library_packet")
    assert request_event["metadata"]["projection"] == "vehicle_configuration_reference"
    assert boundary["metadata"]["mutation_allowed"] is False
    assert packet_event["metadata"]["projection"] == "vehicle_configuration_reference"
    assert not {
        "sales_adapter_bound",
        "sales_context_delivered",
        "sales_result",
        "fitness",
    } & set(stages)

    assert library.packet is not None
    assert library.packet.payload["lookup_state"] == "PROVIDER_UNAVAILABLE"
    assert library.packet.payload["lookup_state"] != "MISS"
    assert library.packet.payload["query"] == {
        "market": "TW",
        "model_year": 2018,
        "make": "BMW",
        "model": "318I",
        "generation": None,
        "trim": None,
        "vehicle_instance_id": None,
        "include_trim_matrix": True,
        "observed_equipment_keys": [],
        "hard_evidence_refs": [],
    }


def test_missing_vehicle_library_adapter_has_vehicle_only_failure_chain(tmp_path, capsys):
    application = _application(tmp_path)
    application.dispatcher.domains[Owner.LIBRARY_FACT] = NotConfiguredDomain(
        Owner.LIBRARY_FACT
    )

    result = application.dispatcher.dispatch(_vehicle_request())
    events = _events(capsys)
    by_stage = {event["stage"]: event for event in events}

    assert result.status == SNAPSHOT_COMPILATION_FAIL
    assert result.evidence["failure_locus"] == "library_request"
    assert by_stage["library_request"]["decision"] == "FAIL"
    for stage in ("library_boundary", "library_packet", "snapshot_compiled"):
        assert by_stage[stage]["decision"] == NOT_EXECUTED_UPSTREAM_BLOCK
    assert not {
        "sales_adapter_bound",
        "sales_context_delivered",
        "sales_result",
        "fitness",
    } & set(by_stage)


def test_multi_projection_builds_bounded_evidence_bundle(tmp_path, capsys):
    application = _application(tmp_path)
    result = application.dispatcher.dispatch(
        _vehicle_request("2018 BMW 318I Facebook media vehicle configuration")
    )
    events = _events(capsys)

    assert result.status == "SALES_EVIDENCE_BUNDLE_READY"
    assert result.output["state"] == "READY"
    assert len(result.output["projection_packets"]) == 2
    assert {item["evidence_role"] for item in result.output["projection_packets"]} == {
        "LIBRARY_EVIDENCE_NOT_SALES_DECISION",
        "LIBRARY_REFERENCE_NOT_INSTANCE_PROOF",
    }
    assert result.evidence["instance_trim_state"] == "UNRESOLVED"
    assert result.evidence["factory_provenance_state"] == "UNRESOLVED"
    assert sum(event["stage"] == "library_request" for event in events) == 2


def test_legacy_non_media_sales_does_not_request_library(tmp_path, capsys):
    application = _application(tmp_path)
    result = application.dispatcher.dispatch(
        TaskRequest.model_validate(
            {
                "request_text": "prepare an unrelated human sales follow-up",
                "intent": "sales_human",
                "effects": ["read_only"],
            }
        )
    )
    events = _events(capsys)
    assert result.status == "BLOCKED_NOT_CONFIGURED"
    assert not any(event["stage"] == "library_request" for event in events)
