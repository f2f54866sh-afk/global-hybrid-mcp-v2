import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.runtime.identity_ingress import TrustedIdentityIngress
from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentityAuthoritySelection,
    IdentitySelectionLifecycle,
    RuntimeStateAlreadyExists,
    RuntimeStateError,
    SQLiteRuntimeStateStore,
    identity_authority_selection_digest,
)


def _principal(subject="user-1"):
    return AuthenticatedPrincipal(subject=subject, authentication_source="fake-test")


def _selection_args(**updates):
    values = {
        "principal": _principal(),
        "conversation_or_thread_id": "thread-1",
        "runtime_task_id": "task-1",
        "master_asset_id": "master-1",
        "master_sha256": "a" * 64,
        "secondary_roles": {"BODY": "body-1", "POSE": "pose-1"},
        "excluded_generated_source_ids": {"generated-1"},
        "generative_only": True,
    }
    values.update(updates)
    return values


def _verify(service, record_id, **updates):
    values = {
        "record_id": record_id,
        "principal": _principal(),
        "conversation_or_thread_id": "thread-1",
        "runtime_task_id": "task-1",
    }
    values.update(updates)
    return service.verify(**values)


def test_initial_issue_verify_supersede_revoke_and_reopen(tmp_path):
    path = tmp_path / "runtime.db"
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(path))
    initial = service.issue(**_selection_args())
    assert initial.revision == 1
    assert initial.lifecycle is IdentitySelectionLifecycle.ACTIVE
    assert _verify(service, initial.record_id) == initial

    replacement = service.supersede(
        prior_record_id=initial.record_id,
        **_selection_args(master_asset_id="master-2", master_sha256="b" * 64),
    )
    assert replacement.revision == 2
    assert replacement.lifecycle is IdentitySelectionLifecycle.ACTIVE
    assert _verify(service, replacement.record_id) == replacement
    with pytest.raises((PermissionError, RuntimeStateError)):
        _verify(service, initial.record_id)

    reopened_store = SQLiteRuntimeStateStore(path)
    assert (
        reopened_store.load_identity_authority_selection(initial.record_id).lifecycle
        is IdentitySelectionLifecycle.SUPERSEDED
    )
    reopened_service = TrustedIdentityIngress(reopened_store)
    revoked = reopened_service.revoke(
        record_id=replacement.record_id,
        principal=_principal(),
        conversation_or_thread_id="thread-1",
        runtime_task_id="task-1",
    )
    assert revoked.lifecycle is IdentitySelectionLifecycle.REVOKED
    with pytest.raises((PermissionError, RuntimeStateError)):
        _verify(reopened_service, replacement.record_id)


