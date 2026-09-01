from __future__ import annotations

from typing import Protocol

from global_hybrid_v2.contracts import DomainResult, TaskContract


class DomainPort(Protocol):
    def run(self, contract: TaskContract) -> DomainResult: ...
