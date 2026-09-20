from __future__ import annotations

import json

import pytest

from global_hybrid_v2.adapters.file_vehicle_configuration import (
    FileVehicleConfigurationProvider,
)
from global_hybrid_v2.contracts import Owner
from global_hybrid_v2.domains.library_projection import LibraryProjectionDomain
from global_hybrid_v2.settings import Settings
from tests.test_eng007_vehicle_runtime_e2e import (
    FakeVehicleConfigurationProvider,
    _application,
    _events,
    _vehicle_request,
)


def _override_snapshot(path, snapshot_id):
    payload = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "source_revision": "override:v1",
        "generated_at": "2026-09-20T00:00:00Z",
        "configurations": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_package_resource_factory_loads_production_snapshot():
    provider = FileVehicleConfigurationProvider.from_package_resource()
    assert provider.provider_version == "vehicle-config-v1-4f4a27ddd89e09b6"
    assert len(provider.configurations) == 3


@pytest.mark.parametrize("absolute", [False, True])
def test_settings_snapshot_override_resolves_relative_and_absolute_paths(
    tmp_path, absolute
):
    from global_hybrid_v2.application import create_application

    snapshot = tmp_path / "overrides" / "vehicle.json"
    _override_snapshot(snapshot, f"override-{absolute}")
    configured_path = str(snapshot if absolute else snapshot.relative_to(tmp_path))
    application = create_application(
        repo_root=tmp_path,
        settings=Settings(vehicle_configuration_snapshot_path=configured_path),
    )
    library = application.dispatcher.domains[Owner.LIBRARY_FACT]
    assert isinstance(library, LibraryProjectionDomain)
    assert library.vehicle_configuration_provider.provider_version == f"override-{absolute}"


def test_explicit_provider_injection_has_highest_precedence(tmp_path):
    provider = FakeVehicleConfigurationProvider()
    application = _application(tmp_path, provider)
    library = application.dispatcher.domains[Owner.LIBRARY_FACT]
    assert library.vehicle_configuration_provider is provider


def test_default_provider_second_query_hit_and_noncovered_gaps(tmp_path, capsys):
    application = _application(tmp_path)
    request = _vehicle_request()
    first = application.dispatcher.dispatch(request)
    _events(capsys)
    second = application.dispatcher.dispatch(request)
    _events(capsys)
    for result in (first, second):
        assert result.status == "SALES_VEHICLE_CONFIGURATION_READY"
        assert result.output["lookup_state"] == "HIT"
    assert first.output["reference_configurations"] == second.output["reference_configurations"]

    for changes in ({"model_year": 2019}, {"market": "US"}):
        result = application.dispatcher.dispatch(_vehicle_request(**changes))
        _events(capsys)
        assert result.status == "SALES_VEHICLE_CONFIGURATION_GAP"
        assert result.output["lookup_state"] == "MISS"
