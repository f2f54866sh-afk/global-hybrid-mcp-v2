from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.contracts import LibraryAccessKind, LibraryAccessRequest, Owner


class LibraryBoundaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class LibraryAccessDecision:
    access_kind: LibraryAccessKind
    allowed: bool
    mutation_allowed: bool
    reason: str


class LibraryReadWriteBoundary:
    """Keep fact mutation with LIBRARY_FACT while admitting bounded projections/signals."""

    def authorize(self, request: LibraryAccessRequest) -> LibraryAccessDecision:
        if request.access_kind is LibraryAccessKind.COMMIT_FACT:
            if request.actor_owner is not Owner.LIBRARY_FACT:
                raise LibraryBoundaryError("only LIBRARY_FACT may commit current fact values")
            return LibraryAccessDecision(
                access_kind=request.access_kind,
                allowed=True,
                mutation_allowed=True,
                reason="LIBRARY_FACT_WRITE_AUTHORITY",
            )

        if request.access_kind is LibraryAccessKind.READ_PROJECTION:
            if not request.projection or not request.projection.strip():
                raise LibraryBoundaryError("Library read requires a named consumer projection")
            return LibraryAccessDecision(
                access_kind=request.access_kind,
                allowed=True,
                mutation_allowed=False,
                reason="CONSUMER_PROJECTION_ONLY",
            )

        return LibraryAccessDecision(
            access_kind=request.access_kind,
            allowed=True,
            mutation_allowed=False,
            reason="FACT_NEED_SIGNAL_ONLY",
        )
