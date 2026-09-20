from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

from global_hybrid_v2.contracts import VehicleConfigurationQuery


class VehicleConfigurationLookupState(StrEnum):
    HIT = "HIT"
    PARTIAL = "PARTIAL"
    MISS = "MISS"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"


class VehicleEquipmentClassification(StrEnum):
    STANDARD = "STANDARD"
    OPTION = "OPTION"
    PACKAGE = "PACKAGE"
    DISCRIMINATOR = "DISCRIMINATOR"


class VehicleEquipmentReference(BaseModel):
    equipment_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    classification: VehicleEquipmentClassification
    trim_ids: list[str] = Field(default_factory=list)
    primary_source_pointer: str = Field(min_length=1)
    last_verified: str = Field(min_length=1)


class VehicleConfigurationReference(BaseModel):
    configuration_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    model_year: int = Field(ge=1886, le=3000)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    generation: str | None = None
    trim: str | None = None
    powertrain: dict = Field(default_factory=dict)
    equipment: list[VehicleEquipmentReference] = Field(default_factory=list)
    primary_source_pointers: list[str] = Field(default_factory=list)
    last_verified: str = Field(min_length=1)
    conflict_state: str = Field(min_length=1)
    query_key: str = Field(min_length=1)


class VehicleConfigurationLookupResult(BaseModel):
    state: VehicleConfigurationLookupState
    query: VehicleConfigurationQuery
    configurations: list[VehicleConfigurationReference] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)


class VehicleConfigurationProvider(Protocol):
    def lookup(self, query: VehicleConfigurationQuery) -> VehicleConfigurationLookupResult: ...


class UnavailableVehicleConfigurationProvider:
    def lookup(self, query: VehicleConfigurationQuery) -> VehicleConfigurationLookupResult:
        return VehicleConfigurationLookupResult(
            state=VehicleConfigurationLookupState.PROVIDER_UNAVAILABLE,
            query=query,
            uncertainties=["VEHICLE_CONFIGURATION_PROVIDER_TRANSPORT_UNAVAILABLE"],
            provenance=["vehicle-configuration-provider:unavailable"],
            provider_id="UNAVAILABLE_VEHICLE_CONFIGURATION_PROVIDER",
            provider_version="UNCONFIGURED",
        )
