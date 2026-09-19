import pytest

from global_hybrid_v2.runtime.identity_ingress import TrustedIdentityIngress
from global_hybrid_v2.runtime.state import AuthenticatedPrincipal, SQLiteRuntimeStateStore


def test_rd014_stage1_server_owned_selection_round_trip_and_fail_closed(tmp_path):
    service = TrustedIdentityIngress(SQLiteRuntimeStateStore(tmp_path / "runtime.db"))
    principal = AuthenticatedPrincipal(subject="user-1", authentication_source="fake-test")
    issued = service.issue(
        principal=principal, conversation_or_thread_id="thread", runtime_task_id="task",
        master_asset_id="master", master_sha256="a" * 64,
        secondary_roles={"body": "BODY"}, excluded_generated_source_ids={"generated"},
        generative_only=True,
    )
    assert issued.record_id and issued.server_digest
    loaded = service.verify(record_id=issued.record_id, principal=principal,
                            conversation_or_thread_id="thread", runtime_task_id="task")
    assert loaded.master_asset_id == "master" and loaded.generative_only
    with pytest.raises(PermissionError):
        service.verify(
            record_id=issued.record_id,
            principal=AuthenticatedPrincipal(subject="other", authentication_source="fake-test"),
            conversation_or_thread_id="thread", runtime_task_id="task",
        )
    with pytest.raises(RuntimeError):
        service.verify(
            record_id="forged", principal=principal,
            conversation_or_thread_id="thread", runtime_task_id="task",
        )
