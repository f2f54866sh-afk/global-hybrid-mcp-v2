import json
from pathlib import Path

import pytest

from global_hybrid_v2.contracts import AuthorityDocumentRole, Owner
from global_hybrid_v2.governance.authority import (
    AuthorityError,
    AuthorityResolver,
)

DOCUMENTS = {
    "GLOBAL": ("LIVE_AUTHORITY", "## Current Authority"),
    "SALES": ("LIVE_AUTHORITY", "## Current Authority"),
    "SALES_HUMAN": ("REFERENCE_ONLY", "## Reference Content"),
    "LIBRARY_FACT": ("LIVE_AUTHORITY", "## Current Authority"),
    "VISUAL": ("LIVE_AUTHORITY", "## Current Authority"),
    "EXECUTION": ("LIVE_AUTHORITY", "## Current Authority"),
    "REAL_CAR": ("CANONICAL", "## Canonical Content"),
}

BINDINGS = {
    "GLOBAL": {"live_authority": "GLOBAL", "references": [], "canonicals": []},
    "SALES_HUMAN": {
        "live_authority": "SALES",
        "references": ["SALES_HUMAN"],
        "canonicals": [],
    },
    "LIBRARY_FACT": {"live_authority": "LIBRARY_FACT", "references": [], "canonicals": []},
    "VISUAL": {"live_authority": "VISUAL", "references": [], "canonicals": ["REAL_CAR"]},
    "EXECUTION": {"live_authority": "EXECUTION", "references": [], "canonicals": ["REAL_CAR"]},
}


def _authority_tree(tmp_path: Path, *, revision: str = "rev-1") -> tuple[Path, dict]:
    current = tmp_path / "authority" / "current"
    current.mkdir(parents=True)
    documents = {}
    for name, (role, section) in DOCUMENTS.items():
        path = current / f"{name}.md"
        path.write_text(
            f"# {name}\n\n"
            f"ROLE: {role}\n"
            f"STATUS: CURRENT\n"
            f"REVISION: {revision}\n\n"
            f"{section}\n\n"
            f"test fixture content for {name}\n",
            encoding="utf-8",
        )
        documents[name] = {
            "role": role,
            "revision": revision,
            "path": f"authority/current/{name}.md",
        }

    registry = current / "registry.json"
    payload = {
        "schema_version": 2,
        "documents": documents,
        "entries": json.loads(json.dumps(BINDINGS)),
    }
    registry.write_text(json.dumps(payload), encoding="utf-8")
    return registry, payload


@pytest.mark.parametrize("document_name", DOCUMENTS)
def test_unset_document_revision_fails_closed(tmp_path, document_name):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"][document_name]["revision"] = "UNSET"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=f"document revision unset: {document_name}"):
        AuthorityResolver(registry).resolve()


def test_valid_bindings_keep_owner_and_document_roles_separate(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = AuthorityResolver(registry).resolve()

    assert set(snapshot.entries) == set(Owner)
    assert "SALES" not in {owner.value for owner in Owner}
    assert "REAL_CAR" not in {owner.value for owner in Owner}

    sales = snapshot.entries[Owner.SALES_HUMAN]
    assert sales.live_authority.name == "SALES"
    assert sales.live_authority.role is AuthorityDocumentRole.LIVE_AUTHORITY
    assert [item.name for item in sales.references] == ["SALES_HUMAN"]
    assert sales.references[0].role is AuthorityDocumentRole.REFERENCE_ONLY

    visual = snapshot.entries[Owner.VISUAL]
    execution = snapshot.entries[Owner.EXECUTION]
    assert visual.live_authority.name == "VISUAL"
    assert execution.live_authority.name == "EXECUTION"
    assert visual.live_authority != execution.live_authority
    assert [item.name for item in visual.canonicals] == ["REAL_CAR"]
    assert visual.canonicals == execution.canonicals
    assert visual.canonicals[0].role is AuthorityDocumentRole.CANONICAL


def test_missing_authority_document_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    (tmp_path / "authority" / "current" / "REAL_CAR.md").unlink()

    with pytest.raises(AuthorityError, match="document unreadable: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_document_revision_must_match_registry(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    path = tmp_path / "authority" / "current" / "EXECUTION.md"
    path.write_text(path.read_text(encoding="utf-8").replace("REVISION: rev-1", "REVISION: rev-2"))

    with pytest.raises(AuthorityError, match="document revision mismatch: EXECUTION"):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("ROLE: LIVE_AUTHORITY", "ROLE: REFERENCE_ONLY", "file role mismatch"),
        ("STATUS: CURRENT", "STATUS: UNSET", "status is not CURRENT"),
        ("REVISION: rev-1", "REVISION: UNSET", "file revision unset"),
        ("test fixture content for GLOBAL", "UNSET", "content unset"),
        ("# GLOBAL", "# VISUAL", "name mismatch"),
    ],
)
def test_authority_document_metadata_fails_closed(tmp_path, old, new, message):
    registry, _ = _authority_tree(tmp_path)
    path = tmp_path / "authority" / "current" / "GLOBAL.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    with pytest.raises(AuthorityError, match=message):
        AuthorityResolver(registry).resolve()


