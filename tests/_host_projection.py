from __future__ import annotations

from datetime import UTC, datetime, timedelta

from global_hybrid_v2.governance.host_projection import HostCurrentStateVerification


class TestHostCurrentStateVerifier:
    def verify(self, projection):
        return HostCurrentStateVerification(
            projection.source_id == "test-host-current-state"
            and projection.source_state == "CURRENT"
            and projection.currentness_token == "test-current-token"
        )


def host_projection_payload(*, alias: str = "管家", referent: str = "test-active-task") -> dict:
    now = datetime.now(UTC)
    return {
        "current_identity_projection": {
            "projection_id": "test-projection",
            "projection_version": "test-projection-v1",
            "source_id": "test-host-current-state",
            "source_version": "test-source-v1",
            "currentness_token": "test-current-token",
            "source_state": "CURRENT",
            "source_provenance": ["test:host-current-state"],
            "mapping_version": "test-map-v1",
            "identities": {alias: "test-target"},
            "issued_at": now.isoformat(),
            "valid_until": (now + timedelta(minutes=5)).isoformat(),
        },
        "dialogue_binding_state": {
            "mapping_version": "test-map-v1",
            "requested_identity_alias": alias,
            "resolved_referent_id": referent,
            "issued_at": now.isoformat(),
            "valid_until": (now + timedelta(minutes=5)).isoformat(),
        },
    }
