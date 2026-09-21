import json
from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.runtime.dispatcher import TrustedDispatchContext
from global_hybrid_v2.runtime.identity_ingress import TrustedIdentityIngress
from global_hybrid_v2.runtime.state import (
    AuthenticatedPrincipal,
    IdentitySecondaryRole,
    SQLiteRuntimeStateStore,
    identity_authority_selection_digest,
)
from tests.test_rd014_stage1a_trusted_context import _capability_context
from tests.test_rd_20260913_009_image_binding import (
    _dispatcher,
    _image_spec,
    _RecordingPort,
    _request,
)

PRINCIPAL = AuthenticatedPrincipal(
    subject="user-1",
    authentication_source="fake-test",
)
TRUSTED_CONTEXT = TrustedDispatchContext("user-1", "fake-test")


def _selection_args(**updates):
    values = {
        "principal": PRINCIPAL,
        "conversation_or_thread_id": "thread-a",
        "runtime_task_id": "task-a",
        "person_binding": "person-1",
        "master_asset_id": "master-real",
        "master_sha256": "a" * 64,
        "secondary_roles": {
            "body-real": IdentitySecondaryRole.BODY,
            "tattoo-real": IdentitySecondaryRole.TATTOO,
            "pose-real": IdentitySecondaryRole.POSE,
        },
        "secondary_sha256": {
            "body-real": "b" * 64,
            "tattoo-real": "c" * 64,
            "pose-real": "d" * 64,
        },
        "excluded_generated_source_ids": {"generated-old"},
        "generative_only": True,
    }
    values.update(updates)
    return values


def _trusted_request(record_id, **updates):
    spec = _image_spec(None).model_copy(
        update={"identity_trusted_ingress_required": True}
    )
    request = _request(spec, context=[_capability_context()]).model_copy(
        update={
            "conversation_or_thread_id": "thread-a",
            "runtime_task_id": "task-a",
            "identity_selection_record_id": record_id,
        }
    )
    return request.model_copy(update=updates)


def _issue(tmp_path):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    selection = TrustedIdentityIngress(store).issue(**_selection_args())
    return store, selection


def _dispatch(request, port, store, context=TRUSTED_CONTEXT):
    return _dispatcher(port, store).dispatch(request, trusted_context=context)


def test_current_selection_rehydrates_server_packet_and_stops_before_port(tmp_path):
    store, selection = _issue(tmp_path)
    port = _RecordingPort()
    result = _dispatch(_trusted_request(selection.record_id), port, store)

    assert result.status == "IDENTITY_REFERENCE_TRANSPORT_REQUIRED"
    assert result.output == {"state": "IDENTITY_REFERENCE_TRANSPORT_REQUIRED"}
    packet = result.evidence["identity_source_packet"]
    assert packet["task_binding"] == "task-a"
    assert packet["person_binding"] == "person-1"
    assert packet["generative_only"] is True
    assert packet["excluded_generated_source_ids"] == ["generated-old"]
    assert packet["version"] == (
        f"identity-selection:{selection.record_id}:"
        f"revision:1:{selection.server_digest}"
    )
    assert packet["sources"] == [
        {
            "asset_id": "master-real",
            "sha256": "a" * 64,
            "role": "ORIGINAL_REAL_MASTER",
            "generated": False,
        },
        {
            "asset_id": "body-real",
            "sha256": "b" * 64,
            "role": "BODY",
            "generated": False,
        },
        {
            "asset_id": "pose-real",
            "sha256": "d" * 64,
            "role": "POSE",
            "generated": False,
        },
        {
            "asset_id": "tattoo-real",
            "sha256": "c" * 64,
            "role": "TATTOO",
            "generated": False,
        },
    ]
    assert result.evidence["request_input_bound"] is False
    assert port.calls == 0


def test_missing_selection_reference_and_trusted_context_block_before_port(tmp_path):
    store, selection = _issue(tmp_path)
    port = _RecordingPort()
    missing_reference = _trusted_request(selection.record_id).model_copy(
        update={"identity_selection_record_id": None}
    )
    assert _dispatch(missing_reference, port, store).status == (
        "IDENTITY_SELECTION_REFERENCE_REQUIRED"
    )
    assert _dispatch(
        _trusted_request(selection.record_id), port, store, context=None
    ).status == "IDENTITY_TRUSTED_CONTEXT_REQUIRED"
    assert port.calls == 0


