from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from global_hybrid_v2.application import create_application
from global_hybrid_v2.contracts import Owner, TaskRequest
from global_hybrid_v2.domains.library_projection import LibraryProjectionDomain
from global_hybrid_v2.domains.sales_human import SalesHumanDomain
from global_hybrid_v2.domains.vehicle_configuration import (
    VehicleConfigurationLookupResult,
    VehicleConfigurationLookupState,
    VehicleConfigurationReference,
    VehicleEquipmentClassification,
    VehicleEquipmentReference,
)
from global_hybrid_v2.settings import Settings
from tests._authority_signing import TEST_KEY_ID, TEST_PUBLIC_KEY, activate_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICALS = (
    "GLOBAL_WINDOW_CANONICAL.md",
    "SALES_CANONICAL.md",
    "SALES_HUMAN_CANONICAL.md",
    "VEHICLE_KNOWLEDGE_BASE.md",
    "REAL_CAR_統一正式指令.md",
)
MEDIA_REQUEST = (
    "2021 Toyota Sienta 1.8，要在 Facebook 投放廣告，分析適合的年齡、"
    "地區、客群設定與投放策略。"
)


class FakeVehicleConfigurationProvider:
    provider_id = "fixture"
    provider_version = "v1"

    def __init__(self, state: VehicleConfigurationLookupState = VehicleConfigurationLookupState.HIT):
        self.state = state

    def lookup(self, query):
        configurations = self._configurations() if self.state is VehicleConfigurationLookupState.HIT else []
        state = self.state
        if query.market != "TW":
            state = VehicleConfigurationLookupState.MISS
            configurations = []
        return VehicleConfigurationLookupResult(
            state=state,
            query=query,
            configurations=configurations,
            uncertainties=[] if configurations else [f"lookup state: {state.value}"],
            provenance=["provider:fixture:v1"],
            provider_id=self.provider_id,
            provider_version=self.provider_version,
        )

    @staticmethod
    def _configurations():
        shared = {
            "market": "TW",
            "model_year": 2018,
            "make": "BMW",
            "model": "318I",
            "generation": "F30",
            "powertrain": {"fuel": "gasoline"},
            "primary_source_pointers": ["fixture:tw-2018-bmw-318i"],
            "last_verified": "2026-09-20",
            "conflict_state": "NONE",
            "query_key": "TW:2018:BMW:318I",
        }
        return [
            VehicleConfigurationReference(
                configuration_id="base",
                trim="Base",
                equipment=[
                    _equipment("SPORT_SEAT", "Sport seat", "OPTION", ["base"]),
                    _equipment("HARMAN_KARDON", "Harman Kardon", "PACKAGE", ["base"]),
                ],
                **shared,
            ),
            VehicleConfigurationReference(
                configuration_id="luxury",
                trim="Luxury",
                equipment=[
                    _equipment("SPORT_SEAT", "Sport seat", "DISCRIMINATOR", ["luxury"]),
                    _equipment(
                        "BMW_INDIVIDUAL_STEERING_WHEEL",
                        "BMW Individual steering wheel",
                        "OPTION",
                        ["luxury"],
                    ),
                    _equipment("HARMAN_KARDON", "Harman Kardon", "PACKAGE", ["luxury"]),
                ],
                **shared,
            ),
        ]


def _equipment(key, label, classification, trim_ids):
    return VehicleEquipmentReference(
        equipment_key=key,
        label=label,
        classification=VehicleEquipmentClassification(classification),
        trim_ids=trim_ids,
        primary_source_pointer=f"fixture:{key}",
        last_verified="2026-09-20",
    )


def _application(tmp_path: Path, provider=None):
    registry = tmp_path / "authority" / "current" / "registry.json"
    registry.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "authority/current/registry.json", registry)
    for filename in CANONICALS:
        shutil.copy2(REPO_ROOT / filename, tmp_path / filename)
    activate_registry(registry)
    return create_application(
        repo_root=tmp_path,
        settings=Settings(
            authority_trusted_key_id=TEST_KEY_ID,
            authority_trusted_public_key=TEST_PUBLIC_KEY,
        ),
        vehicle_configuration_provider=provider,
    )