def test_duplicate_active_and_conflicting_concurrent_issue_fail_closed(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    service = TrustedIdentityIngress(store)
    service.issue(**_selection_args())
    with pytest.raises(RuntimeStateAlreadyExists, match="ACTIVE_ALREADY_EXISTS"):
        service.issue(**_selection_args(master_asset_id="duplicate"))

    other_store = SQLiteRuntimeStateStore(tmp_path / "concurrent.db")

    def issue(master):
        return TrustedIdentityIngress(other_store).issue(
            **_selection_args(master_asset_id=master)
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [future.exception() for future in [pool.submit(issue, "a"), pool.submit(issue, "b")]]
    assert sum(item is None for item in outcomes) == 1
    assert sum(isinstance(item, RuntimeStateAlreadyExists) for item in outcomes) == 1
    with other_store._connect() as connection:
        active_count = connection.execute(
            "SELECT COUNT(*) FROM identity_authority_selection WHERE lifecycle='ACTIVE'"
        ).fetchone()[0]
    assert active_count == 1


@pytest.mark.parametrize(
    "bindings",
    [
        {"principal": _principal("other")},
        {"conversation_or_thread_id": "wrong-thread"},
        {"runtime_task_id": "wrong-task"},
    ],
)
def test_verify_rejects_wrong_binding(tmp_path, bindings):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    selection = service.issue(**_selection_args())
    with pytest.raises((PermissionError, RuntimeStateError)):
        _verify(service, selection.record_id, **bindings)


def test_expired_and_digest_tampered_selection_fail_verification(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    service = TrustedIdentityIngress(store)
    expired = service.issue(**_selection_args())
    expired_value = expired.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    expired_value = expired_value.model_copy(
        update={"server_digest": identity_authority_selection_digest(expired_value)}
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE identity_authority_selection SET payload=?, expires_at=? WHERE record_id=?",
            (
                json.dumps(expired_value.model_dump(mode="json")),
                expired_value.expires_at.isoformat(),
                expired.record_id,
            ),
        )
    with pytest.raises((PermissionError, RuntimeStateError)):
        _verify(service, expired.record_id)
    with pytest.raises(RuntimeStateError, match="EXPIRED"):
        service.supersede(
            prior_record_id=expired.record_id,
            **_selection_args(master_asset_id="not-allowed"),
        )

    fresh = service.issue(**_selection_args(master_asset_id="fresh"))
    tampered = fresh.model_copy(update={"master_asset_id": "forged"})
    with store._connect() as connection:
        connection.execute(
            "UPDATE identity_authority_selection SET payload=? WHERE record_id=?",
            (json.dumps(tampered.model_dump(mode="json")), fresh.record_id),
        )
    with pytest.raises(PermissionError):
        _verify(service, fresh.record_id)
    with pytest.raises(RuntimeStateError, match="DIGEST_MISMATCH"):
        service.supersede(
            prior_record_id=fresh.record_id,
            **_selection_args(master_asset_id="cannot-launder-tamper"),
        )


def test_stale_supersede_and_revoke_fail_closed(tmp_path):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    initial = service.issue(**_selection_args())
    replacement = service.supersede(
        prior_record_id=initial.record_id,
        **_selection_args(master_asset_id="replacement"),
    )
    with pytest.raises(RuntimeStateError, match="NOT_ACTIVE"):
        service.supersede(prior_record_id=initial.record_id, **_selection_args())
    with pytest.raises(RuntimeStateError, match="NOT_ACTIVE"):
        service.revoke(
            record_id=initial.record_id,
            principal=_principal(),
            conversation_or_thread_id="thread-1",
            runtime_task_id="task-1",
        )
    service.revoke(
        record_id=replacement.record_id,
        principal=_principal(),
        conversation_or_thread_id="thread-1",
        runtime_task_id="task-1",
    )
    with pytest.raises(RuntimeStateError, match="NOT_ACTIVE"):
        service.supersede(
            prior_record_id=replacement.record_id,
            **_selection_args(master_asset_id="revoked-replacement"),
        )
    with pytest.raises(RuntimeStateError, match="NOT_ACTIVE"):
        service.revoke(
            record_id=replacement.record_id,
            principal=_principal(),
            conversation_or_thread_id="thread-1",
            runtime_task_id="task-1",
        )


@pytest.mark.parametrize("field", ["revision", "current", "server_digest", "record_id"])
def test_issue_rejects_caller_controlled_lifecycle_metadata(tmp_path, field):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    with pytest.raises(TypeError):
        service.issue(**_selection_args(**{field: "caller-value"}))


def test_selection_model_rejects_legacy_currentness_injection():
    base = {
        "record_id": "record",
        "principal_subject": "user",
        "conversation_or_thread_id": "thread",
        "runtime_task_id": "task",
        "master_asset_id": "master",
        "master_sha256": "a" * 64,
        "revision": 1,
        "issued_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(minutes=1),
        "server_nonce": "nonce",
        "server_digest": "b" * 64,
        "current": True,
    }
    with pytest.raises(ValueError):
        IdentityAuthoritySelection.model_validate(base)
