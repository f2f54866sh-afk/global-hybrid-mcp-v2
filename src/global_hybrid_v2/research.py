from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from global_hybrid_v2.contracts import (
    ResearchExecutionReceipt,
    ResearchProviderAvailability,
    ResearchRequest,
)


class ResearchPort(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def availability(self) -> ResearchProviderAvailability: ...

    def execute(self, request: ResearchRequest) -> ResearchExecutionReceipt: ...


class UnavailableResearchPort:
    provider = "UNAVAILABLE"
    availability = ResearchProviderAvailability.UNAVAILABLE

    def __init__(self, blocker: str = "no production research provider is configured"):
        self.blocker = blocker

    def execute(self, request: ResearchRequest) -> ResearchExecutionReceipt:
        del request
        raise RuntimeError(self.blocker)


@dataclass(frozen=True)
class ResearchExecutor:
    port: ResearchPort

    @property
    def provider(self) -> str:
        return self.port.provider

    @property
    def availability(self) -> ResearchProviderAvailability:
        return self.port.availability

    def execute(self, request: ResearchRequest) -> ResearchExecutionReceipt:
        return self.port.execute(request)
