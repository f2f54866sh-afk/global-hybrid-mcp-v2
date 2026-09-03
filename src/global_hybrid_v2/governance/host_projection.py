"""Stateless admission of current Chat/Host identity and dialogue bindings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from global_hybrid_v2.contracts import CurrentIdentityProjection, EffectType, TaskRequest

HOST_STATE_PROJECTION_UNAVAILABLE = "HOST_STATE_PROJECTION_UNAVAILABLE"
HOST_STATE_PROJECTION_STALE = "HOST_STATE_PROJECTION_STALE"
HOST_STATE_MAPPING_MISMATCH = "HOST_STATE_MAPPING_MISMATCH"
CURRENT_IDENTITY_CURRENTNESS_UNPROVEN = "CURRENT_IDENTITY_CURRENTNESS_UNPROVEN"
DIALOGUE_REFERENT_AMBIGUOUS = "DIALOGUE_REFERENT_AMBIGUOUS"
WITNESS_READ_ONLY = "WITNESS_READ_ONLY"

_MUTATIONS = {EffectType.EXTERNAL_WRITE, EffectType.FILE_WRITE, EffectType.IMAGE_GENERATE}


@dataclass(frozen=True)
class HostProjectionAdmission:
    allowed: bool
    blocker: str | None = None
    mapping_version: str | None = None
    resolved_referent_id: str | None = None
    source_id: str | None = None
    source_version: str | None = None
    currentness_token: str | None = None


@dataclass(frozen=True)
class HostCurrentStateVerification:
    verified: bool
    blocker: str | None = None


class HostCurrentStateVerifier(Protocol):
    """Boundary to the real Host current-state source; it holds no state here."""

    def verify(self, projection: CurrentIdentityProjection) -> HostCurrentStateVerification: ...


class UnavailableHostCurrentStateVerifier:
    """Production default until a real Host current-state verifier is supplied."""

    def verify(self, projection: CurrentIdentityProjection) -> HostCurrentStateVerification:
        del projection
        return HostCurrentStateVerification(False, CURRENT_IDENTITY_CURRENTNESS_UNPROVEN)


class HostProjectionGate:
    """Validate a per-request Host projection without retaining Host state."""

    def __init__(
        self,
        *,
        now: Callable[[], datetime] | None = None,
        verifier: HostCurrentStateVerifier | None = None,
    ):
        self._now = now or (lambda: datetime.now(UTC))
        self._verifier = verifier or UnavailableHostCurrentStateVerifier()

    def admit(self, request: TaskRequest, *, required: bool) -> HostProjectionAdmission:
        identity = request.current_identity_projection
        dialogue = request.dialogue_binding_state
        if identity is None and dialogue is None:
            return (
                HostProjectionAdmission(False, HOST_STATE_PROJECTION_UNAVAILABLE)
                if required
                else HostProjectionAdmission(True)
            )
        if identity is None or dialogue is None:
            return HostProjectionAdmission(False, HOST_STATE_PROJECTION_UNAVAILABLE)

        now = self._now()
        if identity.valid_until < now or dialogue.valid_until < now:
            return HostProjectionAdmission(False, HOST_STATE_PROJECTION_STALE)
        if identity.mapping_version != dialogue.mapping_version:
            return HostProjectionAdmission(False, HOST_STATE_MAPPING_MISMATCH)
        if dialogue.requested_identity_alias not in identity.identities:
            return HostProjectionAdmission(False, HOST_STATE_MAPPING_MISMATCH)
        verification = self._verifier.verify(identity)
        if not verification.verified:
            return HostProjectionAdmission(
                False,
                verification.blocker or CURRENT_IDENTITY_CURRENTNESS_UNPROVEN,
            )
        if dialogue.material_ambiguity:
            return HostProjectionAdmission(False, DIALOGUE_REFERENT_AMBIGUOUS)
        if (
            dialogue.requested_identity_alias == "監察官"
            and _MUTATIONS.intersection(request.effects)
        ):
            return HostProjectionAdmission(False, WITNESS_READ_ONLY)
        return HostProjectionAdmission(
            True,
            mapping_version=identity.mapping_version,
            resolved_referent_id=dialogue.resolved_referent_id,
            source_id=identity.source_id,
            source_version=identity.source_version,
            currentness_token=identity.currentness_token,
        )
