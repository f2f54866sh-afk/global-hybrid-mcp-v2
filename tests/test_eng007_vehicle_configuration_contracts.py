import pytest
from pydantic import ValidationError

from global_hybrid_v2.contracts import (
    LibraryAccessRequest,
    TaskRequest,
    VehicleConfigurationQuery,
)
from global_hybrid_v2.domains.vehicle_configuration import (
    UnavailableVehicleConfigurationProvider,
    VehicleConfigurationLookupResult,
    VehicleConfigurationLookupState,
    VehicleConfigurationProvider,
    VehicleConfigurationReference,
    VehicleEquipmentClassification,
    VehicleEquipmentReference,
)


def _query(**changes):
    values = {"market": "TW", "model_year": 2018, "make": "BMW", "model": "318I"}
    values.update(changes)
    return VehicleConfigurationQuery(**values)


def _equipment(**changes):
    values = {
        "equipment_key": "sport-seat",
        "label": "Sport seat",
        "classification": "OPTION",
        "trim_ids": ["luxury"],
        "primary_source_pointer": "source:equipment",
        "last_verified": "2026-09-19",
    }
    values.update(changes)
    return VehicleEquipmentReference(**values)


def _reference(**changes):
    values = {
        "configuration_id": "tw-2018-318i",
        "market": "TW",
        "model_year": 2018,
        "make": "BMW",
        "model": "318I",
        "powertrain": {"fuel": "petrol"},
        "equipment": [_equipment()],
        "primary_source_pointers": ["source:configuration"],
        "last_verified": "2026-09-19",
        "conflict_state": "NONE",
        "query_key": "TW:2018:BMW:318I",
    }
    values.update(changes)
    return VehicleConfigurationReference(**values)


def test_valid_query_and_optional_fields_are_retained():
    query = _query(
        generation="F30",
        trim="Luxury",
        vehicle_instance_id="vehicle-1",
        include_trim_matrix=False,
        observed_equipment_keys=["sport-seat"],
        hard_evidence_refs=["invoice-1"],
    )
    assert query.market == "TW"
    assert query.generation == "F30"
    assert query.trim == "Luxury"
    assert query.vehicle_instance_id == "vehicle-1"
    assert query.include_trim_matrix is False
    assert query.observed_equipment_keys == ["sport-seat"]
    assert query.hard_evidence_refs == ["invoice-1"]


@pytest.mark.parametrize("field", ["market", "make", "model"])
def test_query_required_identifiers_reject_whitespace(field):
    with pytest.raises(ValidationError):
        _query(**{field: "   "})


@pytest.mark.parametrize("field", ["generation", "trim", "vehicle_instance_id"])
def test_query_optional_identifiers_reject_whitespace(field):
    with pytest.raises(ValidationError):
        _query(**{field: "   "})


@pytest.mark.parametrize("year", [0, 1885, 3001])
def test_query_invalid_model_year_rejected(year):
    with pytest.raises(ValidationError):
        _query(model_year=year)


def test_task_request_legacy_and_typed_compatibility():
    legacy = TaskRequest.model_validate(
        {"request_text": "legacy sales request", "intent": "sales_human"}
    )
    assert legacy.vehicle_configuration_query is None
    typed = TaskRequest.model_validate(
        {
            "request_text": "vehicle configuration request",
            "intent": "sales_human",
            "vehicle_configuration_query": _query().model_dump(),
        }
    )
    assert typed.vehicle_configuration_query == _query()


def test_unavailable_provider_is_explicit_and_satisfies_protocol():
    provider = UnavailableVehicleConfigurationProvider()
    result = provider.lookup(_query())
    assert isinstance(provider, VehicleConfigurationProvider)
    assert result.state is VehicleConfigurationLookupState.PROVIDER_UNAVAILABLE
    assert result.state is not VehicleConfigurationLookupState.MISS
    assert result.query == _query()
    assert result.configurations == []
    assert result.uncertainties and result.provenance
    assert result.provider_id.strip() and result.provider_version.strip()


@pytest.mark.parametrize(
    "field", ["equipment_key", "label", "primary_source_pointer", "last_verified"]
)
def test_equipment_required_strings_reject_whitespace(field):
    with pytest.raises(ValidationError):
        _equipment(**{field: "   "})


def test_equipment_trim_ids_and_classification_are_bounded():
    with pytest.raises(ValidationError):
        _equipment(trim_ids=["   "])
    for classification in VehicleEquipmentClassification:
        assert _equipment(classification=classification).classification is classification
    with pytest.raises(ValidationError):
        _equipment(classification="UNKNOWN")


@pytest.mark.parametrize(
    "field",
    [
        "configuration_id",
        "market",
        "make",
        "model",
        "last_verified",
        "conflict_state",
        "query_key",
    ],
)
def test_reference_required_strings_reject_whitespace(field):
    with pytest.raises(ValidationError):
        _reference(**{field: "   "})


@pytest.mark.parametrize("field", ["generation", "trim"])
def test_reference_optional_identifiers_reject_whitespace(field):
    with pytest.raises(ValidationError):
        _reference(**{field: "   "})


def test_reference_source_pointers_reject_whitespace():
    with pytest.raises(ValidationError):
        _reference(primary_source_pointers=["   "])


@pytest.mark.parametrize("field", ["provider_id", "provider_version"])
def test_lookup_provider_metadata_rejects_whitespace(field):
    values = {
        "state": "MISS",
        "query": _query(),
        "provider_id": "provider",
        "provider_version": "1",
    }
    values[field] = "   "
    with pytest.raises(ValidationError):
        VehicleConfigurationLookupResult(**values)


@pytest.mark.parametrize("field", ["uncertainties", "provenance"])
def test_lookup_lists_reject_whitespace(field):
    values = {
        "state": "MISS",
        "query": _query(),
        "provider_id": "provider",
        "provider_version": "1",
        field: ["   "],
    }
    with pytest.raises(ValidationError):
        VehicleConfigurationLookupResult(**values)


def test_library_access_request_does_not_gain_vehicle_query():
    assert "vehicle_configuration_query" not in LibraryAccessRequest.model_fields
