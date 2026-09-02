from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    ContextItem,
    ContextOrigin,
    Owner,
)
from global_hybrid_v2.governance.firewall import TaskFirewall


def _snapshot():
    return AuthoritySnapshot(
        entries={
            owner: AuthorityEntry(
                owner=owner,
                live_authority=AuthorityDocument(
                    name=owner.value,
                    role=AuthorityDocumentRole.LIVE_AUTHORITY,
                    revision=f"{owner.value}-1",
                    path=f"{owner.value}.md",
                ),
            )
            for owner in Owner
        }
    )


def test_history_is_quarantined():
    items = [
        ContextItem(
            id="old",
            origin=ContextOrigin.HISTORY,
            purpose="old case",
            task_scope="x",
            payload="legacy",
        ),
        ContextItem(
            id="now",
            origin=ContextOrigin.CURRENT_USER,
            purpose="current request",
            task_scope="x",
            payload="current",
        ),
    ]
    result = TaskFirewall().filter(items, _snapshot())
    assert [x.id for x in result] == ["now"]


def test_wrong_authority_revision_is_quarantined():
    item = ContextItem(
        id="bad",
        origin=ContextOrigin.CURRENT_AUTHORITY,
        purpose="authority",
        task_scope="x",
        payload="...",
        authority_owner=Owner.GLOBAL,
        authority_revision="OLD",
    )
    assert TaskFirewall().filter([item], _snapshot()) == []
