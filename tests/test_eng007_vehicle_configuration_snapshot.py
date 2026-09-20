from pathlib import Path

from global_hybrid_v2.adapters.file_vehicle_configuration import (
    FileVehicleConfigurationProvider,
)
from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.domains.vehicle_configuration import (
    VehicleConfigurationLookupState,
    VehicleEquipmentClassification,
)

SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "src/global_hybrid_v2/data/vehicle_configuration_current.json"
)
BASE = "TW-BMW-F30LCI-318I-2017M08-BASE"
LUXURY = "TW-BMW-F30LCI-318I-2018M07-LUXWHITE"


def _query(**changes):
    values = {"market": "TW", "model_year": 2018, "make": "BMW", "model": "318I"}
    values.update(changes)
    return VehicleConfigurationQuery(**values)


def test_snapshot_cardinality_identity_and_source_integrity():
    provider = FileVehicleConfigurationProvider(SNAPSHOT)
    assert provider.provider_version == "vehicle-config-v1-4f4a27ddd89e09b6"
    assert len(provider.configurations) == 3
    assert len({(item.configuration_id, item.model_year) for item in provider.configurations}) == 3
    assert [(item.configuration_id, item.model_year) for item in provider.configurations] == [
        (BASE, 2017),
        (BASE, 2018),
        (LUXURY, 2018),
    ]
    base_rows = [item for item in provider.configurations if item.configuration_id == BASE]
    assert [[fact.equipment_key for fact in row.equipment] for row in base_rows] == [
        [f"BMW318I-BASE-{number:03d}" for number in range(1, 5)],
        [f"BMW318I-BASE-{number:03d}" for number in range(1, 5)],
    ]
    luxury = next(item for item in provider.configurations if item.configuration_id == LUXURY)
    assert len(base_rows[0].equipment) == 4
    assert len(luxury.equipment) == 11
    assert all(
        fact.classification is VehicleEquipmentClassification.STANDARD
        for row in provider.configurations
        for fact in row.equipment
    )
    assert all(
        fact.equipment_key.startswith(("BMW318I-BASE-", "BMW318I-LUX-"))
        for row in provider.configurations
        for fact in row.equipment
    )
    assert all(row.conflict_state == "NO_CONFLICT" for row in provider.configurations)
    assert all(row.last_verified == "2026-09-19" for row in provider.configurations)


def test_snapshot_exact_lookup_projection_and_provenance():
    provider = FileVehicleConfigurationProvider(SNAPSHOT)
    result_2018 = provider.lookup(_query())
    assert result_2018.state is VehicleConfigurationLookupState.HIT
    assert [item.configuration_id for item in result_2018.configurations] == [BASE, LUXURY]
    assert "source-revision:libfile_6af09104d854819180eb56566dfa7f02:v1" in result_2018.provenance

    result_2017 = provider.lookup(_query(model_year=2017))
    assert result_2017.state is VehicleConfigurationLookupState.HIT
    assert [item.configuration_id for item in result_2017.configurations] == [BASE]

    for changes in ({"model_year": 2019}, {"market": "US"}):
        result = provider.lookup(_query(**changes))
        assert result.state is VehicleConfigurationLookupState.MISS
        assert result.configurations == []


def test_snapshot_trim_filters_are_exact():
    provider = FileVehicleConfigurationProvider(SNAPSHOT)
    luxury = provider.lookup(_query(trim="豪華白金版"))
    base = provider.lookup(_query(trim="318i"))
    assert [item.configuration_id for item in luxury.configurations] == [LUXURY]
    assert [item.configuration_id for item in base.configurations] == [BASE]
