"""Stateless admission of an exact Host-produced public-Copy oracle packet."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    ContextItem,
    ContextOrigin,
    PublicCopyLiteralAuthority,
    PublicCopyOracleInput,
    PublicCopySourceKind,
    TaskRequest,
)
from global_hybrid_v2.runtime.public_copy import digest, serialize

PUBLIC_COPY_ORACLE_INPUT_REQUIRED = "PUBLIC_COPY_ORACLE_INPUT_REQUIRED"
PUBLIC_COPY_ORACLE_INPUT_STALE = "PUBLIC_COPY_ORACLE_INPUT_STALE"
PUBLIC_COPY_ORACLE_INPUT_UNVERIFIED = "PUBLIC_COPY_ORACLE_INPUT_UNVERIFIED"
PUBLIC_COPY_ORACLE_TASK_SCOPE_MISMATCH = "PUBLIC_COPY_ORACLE_TASK_SCOPE_MISMATCH"
PUBLIC_COPY_ORACLE_FRAME_MISMATCH = "PUBLIC_COPY_ORACLE_FRAME_MISMATCH"
PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID = "PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID"
PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID = "PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID"
PUBLIC_COPY_ORACLE_AUTHORITY_MISMATCH = "PUBLIC_COPY_ORACLE_AUTHORITY_MISMATCH"


@dataclass(frozen=True)
class PublicCopyOracleVerification:
    verified: bool
    blocker: str | None = None


class PublicCopyOracleVerifier(Protocol):
    def verify(self, packet: PublicCopyOracleInput) -> PublicCopyOracleVerification: ...


class UnavailablePublicCopyOracleVerifier:
    def verify(self, packet: PublicCopyOracleInput) -> PublicCopyOracleVerification:
        del packet
        return PublicCopyOracleVerification(False, PUBLIC_COPY_ORACLE_INPUT_UNVERIFIED)


@dataclass(frozen=True)
class PublicCopyOracleAdmission:
    allowed: bool
    blocker: str | None = None
    packet: PublicCopyOracleInput | None = None
    oracle_input_digest: str | None = None
    admitted_source_refs: tuple[str, ...] = ()


class PublicCopyOracleGate:
    def __init__(
        self, *, now: Callable[[], datetime] | None = None,
        verifier: PublicCopyOracleVerifier | None = None,
    ):
        self._now = now or (lambda: datetime.now(UTC))
        self._verifier = verifier or UnavailablePublicCopyOracleVerifier()

    def admit(
        self, request: TaskRequest, *, authority: AuthoritySnapshot,
        admitted_context: list[ContextItem],
    ) -> PublicCopyOracleAdmission:
        if not request.public_commercial_copy:
            return PublicCopyOracleAdmission(True)
        packet = request.public_copy_oracle_input
        if packet is None:
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_INPUT_REQUIRED)
        if packet.valid_until < self._now():
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_INPUT_STALE)
        if packet.task_scope != request.request_text:
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_TASK_SCOPE_MISMATCH)
        try:
            terminal_candidate = json.loads(packet.terminal_candidate.canonical_json)
        except json.JSONDecodeError:
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID)
        if (
            serialize(terminal_candidate) != packet.terminal_candidate.canonical_json
            or digest(terminal_candidate) != packet.terminal_candidate.sha256
        ):
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID)
        if (
            request.public_copy_generation_id is None
            or request.public_copy_frame_id is None
            or packet.generation_id != request.public_copy_generation_id
            or packet.frame_id != request.public_copy_frame_id
        ):
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_FRAME_MISMATCH)

        requested = request.public_copy_requirement_ids
        packet_ids = [item.requirement_id for item in packet.hard_requirements]
        if (
            not requested or len(requested) != len(set(requested))
            or len(packet_ids) != len(set(packet_ids)) or set(requested) != set(packet_ids)
            or any(not item.body.strip() for item in packet.hard_requirements)
        ):
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_REQUIREMENTS_INVALID)

        revisions = {item.owner: item.revision for item in packet.authority_revisions}
        if len(revisions) != len(packet.authority_revisions) or any(
            owner not in authority.entries or authority.entries[owner].revision != revision
            for owner, revision in revisions.items()
        ):
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_AUTHORITY_MISMATCH)

        contexts = {item.id: item for item in admitted_context}
        context_ids = set(contexts)
        refs = {item.ref_id: item for item in packet.source_refs}
        if len(refs) != len(packet.source_refs):
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID)
        for source in refs.values():
            if source.kind is PublicCopySourceKind.CURRENT_CONTEXT:
                if (
                    source.context_id is None
                    or source.context_id not in context_ids
                    or source.authority_owner
                ):
                    return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID)
            elif (
                source.authority_owner is None or source.authority_owner not in revisions
                or source.context_id is not None
            ):
                return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID)
        consumed_refs = set(packet.primary_reason.source_refs)
        consumed_refs.update(ref for item in packet.literal_records for ref in item.source_refs)
        consumed_refs.update(ref for item in packet.supporting_proofs for ref in item.evidence_refs)
        if packet.qualification:
            consumed_refs.update(packet.qualification.evidence_refs)
        if not consumed_refs or not consumed_refs <= set(refs):
            return PublicCopyOracleAdmission(False, PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID)
        for literal in packet.literal_records:
            if literal.authority_classification is PublicCopyLiteralAuthority.CURRENT_USER_INPUT:
                literal_sources = [refs[ref] for ref in literal.source_refs]
                if any(
                    source.kind is not PublicCopySourceKind.CURRENT_CONTEXT
                    or contexts[source.context_id].origin is not ContextOrigin.CURRENT_USER
                    for source in literal_sources
                ):
                    return PublicCopyOracleAdmission(
                        False, PUBLIC_COPY_ORACLE_SOURCE_BINDING_INVALID
                    )

        verification = self._verifier.verify(packet)
        if not verification.verified:
            return PublicCopyOracleAdmission(
                False, verification.blocker or PUBLIC_COPY_ORACLE_INPUT_UNVERIFIED,
            )
        packet_copy = packet.model_copy(deep=True)
        return PublicCopyOracleAdmission(
            True, packet=packet_copy,
            oracle_input_digest=digest(packet_copy.model_dump(mode="json")),
            admitted_source_refs=tuple(sorted(refs)),
        )
