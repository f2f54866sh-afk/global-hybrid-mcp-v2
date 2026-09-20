from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.domains.vehicle_configuration import (
    VehicleConfigurationLookupResult,
    VehicleConfigurationLookupState,
    VehicleConfigurationReference,
)
from global_hybrid_v2.settings import Settings


class FileVehicleConfigurationProvider:
    provider_id = "file-vehicle-configuration"

    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        self.snapshot_resource = None
        try:
            content = self.snapshot_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("vehicle configuration snapshot is not readable") from exc
        self._initialize_snapshot(self._parse_snapshot(content))

    def _initialize_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.snapshot_id = self._required_string(snapshot, "snapshot_id")
        self.source_revision = self._required_string(snapshot, "source_revision")
        self.generated_at = self._required_string(snapshot, "generated_at")
        self.provider_version = self.snapshot_id
        configurations = snapshot.get("configurations")
        if not isinstance(configurations, list):
            raise ValueError("vehicle configuration snapshot configurations must be a list")
        try:
            self.configurations = [
                VehicleConfigurationReference.model_validate(item)
                for item in configurations
            ]
        except ValidationError as exc:
            raise ValueError("vehicle configuration snapshot contains an invalid configuration") from exc

    @classmethod
    def from_package_resource(
        cls,
        *,
        package: str = "global_hybrid_v2",
        resource: str = "data/vehicle_configuration_current.json",
    ) -> FileVehicleConfigurationProvider:
        try:
            content = resources.files(package).joinpath(resource).read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError, OSError) as exc:
            raise RuntimeError("packaged vehicle configuration snapshot is unavailable") from exc
        provider = cls.__new__(cls)
        provider.snapshot_path = None
        provider.snapshot_resource = f"{package}:{resource}"
        provider._initialize_snapshot(provider._parse_snapshot(content))
        return provider

    @staticmethod
    def _parse_snapshot(content: str) -> dict[str, Any]:
        try:
            snapshot = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("vehicle configuration snapshot is not valid JSON") from exc
        if not isinstance(snapshot, dict):
            raise ValueError("vehicle configuration snapshot root must be an object")
        if snapshot.get("schema_version") != 1 or isinstance(
            snapshot.get("schema_version"), bool
        ):
            raise ValueError("unsupported vehicle configuration snapshot schema_version")
        return snapshot

    @staticmethod
    def _required_string(snapshot: dict[str, Any], field: str) -> str:
        value = snapshot.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"vehicle configuration snapshot {field} is required")
        return value

    def lookup(
        self,
        query: VehicleConfigurationQuery,
    ) -> VehicleConfigurationLookupResult:
        matches = [
            configuration
            for configuration in self.configurations
            if self._matches(configuration, query)
        ]
        state = VehicleConfigurationLookupState.MISS
        if matches:
            state = (
                VehicleConfigurationLookupState.HIT
                if all(item.conflict_state == "NO_CONFLICT" for item in matches)
                else VehicleConfigurationLookupState.CONFLICT
            )
        uncertainties = []
        if query.vehicle_instance_id is not None:
            uncertainties.append("VEHICLE_INSTANCE_NOT_RESOLVED_BY_REFERENCE_PROVIDER")
        provenance = [
            f"snapshot:{self.snapshot_id}",
            f"source-revision:{self.source_revision}",
        ]
        for configuration in matches:
            for pointer in configuration.primary_source_pointers:
                if pointer not in provenance:
                    provenance.append(pointer)
        return VehicleConfigurationLookupResult(
            state=state,
            query=query,
            configurations=matches,
            uncertainties=uncertainties,
            provenance=provenance,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
        )

    @staticmethod
    def _matches(
        configuration: VehicleConfigurationReference,
        query: VehicleConfigurationQuery,
    ) -> bool:
        if not (
            configuration.market.casefold() == query.market.casefold()
            and configuration.model_year == query.model_year
            and configuration.make.casefold() == query.make.casefold()
            and configuration.model.casefold() == query.model.casefold()
        ):
            return False
        if query.generation is not None and (
            configuration.generation is None
            or configuration.generation.casefold() != query.generation.casefold()
        ):
            return False
        return not (
            query.trim is not None
            and (
                configuration.trim is None
                or configuration.trim.casefold() != query.trim.casefold()
            )
        )


def configured_vehicle_configuration_provider(
    settings: Settings,
    *,
    repo_root: str | Path,
) -> FileVehicleConfigurationProvider:
    configured_path = settings.vehicle_configuration_snapshot_path
    if configured_path is None:
        return FileVehicleConfigurationProvider.from_package_resource()
    snapshot_path = Path(configured_path)
    if not snapshot_path.is_absolute():
        snapshot_path = Path(repo_root) / snapshot_path
    return FileVehicleConfigurationProvider(snapshot_path.resolve())
