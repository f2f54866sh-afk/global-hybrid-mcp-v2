from __future__ import annotations

from typing import Protocol, runtime_checkable

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    DomainContract,
    DomainResult,
    LibraryAccessRequest,
    TaskContract,
)


class DomainPort(Protocol):
    def run(self, contract: TaskContract) -> DomainResult: ...


@runtime_checkable
class LibraryProjectionPort(DomainPort, Protocol):
    def project(
        self,
        request: LibraryAccessRequest,
        *,
        task: TaskContract,
        authority: AuthoritySnapshot,
    ) -> DomainContract: ...
