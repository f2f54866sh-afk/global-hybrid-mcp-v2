from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

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

    @model_validator(mode="after")
    def reject_blank_strings(self) -> VehicleEquipmentReference:
        if not self.equipment_key.strip():
            raise ValueError("equipment_key cannot be blank")
        if not self.label.strip():
            raise ValueError("label cannot be blank")
        if not self.primary_source_pointer.strip():
            raise ValueError("primary_source_pointer cannot be blank")
        if not self.last_verified.strip():
            raise ValueError("last_verified cannot be blank")
        if any(not item.strip() for item in self.trim_ids):
            raise ValueError("trim_ids cannot contain blank values")
        return self


class VehicleConfigurationReference(BaseModel):
    configuration_id: str = Field(min_length=1)
    market: str = Field(min_length=1)
    model_year: int = Field(ge=1886, le=3000)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    generation: str | None = None
    trim: str | None = None
    powertrain: dict[str, Any] = Field(default_factory=dict)
    equipment: list[VehicleEquipmentReference] = Field(default_factory=list)
    primary_source_pointers: list[str] = Field(default_factory=list)
    last_verified: str = Field(min_length=1)
    conflict_state: str = Field(min_length=1)
    query_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_blank_strings(self) -> VehicleConfigurationReference:
        required_values = (
            self.configuration_id,
            self.market,
            self.make,
            self.model,
            self.last_verified,
            self.conflict_state,
            self.query_key,
        )
        if any(not value.strip() for value in required_values):
            raise ValueError(
                "vehicle configuration identity/source fields cannot be blank"
            )

        for value in (self.generation, self.trim):
            if value is not None and not value.strip():
                raise ValueError(
                    "optional vehicle configuration identifiers cannot be blank"
                )

        if any(not item.strip() for item in self.primary_source_pointers):
            raise ValueError(
                "primary_source_pointers cannot contain blank values"
            )

        return self


class VehicleConfigurationLookupResult(BaseModel):
    state: VehicleConfigurationLookupState
    query: VehicleConfigurationQuery
    configurations: list[VehicleConfigurationReference] = Field(
        default_factory=list
    )
    uncertainties: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def reject_blank_provider_metadata(
        self,
    ) -> VehicleConfigurationLookupResult:
        if not self.provider_id.strip():
            raise ValueError("provider_id cannot be blank")
        if not self.provider_version.strip():
            raise ValueError("provider_version cannot be blank")
        if any(not item.strip() for item in self.uncertainties):
            raise ValueError("uncertainties cannot contain blank values")
        if any(not item.strip() for item in self.provenance):
            raise ValueError("provenance cannot contain blank values")
        return self


@runtime_checkable
class VehicleConfigurationProvider(Protocol):
    def lookup(
        self,
        query: VehicleConfigurationQuery,
    ) -> VehicleConfigurationLookupResult: ...


class UnavailableVehicleConfigurationProvider:
    provider_id = "vehicle-configuration-provider-unavailable"
    provider_version = "1"

    def lookup(
        self,
        query: VehicleConfigurationQuery,
    ) -> VehicleConfigurationLookupResult:
        return VehicleConfigurationLookupResult(
            state=VehicleConfigurationLookupState.PROVIDER_UNAVAILABLE,
            query=query,
            configurations=[],
            uncertainties=[
                "VEHICLE_CONFIGURATION_PROVIDER_UNAVAILABLE"
            ],
            provenance=[
                f"provider:{self.provider_id}:{self.provider_version}"
            ],
            provider_id=self.provider_id,
            provider_version=self.provider_version,
        )