def _vehicle_request(**query_changes):
    query = {
        "market": "TW",
        "model_year": 2018,
        "make": "BMW",
        "model": "318I",
    }
    query.update(query_changes)
    return TaskRequest.model_validate(
        {
            "request_text": "2018 BMW 318I vehicle configuration lookup",
            "intent": "sales_human",
            "effects": ["read_only"],
            "vehicle_configuration_query": query,
        }
    )


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_default_provider_runtime_returns_hit_with_vehicle_only_trace(tmp_path, capsys):
    application = _application(tmp_path)
    result = application.dispatcher.dispatch(_vehicle_request())
    events = _events(capsys)

    assert result.status == "SALES_VEHICLE_CONFIGURATION_READY"
    assert result.output["state"] == "READY"
    assert result.output["lookup_state"] == "HIT"
    assert [item["configuration_id"] for item in result.output["reference_configurations"]] == [
        "TW-BMW-F30LCI-318I-2017M08-BASE",
        "TW-BMW-F30LCI-318I-2018M07-LUXWHITE",
    ]
    assert result.output["instance_trim_state"] == "UNRESOLVED"
    assert result.output["factory_provenance_state"] == "UNRESOLVED"
    stages = [event["stage"] for event in events]
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
    assert not {"sales_adapter_bound", "sales_context_delivered", "sales_result", "fitness"} & set(stages)
    boundary = next(event for event in events if event["stage"] == "library_boundary")
    packet = next(event for event in events if event["stage"] == "library_packet")
    assert boundary["metadata"]["mutation_allowed"] is False
    assert packet["metadata"]["projection"] == "vehicle_configuration_reference"
    assert not any(
        finding.code == "RUNTIME_CONSUMPTION_PROOF_INCOMPLETE"
        for finding in application.trace.findings
    )


def test_hit_provider_composition_and_reference_runtime(tmp_path, capsys):
    provider = FakeVehicleConfigurationProvider()
    application = _application(tmp_path, provider)

    assert isinstance(application.dispatcher.domains[Owner.SALES_HUMAN], SalesHumanDomain)
    library = application.dispatcher.domains[Owner.LIBRARY_FACT]
    assert isinstance(library, LibraryProjectionDomain)
    assert library.vehicle_configuration_provider is provider
    assert application.composition_fitness is not None
    assert application.composition_fitness.passed is True

    result = application.dispatcher.dispatch(_vehicle_request())
    _events(capsys)
    assert result.status == "SALES_VEHICLE_CONFIGURATION_READY"
    assert result.output["state"] == "READY"
    assert result.output["lookup_state"] == "HIT"
    assert result.output["reference_configurations"]
    assert result.output["trim_matrix"]
    assert result.output["instance_trim_state"] == "UNRESOLVED"
    assert result.output["factory_provenance_state"] == "UNRESOLVED"


def test_observed_equipment_remains_supporting_reference_only(tmp_path, capsys):
    application = _application(tmp_path, FakeVehicleConfigurationProvider())
    result = application.dispatcher.dispatch(
        _vehicle_request(
            observed_equipment_keys=[
                "SPORT_SEAT",
                "BMW_INDIVIDUAL_STEERING_WHEEL",
                "HARMAN_KARDON",
            ]
        )
    )
    _events(capsys)
    matches = {item["equipment_key"]: item for item in result.output["observed_equipment_matches"]}
    assert set(matches) == {
        "SPORT_SEAT",
        "BMW_INDIVIDUAL_STEERING_WHEEL",
        "HARMAN_KARDON",
    }
    assert matches["SPORT_SEAT"]["matched_configuration_ids"] == ["base", "luxury"]
    assert matches["BMW_INDIVIDUAL_STEERING_WHEEL"]["matched_configuration_ids"] == ["luxury"]
    assert all(item["evidence_role"] == "SUPPORTING_REFERENCE_MATCH_ONLY" for item in matches.values())
    assert result.output["instance_trim_state"] == "UNRESOLVED"
    assert result.output["factory_provenance_state"] == "UNRESOLVED"


@pytest.mark.parametrize(
    ("query_changes", "provider_state", "expected_state"),
    [
        ({"market": "US"}, VehicleConfigurationLookupState.HIT, "MISS"),
        ({}, VehicleConfigurationLookupState.STALE, "STALE"),
        ({}, VehicleConfigurationLookupState.CONFLICT, "CONFLICT"),
    ],
)
def test_non_hit_states_are_preserved_without_foreign_market_rows(
    tmp_path, capsys, query_changes, provider_state, expected_state
):
    application = _application(tmp_path, FakeVehicleConfigurationProvider(provider_state))
    result = application.dispatcher.dispatch(_vehicle_request(**query_changes))
    _events(capsys)
    assert result.status == "SALES_VEHICLE_CONFIGURATION_GAP"
    assert result.output["lookup_state"] == expected_state
    assert result.output["reference_configurations"] == []


def test_legacy_sales_remains_blocked_and_multi_projection_returns_bundle(tmp_path, capsys):
    application = _application(tmp_path, FakeVehicleConfigurationProvider())
    legacy = application.dispatcher.dispatch(
        TaskRequest.model_validate(
            {
                "request_text": "prepare an unrelated human sales follow-up",
                "intent": "sales_human",
                "effects": ["read_only"],
            }
        )
    )
    legacy_events = _events(capsys)
    assert legacy.status == "BLOCKED_NOT_CONFIGURED"
    assert not any(event["stage"] == "library_request" for event in legacy_events)

    multi = _vehicle_request().model_copy(update={"request_text": MEDIA_REQUEST})
    result = application.dispatcher.dispatch(multi)
    events = _events(capsys)
    assert result.status == "SALES_EVIDENCE_BUNDLE_READY"
    assert len(result.output["projection_packets"]) == 2
    assert sum(event["stage"] == "library_request" for event in events) == 2
