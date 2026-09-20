from __future__ import annotations

import json

import pytest

from global_hybrid_v2.adapters.file_vehicle_configuration import (
    FileVehicleConfigurationProvider,
)
from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.domains.vehicle_configuration import VehicleConfigurationLookupState


def _configuration(identifier="base", **changes):
    value = {
        "configuration_id": identifier,
        "market": "TW",
        "model_year": 2018,
        "make": "BMW",
        "model": "318I",
        "generation": "F30 LCI",
        "trim": "Base" if identifier == "base" else "Luxury",
        "powertrain": {"engine": "gasoline"},
        "equipment": [],
        "primary_source_pointers": [f"source:{identifier}", "source:shared"],
        "last_verified": "2026-09-19",
        "conflict_state": "NO_CONFLICT",
        "query_key": "TW:2018:BMW:318I",
    }
    value.update(changes)
    return value


def _snapshot(**changes):
    value = {
        "schema_version": 1,
        "snapshot_id": "vehicle-config-fixture-v1",
        "source_revision": "LIBRARY_FIXTURE_V1",
        "generated_at": "2026-09-20T00:00:00Z",
        "configurations": [_configuration(), _configuration("luxury")],
    }
    value.update(changes)
    return value


def _provider(tmp_path, snapshot=None):
    path = tmp_path / "vehicle-config.json"
    path.write_text(json.dumps(snapshot or _snapshot()), encoding="utf-8")
    return FileVehicleConfigurationProvider(path)


def _query(**changes):
    value = {"market": "TW", "model_year": 2018, "make": "BMW", "model": "318I"}
    value.update(changes)
    return VehicleConfigurationQuery(**value)


def test_valid_hit_matrix_casefold_and_snapshot_provenance(tmp_path):
    result = _provider(tmp_path).lookup(_query(market="tw", make="bmw", model="318i"))
    assert result.state is VehicleConfigurationLookupState.HIT
    assert [item.configuration_id for item in result.configurations] == ["base", "luxury"]
    assert result.provider_id == "file-vehicle-configuration"
    assert result.provider_version == "vehicle-config-fixture-v1"
    assert result.provenance == [
        "snapshot:vehicle-config-fixture-v1",
        "source-revision:LIBRARY_FIXTURE_V1",
        "source:base",
        "source:shared",
        "source:luxury",
    ]


@pytest.mark.parametrize("changes", [{"market": "US"}, {"model_year": 2019}])
def test_wrong_base_identity_is_miss(tmp_path, changes):
    result = _provider(tmp_path).lookup(_query(**changes))
    assert result.state is VehicleConfigurationLookupState.MISS
    assert result.configurations == []


def test_generation_and_trim_are_case_insensitive_exact_filters(tmp_path):
    provider = _provider(tmp_path)
    generation = provider.lookup(_query(generation="f30 lci"))
    trim = provider.lookup(_query(trim="luxury"))
    wrong_generation = provider.lookup(_query(generation="F31"))
    assert len(generation.configurations) == 2
    assert [item.configuration_id for item in trim.configurations] == ["luxury"]
    assert wrong_generation.state is VehicleConfigurationLookupState.MISS


def test_reference_inputs_do_not_narrow_matrix(tmp_path):
    query = _query(
        vehicle_instance_id="VIN-1",
        observed_equipment_keys=["SPORT_SEAT"],
        hard_evidence_refs=["BUILD-SHEET-1"],
    )
    result = _provider(tmp_path).lookup(query)
    assert result.query is query
    assert [item.configuration_id for item in result.configurations] == ["base", "luxury"]
    assert result.uncertainties == ["VEHICLE_INSTANCE_NOT_RESOLVED_BY_REFERENCE_PROVIDER"]


def test_matching_conflict_is_preserved(tmp_path):
    snapshot = _snapshot(configurations=[_configuration(conflict_state="SOURCE_CONFLICT")])
    result = _provider(tmp_path, snapshot).lookup(_query())
    assert result.state is VehicleConfigurationLookupState.CONFLICT


def test_missing_file_fails_fast(tmp_path):
    with pytest.raises(RuntimeError):
        FileVehicleConfigurationProvider(tmp_path / "missing.json")


def test_invalid_json_fails_fast(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        FileVehicleConfigurationProvider(path)


@pytest.mark.parametrize("version", [0, 2, True, "1"])
def test_unsupported_schema_version_fails_fast(tmp_path, version):
    with pytest.raises(ValueError):
        _provider(tmp_path, _snapshot(schema_version=version))


@pytest.mark.parametrize("field", ["snapshot_id", "source_revision", "generated_at"])
def test_blank_required_snapshot_metadata_fails_fast(tmp_path, field):
    with pytest.raises(ValueError):
        _provider(tmp_path, _snapshot(**{field: "   "}))


def test_non_list_configurations_fails_fast(tmp_path):
    with pytest.raises(ValueError):
        _provider(tmp_path, _snapshot(configurations={}))


def test_one_malformed_configuration_invalidates_whole_snapshot(tmp_path):
    malformed = _configuration(model="   ")
    with pytest.raises(ValueError):
        _provider(tmp_path, _snapshot(configurations=[_configuration(), malformed]))


def test_package_resource_provider_remains_usable_without_temporary_path():
    provider = FileVehicleConfigurationProvider.from_package_resource()
    assert provider.snapshot_path is None
    assert (
        provider.snapshot_resource
        == "global_hybrid_v2:data/vehicle_configuration_current.json"
    )
    assert provider.provider_version == "vehicle-config-v1-4f4a27ddd89e09b6"
    result = provider.lookup(_query())
    assert result.state is VehicleConfigurationLookupState.HIT
