from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.domains.vehicle_configuration import (
    VehicleConfigurationLookupResult,
    VehicleConfigurationLookupState,
)


class VehicleProviderReadback(BaseModel):
    provider_id: str = Field(min_length=1)
    provider_version: str = Field(min_length=1)
    snapshot_id: str | None = None
    source_revision: str | None = None
    generated_at: str | None = None
    active: bool
    readback_at: datetime


class VehicleProviderTransport(Protocol):
    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]: ...


class UrlLibVehicleProviderTransport:
    def __init__(self, *, base_url: str, read_secret: str, timeout: float = 10):
        self.base_url = base_url.rstrip("/")
        self.read_secret = read_secret
        self.timeout = timeout

    def get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={"authorization": f"Bearer {self.read_secret}", "accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.load(response)


class HttpVehicleConfigurationProvider:
    provider_id = "cloudflare-d1-http"

    def __init__(self, transport: VehicleProviderTransport):
        self.transport = transport
        self.provider_version = "unresolved"

    def lookup(self, query: VehicleConfigurationQuery) -> VehicleConfigurationLookupResult:
        try:
            payload = self.transport.get_json(
                "/v1/vehicle-config/query",
                {key: str(value) for key, value in query.model_dump(exclude_none=True).items()},
            )
            result = VehicleConfigurationLookupResult.model_validate(payload)
            if result.provider_id != self.provider_id:
                raise ValueError("vehicle provider identity mismatch")
            self.provider_version = result.provider_version
            return result
        except (OSError, TimeoutError, urllib.error.URLError, ValueError):
            return VehicleConfigurationLookupResult(
                state=VehicleConfigurationLookupState.PROVIDER_UNAVAILABLE,
                query=query,
                configurations=[],
                uncertainties=["CLOUDFLARE_D1_PROVIDER_UNAVAILABLE"],
                provenance=["provider:cloudflare-d1-http:unavailable"],
                provider_id=self.provider_id,
                provider_version=self.provider_version,
            )

    def readback(self) -> VehicleProviderReadback:
        try:
            payload = self.transport.get_json("/v1/vehicle-config/readback", {})
            result = VehicleProviderReadback.model_validate(payload)
            if result.provider_id != self.provider_id:
                raise ValueError("vehicle provider readback identity mismatch")
            self.provider_version = result.provider_version
            return result
        except (OSError, TimeoutError, urllib.error.URLError, ValueError):
            return VehicleProviderReadback(
                provider_id=self.provider_id,
                provider_version=self.provider_version,
                active=False,
                readback_at=datetime.now(UTC),
            )