def test_document_path_must_map_to_named_file(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["GLOBAL"]["path"] = "authority/current/VISUAL.md"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document path mismatch: GLOBAL"):
        AuthorityResolver(registry).resolve()


def test_registry_rejects_duplicate_document(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    registry.write_text(
        '{"schema_version": 2, "documents": {"GLOBAL": {}, "GLOBAL": {}}, "entries": {}}',
        encoding="utf-8",
    )

    with pytest.raises(AuthorityError, match="duplicate registry key: GLOBAL"):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version=3), "unsupported authority registry schema"),
        (lambda payload: payload["documents"].pop("SALES"), "missing authority documents: SALES"),
        (
            lambda payload: payload["documents"].update(
                UNKNOWN={
                    "role": "LIVE_AUTHORITY",
                    "revision": "rev-1",
                    "path": "authority/current/UNKNOWN.md",
                }
            ),
            "unexpected authority documents: UNKNOWN",
        ),
        (lambda payload: payload["entries"].pop("GLOBAL"), "missing current authority entries: GLOBAL"),
        (
            lambda payload: payload["entries"].update(
                SALES={"live_authority": "SALES", "references": [], "canonicals": []}
            ),
            "unexpected current authority entries: SALES",
        ),
    ],
)
def test_registry_schema_document_and_owner_sets_fail_closed(tmp_path, mutation, message):
    registry, payload = _authority_tree(tmp_path)
    mutation(payload)
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=message):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize(
    ("owner", "field", "value", "message"),
    [
        ("SALES_HUMAN", "live_authority", "SALES_HUMAN", "live authority binding mismatch"),
        ("SALES_HUMAN", "references", [], "reference binding mismatch"),
        ("VISUAL", "live_authority", "EXECUTION", "live authority binding mismatch"),
        ("VISUAL", "canonicals", [], "canonical binding mismatch"),
        ("EXECUTION", "canonicals", [], "canonical binding mismatch"),
    ],
)
def test_partition_bindings_fail_closed(tmp_path, owner, field, value, message):
    registry, payload = _authority_tree(tmp_path)
    payload["entries"][owner][field] = value
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=f"{message}: {owner}"):
        AuthorityResolver(registry).resolve()


def test_document_role_cannot_be_promoted_by_registry(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["SALES_HUMAN"]["role"] = "LIVE_AUTHORITY"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document role mismatch: SALES_HUMAN"):
        AuthorityResolver(registry).resolve()


def test_checked_in_registry_declares_expected_bindings():
    payload = json.loads(Path("authority/current/registry.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 2
    assert payload["entries"] == BINDINGS
    assert set(payload["entries"]) == {owner.value for owner in Owner}
    assert {
        name: item["role"] for name, item in payload["documents"].items()
    } == {name: role for name, (role, _) in DOCUMENTS.items()}


def test_checked_in_document_structures_match_registry():
    payload = json.loads(Path("authority/current/registry.json").read_text(encoding="utf-8"))

    for name, (role, section) in DOCUMENTS.items():
        document = payload["documents"][name]
        assert document["path"] == f"authority/current/{name}.md"
        lines = [
            line.strip()
            for line in Path(document["path"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert lines[0] == f"# {name}"
        assert lines[1] == f"ROLE: {role}"
        assert lines[4] == section
