import hashlib
import json

import pytest
from pydantic import ValidationError

from global_hybrid_v2.runtime.identity_ingress import TrustedIdentityIngress
from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentitySecondaryRole,
    SQLiteRuntimeStateStore,
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
            "tattoo-asset": IdentitySecondaryRole.TATTOO,
            "pose-asset": IdentitySecondaryRole.POSE,
        },
        "secondary_sha256": {
            "body-asset": "b" * 64,
            "tattoo-asset": "c" * 64,
            "pose-asset": "d" * 64,
        },
        "excluded_generated_source_ids": {"generated-1"},
        "generative_only": True,
    }
    values.update(updates)
    return values


def test_new_selection_schema_round_trips_and_supersedes_person_binding(tmp_path):
    path = tmp_path / "runtime.db"
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(path))
    initial = service.issue(**_args())
    assert initial.person_binding == "person-1"
    assert initial.secondary_roles == {
        "body-asset": IdentitySecondaryRole.BODY,
        "tattoo-asset": IdentitySecondaryRole.TATTOO,
        "pose-asset": IdentitySecondaryRole.POSE,
    }

    replacement = service.supersede(
        prior_record_id=initial.record_id,
        **_args(person_binding="person-2", master_asset_id="master-2"),
    )
    assert replacement.person_binding == "person-2"
    reopened = SQLiteRuntimeStateStore(path).load_identity_authority_selection(
        replacement.record_id
    )
    assert reopened.person_binding == "person-2"
    assert reopened.secondary_roles == replacement.secondary_roles
    assert service.verify(
        record_id=replacement.record_id,
        principal=_args()["principal"],
        conversation_or_thread_id="thread-1",
        runtime_task_id="task-1",
    ) == replacement


def test_new_issue_requires_nonblank_person_binding(tmp_path):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    missing = _args()
    del missing["person_binding"]
    with pytest.raises(TypeError):
        service.issue(**missing)
    with pytest.raises(ValidationError, match="person_binding must not be blank"):
        service.issue(**_args(person_binding="   "))


def test_pre_stage1ca_row_without_person_binding_migrates_to_none(tmp_path):
    path = tmp_path / "runtime.db"
    store = SQLiteRuntimeStateStore(path)
    selection = TrustedIdentityIngress(store).issue(**_args())
    legacy = selection.model_dump(mode="json")
    legacy.pop("person_binding")
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
    assert migrated.person_binding is None


@pytest.mark.parametrize(
    "secondary_roles",
    [
        {"BODY": "asset-1"},
        {"asset-1": "UNSUPPORTED"},
        {"   ": "BODY"},
    ],
)
def test_secondary_role_schema_rejects_reversed_unsupported_and_blank_assets(
    tmp_path,
    secondary_roles,
):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    with pytest.raises(ValidationError):
        service.issue(
            **_args(
                secondary_roles=secondary_roles,
                secondary_sha256={asset_id: "e" * 64 for asset_id in secondary_roles},
            )
        )


def test_secondary_roles_reject_master_and_excluded_sources(tmp_path):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    with pytest.raises(ValidationError, match="master asset"):
        service.issue(
            **_args(
                secondary_roles={"master-1": "BODY"},
                secondary_sha256={"master-1": "e" * 64},
            )
        )
    with pytest.raises(ValidationError, match="excluded generated source"):
        service.issue(
            **_args(
                secondary_roles={"generated-1": "POSE"},
                secondary_sha256={"generated-1": "e" * 64},
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("person_binding", "tampered-person"),
        (
            "secondary_roles",
            {
                "body-asset": "POSE",
                "tattoo-asset": "TATTOO",
                "pose-asset": "POSE",
            },
        ),
    ],
)
def test_tampered_packet_schema_fields_fail_digest_verification(tmp_path, field, value):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    service = TrustedIdentityIngress(store)
    selection = service.issue(**_args())
    tampered = selection.model_dump(mode="json")
    tampered[field] = value
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
