import hashlib
import json

import pytest
from pydantic import ValidationError

from global_hybrid_v2.runtime.identity_ingress import TrustedIdentityIngress
from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentitySecondaryRole,
    SQLiteRuntimeStateStore,
    identity_authority_selection_digest,
)


def _args(**updates):
    values = {
        "principal": AuthenticatedPrincipal(
            subject="user-1",
            authentication_source="fake-test",
        ),
        "conversation_or_thread_id": "thread-1",
        "runtime_task_id": "task-1",
        "person_binding": "person-1",
        "master_asset_id": "master-1",
        "master_sha256": "a" * 64,
        "secondary_roles": {
            "body-asset": IdentitySecondaryRole.BODY,
            "pose-asset": IdentitySecondaryRole.POSE,
        },
        "secondary_sha256": {
            "body-asset": "b" * 64,
            "pose-asset": "c" * 64,
        },
        "excluded_generated_source_ids": {"generated-1"},
        "generative_only": True,
    }
    values.update(updates)
    return values


def test_secondary_digest_round_trip_and_supersede(tmp_path):
    path = tmp_path / "runtime.db"
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(path))
    initial = service.issue(**_args())
    assert initial.secondary_sha256 == {
        "body-asset": "b" * 64,
        "pose-asset": "c" * 64,
    }

    replacement = service.supersede(
        prior_record_id=initial.record_id,
        **_args(
            secondary_roles={"tattoo-asset": IdentitySecondaryRole.TATTOO},
            secondary_sha256={"tattoo-asset": "d" * 64},
        ),
    )
    reopened = SQLiteRuntimeStateStore(path).load_identity_authority_selection(
        replacement.record_id
    )
    assert reopened.secondary_sha256 == {"tattoo-asset": "d" * 64}
    assert reopened.server_digest == identity_authority_selection_digest(reopened)


@pytest.mark.parametrize(
    "secondary_sha256",
    [
        {"body-asset": "b" * 64},
        {
            "body-asset": "b" * 64,
            "pose-asset": "c" * 64,
            "extra-asset": "d" * 64,
        },
    ],
)
def test_secondary_digest_keyset_must_exactly_match_roles(
    tmp_path,
    secondary_sha256,
):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    with pytest.raises(ValueError, match="exactly match"):
        service.issue(**_args(secondary_sha256=secondary_sha256))


@pytest.mark.parametrize("digest", ["B" * 64, "not-a-digest", "b" * 63])
def test_secondary_digest_requires_lowercase_sha256(tmp_path, digest):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    with pytest.raises(ValidationError):
        service.issue(
            **_args(
                secondary_sha256={
                    "body-asset": digest,
                    "pose-asset": "c" * 64,
                }
            )
        )


def test_secondary_digest_tamper_fails_verification(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    service = TrustedIdentityIngress(store)
    selection = service.issue(**_args())
    tampered = selection.model_dump(mode="json")
    tampered["secondary_sha256"]["body-asset"] = "e" * 64
    with store._connect() as connection:
        connection.execute(
            "UPDATE identity_authority_selection SET payload=? WHERE record_id=?",
            (json.dumps(tampered), selection.record_id),
        )

    with pytest.raises(PermissionError, match="verification failed"):
        service.verify(
            record_id=selection.record_id,
            principal=_args()["principal"],
            conversation_or_thread_id="thread-1",
            runtime_task_id="task-1",
        )


def test_pre_a2_row_without_secondary_digests_migrates_without_guessing(tmp_path):
    path = tmp_path / "runtime.db"
    store = SQLiteRuntimeStateStore(path)
    selection = TrustedIdentityIngress(store).issue(**_args())
    legacy = selection.model_dump(mode="json")
    legacy.pop("secondary_sha256")
    legacy_body = {key: value for key, value in legacy.items() if key != "server_digest"}
    legacy["server_digest"] = hashlib.sha256(
        json.dumps(legacy_body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with store._connect() as connection:
        connection.execute(
            "UPDATE identity_authority_selection SET payload=? WHERE record_id=?",
            (json.dumps(legacy), selection.record_id),
        )

    migrated = SQLiteRuntimeStateStore(path).load_identity_authority_selection(
        selection.record_id
    )
    assert migrated.secondary_roles == selection.secondary_roles
    assert migrated.secondary_sha256 == {}
    assert migrated.server_digest == identity_authority_selection_digest(migrated)
