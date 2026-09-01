from __future__ import annotations

from global_hybrid_v2.contracts import DomainResult, Owner, TaskContract


class NotConfiguredDomain:
    def __init__(self, owner: Owner):
        self.owner = owner

    def run(self, contract: TaskContract) -> DomainResult:
        return DomainResult(
            owner=self.owner,
            status="BLOCKED_NOT_CONFIGURED",
            output=None,
            evidence={"reason": "domain adapter intentionally not configured in architecture scaffold"},
        )