@pytest.mark.parametrize(
    ("request_updates", "context"),
    [
        ({"identity_selection_record_id": "forged"}, TRUSTED_CONTEXT),
        ({}, TrustedDispatchContext("wrong-user", "fake-test")),
        ({"conversation_or_thread_id": "wrong-thread"}, TRUSTED_CONTEXT),
        ({"runtime_task_id": "wrong-task"}, TRUSTED_CONTEXT),
    ],
)
def test_selection_verification_rejects_forged_or_wrong_bindings(
    tmp_path,
    request_updates,
    context,
):
    store, selection = _issue(tmp_path)
    port = _RecordingPort()
    result = _dispatch(
        _trusted_request(selection.record_id, **request_updates),
        port,
        store,
        context,
    )
    assert result.status == "IDENTITY_SELECTION_VERIFICATION_BLOCKED"
    assert port.calls == 0


@pytest.mark.parametrize("missing_field", ["store", "thread", "task"])
def test_selection_path_requires_store_thread_and_task(tmp_path, missing_field):
    store, selection = _issue(tmp_path)
    port = _RecordingPort()
    request = _trusted_request(selection.record_id)
    dispatch_store = store
    if missing_field == "store":
        dispatch_store = None
    elif missing_field == "thread":
        request = request.model_copy(update={"conversation_or_thread_id": None})
    else:
        request = request.model_copy(update={"runtime_task_id": None})
    result = _dispatch(request, port, dispatch_store)
    assert result.status == "IDENTITY_SELECTION_RUNTIME_BINDING_REQUIRED"
    assert port.calls == 0


def test_expired_revoked_and_superseded_selections_block(tmp_path):
    for state in ("expired", "revoked", "superseded"):
        store = SQLiteRuntimeStateStore(tmp_path / f"{state}.db")
        service = TrustedIdentityIngress(store)
        selection = service.issue(**_selection_args())
        if state == "expired":
            expired = selection.model_copy(
                update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
            )
            expired = expired.model_copy(
                update={"server_digest": identity_authority_selection_digest(expired)}
            )
            with store._connect() as connection:
                connection.execute(
                    """UPDATE identity_authority_selection
                    SET payload=?, expires_at=? WHERE record_id=?""",
                    (
                        json.dumps(expired.model_dump(mode="json")),
                        expired.expires_at.isoformat(),
                        selection.record_id,
                    ),
                )
        elif state == "revoked":
            service.revoke(
                record_id=selection.record_id,
                principal=PRINCIPAL,
                conversation_or_thread_id="thread-a",
                runtime_task_id="task-a",
            )
        else:
            service.supersede(
                prior_record_id=selection.record_id,
                **_selection_args(master_asset_id="master-new"),
            )
        port = _RecordingPort()
        result = _dispatch(_trusted_request(selection.record_id), port, store)
        assert result.status == "IDENTITY_SELECTION_VERIFICATION_BLOCKED"
        assert port.calls == 0


@pytest.mark.parametrize("incomplete_field", ["person_binding", "secondary_sha256"])
def test_legacy_or_incomplete_selection_cannot_rehydrate(tmp_path, incomplete_field):
    store, selection = _issue(tmp_path)
    incomplete = selection.model_copy(
        update={
            incomplete_field: None if incomplete_field == "person_binding" else {}
        }
    )
    incomplete = incomplete.model_copy(
        update={"server_digest": identity_authority_selection_digest(incomplete)}
    )
    with store._connect() as connection:
        connection.execute(
            "UPDATE identity_authority_selection SET payload=? WHERE record_id=?",
            (json.dumps(incomplete.model_dump(mode="json")), selection.record_id),
        )
    port = _RecordingPort()
    result = _dispatch(_trusted_request(selection.record_id), port, store)
    assert result.status == "IDENTITY_SELECTION_REHYDRATION_BLOCKED"
    assert port.calls == 0


@pytest.mark.parametrize(
    "direct_fields",
    [
        {"identity_source_packet": {"master": "caller-master"}},
        {"controlled_request_input_lineage": {"principal": "caller-person"}},
        {
            "identity_source_packet": {
                "master": "different-master",
                "person_binding": "different-person",
                "generative_only": False,
            }
        },
    ],
)
def test_direct_authoritative_payload_bypass_is_blocked(tmp_path, direct_fields):
    store, selection = _issue(tmp_path)
    request = _trusted_request(selection.record_id)
    request.image_task.update(direct_fields)
    port = _RecordingPort()
    result = _dispatch(request, port, store)
    assert result.status == "IDENTITY_DIRECT_AUTHORITY_BYPASS_BLOCKED"
    assert port.calls == 0
