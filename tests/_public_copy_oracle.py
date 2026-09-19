from datetime import UTC, datetime, timedelta

from global_hybrid_v2.contracts import (
    Owner,
    PublicCopyAuthorityRevision,
    PublicCopyHardRequirement,
    PublicCopyLiteralAuthority,
    PublicCopyLiteralRecord,
    PublicCopyOracleInput,
    PublicCopyPrimaryReason,
    PublicCopyQualification,
    PublicCopyQualificationDisposition,
    PublicCopySourceKind,
    PublicCopySourceRef,
    PublicCopySupportingProof,
    PublicCopyTerminalCandidate,
)
from global_hybrid_v2.governance.public_copy_oracle import PublicCopyOracleVerification
from global_hybrid_v2.runtime.public_copy import digest, serialize


class TestPublicCopyOracleVerifier:
    __test__ = False

    def verify(self, packet):
        return PublicCopyOracleVerification(
            packet.producer_id == "synthetic-host-producer"
            and packet.currentness_token == "synthetic-current-token"
        )


def oracle_packet(
    *, revision: str, scope: str = "synthetic copy", generation_id: str = "generation-1",
    frame_id: str = "frame-1", requirement_id: str = "REQ-1",
    valid_until: datetime | None = None,
) -> PublicCopyOracleInput:
    now = datetime.now(UTC)
    expiry = valid_until or now + timedelta(minutes=5)
    issued_at = min(now - timedelta(seconds=1), expiry - timedelta(seconds=1))
    source_ref = "authority:sales"
    candidate = {"output": "synthetic candidate A", "final_response_object": None}
    return PublicCopyOracleInput(
        packet_id="oracle-packet-1",
        schema_version=1,
        task_scope=scope,
        generation_id=generation_id,
        frame_id=frame_id,
        terminal_candidate=PublicCopyTerminalCandidate(
            canonical_json=serialize(candidate), sha256=digest(candidate)
        ),
        hard_requirements=(
            PublicCopyHardRequirement(requirement_id=requirement_id, body="synthetic hard requirement"),
        ),
        literal_records=(
            PublicCopyLiteralRecord(
                record_id="literal-1", literal="calibration only",
                authority_classification=PublicCopyLiteralAuthority.NON_BINDING_CALIBRATION,
                source_refs=(source_ref,),
            ),
        ),
        primary_reason=PublicCopyPrimaryReason(
            reason_ref="primary-1", reason="synthetic reason to care", source_refs=(source_ref,),
        ),
        supporting_proofs=(
            PublicCopySupportingProof(
                proof_id="proof-1", claim="synthetic claim", proof_payload="synthetic proof payload",
                evidence_refs=(source_ref,),
            ),
        ),
        qualification=PublicCopyQualification(
            disposition=PublicCopyQualificationDisposition.PASS,
            qualification_ref="qualification-1", evidence_refs=(source_ref,),
        ),
        authority_revisions=(
            PublicCopyAuthorityRevision(owner=Owner.SALES_HUMAN, revision=revision),
        ),
        source_refs=(
            PublicCopySourceRef(
                ref_id=source_ref, kind=PublicCopySourceKind.CURRENT_AUTHORITY,
                authority_owner=Owner.SALES_HUMAN,
            ),
        ),
        producer_id="synthetic-host-producer",
        producer_version="synthetic-v1",
        currentness_token="synthetic-current-token",
        provenance=("synthetic:host-producer",),
        issued_at=issued_at,
        valid_until=expiry,
    )
