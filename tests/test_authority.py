import json
from pathlib import Path

import pytest

from global_hybrid_v2.contracts import AuthorityDocumentRole, EffectType, Owner
from global_hybrid_v2.governance.authority import AuthorityError, AuthorityResolver
from global_hybrid_v2.governance.effects import EffectAuthorizationError, EffectGate

DOCUMENTS = {
    "GLOBAL": ("LIVE_AUTHORITY", "## Current Authority", "GLOBAL_WINDOW_CANONICAL.md"),
    "SALES": ("LIVE_AUTHORITY", "## Current Authority", "SALES_CANONICAL.md"),
    "SALES_HUMAN_REFERENCE": (
        "REFERENCE_ONLY",
        "## Reference Content",
        "SALES_HUMAN_CANONICAL.md",
    ),
    "LIBRARY": (
        "LIVE_AUTHORITY",
        "## Current Authority",
        "VEHICLE_KNOWLEDGE_BASE.md",
    ),
    "REAL_CAR": ("CANONICAL", "## Canonical Content", "REAL_CAR_統一正式指令.md"),
}

BINDINGS = {
    "GLOBAL": {
        "normative_authority": "GLOBAL",
        "authority_partition": None,
        "references": [],
    },
    "SALES_HUMAN": {
        "normative_authority": "SALES",
        "authority_partition": None,
        "references": ["SALES_HUMAN_REFERENCE"],
    },
    "LIBRARY_FACT": {
        "normative_authority": "LIBRARY",
        "authority_partition": None,
        "references": [],
    },
    "VISUAL": {
        "normative_authority": "REAL_CAR",
        "authority_partition": "VISUAL_JUDGE",
        "references": [],
    },
    "EXECUTION": {
        "normative_authority": "REAL_CAR",
        "authority_partition": "EXECUTION_LAB",
        "references": [],
    },
}

IDENTITIES = {
    "GLOBAL": "GLOBAL_CANONICAL_20260902_REPAIR_RESEARCH_EGRESS_MEDIATION",
    "SALES": "SALES_CANONICAL_20260901_SINGLE_LIVE_RUNNER_CONTRACT_NORMALIZATION",
    "SALES_HUMAN_REFERENCE": (
        "SALES_HUMAN_CANONICAL_20260901_REFERENCE_ONLY_CONSTRAINT_COMPACTION"
    ),
    "LIBRARY": "VEHICLE_KNOWLEDGE_BASE_20260901_SCHEMA_DATA_SEPARATION",
    "REAL_CAR": (
        "REAL_CAR_20260902_TEST_CIRCUIT_BREAKER_END_TO_END_RELEVANCE_GATE"
    ),
}


def _authority_tree(tmp_path: Path, *, revision: str = "rev-1") -> tuple[Path, dict]:
    current = tmp_path / "authority" / "current"
    current.mkdir(parents=True)
    documents = {}
    for name, (role, section, relative_path) in DOCUMENTS.items():
        path = tmp_path / relative_path
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
            "identity": revision,
            "revision": revision,
            "path": relative_path,
        }

    registry = current / "registry.json"
    payload = {
        "schema_version": 4,
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


def test_shared_real_car_binding_preserves_owner_partitions(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = AuthorityResolver(registry).resolve()

    assert set(snapshot.entries) == set(Owner)
    assert "REAL_CAR" not in {owner.value for owner in Owner}
    sales = snapshot.entries[Owner.SALES_HUMAN]
    assert sales.normative_authority.name == "SALES"
    assert sales.normative_authority.role is AuthorityDocumentRole.LIVE_AUTHORITY
    assert [item.name for item in sales.references] == ["SALES_HUMAN_REFERENCE"]
    assert sales.references[0].role is AuthorityDocumentRole.REFERENCE_ONLY

    visual = snapshot.entries[Owner.VISUAL]
    execution = snapshot.entries[Owner.EXECUTION]
    assert visual.normative_authority.name == "REAL_CAR"
    assert visual.normative_authority == execution.normative_authority
    assert visual.revision == execution.revision == "rev-1"
    assert visual.path == execution.path == "REAL_CAR_統一正式指令.md"
    assert visual.authority_partition == "VISUAL_JUDGE"
    assert execution.authority_partition == "EXECUTION_LAB"
    assert visual.authority_partition != execution.authority_partition


def test_shared_canonical_does_not_merge_effect_permissions(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    snapshot = AuthorityResolver(registry).resolve()
    assert snapshot.entries[Owner.VISUAL].revision == snapshot.entries[Owner.EXECUTION].revision

    with pytest.raises(EffectAuthorizationError, match="VISUAL cannot perform effects"):
        EffectGate().authorize(Owner.VISUAL, [EffectType.EXTERNAL_WRITE])
    EffectGate().authorize(Owner.EXECUTION, [EffectType.EXTERNAL_WRITE])


def test_missing_shared_real_car_document_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    (tmp_path / "REAL_CAR_統一正式指令.md").unlink()

    with pytest.raises(AuthorityError, match="document unreadable: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_real_car_revision_mismatch_fails_entire_snapshot_closed(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["REAL_CAR"]["revision"] = "different-revision"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="revision does not match identity: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_document_revision_must_match_registry(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    path = tmp_path / "REAL_CAR_統一正式指令.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("REVISION: rev-1", "REVISION: rev-2"),
        encoding="utf-8",
    )

    with pytest.raises(AuthorityError, match="document revision mismatch: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_document_identity_must_be_set_before_activation(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["REAL_CAR"]["identity"] = "UNSET"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document identity unset: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_document_revision_must_match_identity(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["GLOBAL"]["revision"] = "different-revision"
    path = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("REVISION: rev-1", "REVISION: different-revision"),
        encoding="utf-8",
    )
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="revision does not match identity: GLOBAL"):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("ROLE: LIVE_AUTHORITY", "ROLE: REFERENCE_ONLY", "file role mismatch"),
        ("STATUS: CURRENT", "STATUS: UNSET", "status is not CURRENT"),
        ("REVISION: rev-1", "REVISION: UNSET", "file revision unset"),
        ("test fixture content for GLOBAL", "UNSET", "content unset"),
        ("# GLOBAL", "# REAL_CAR", "name mismatch"),
    ],
)
def test_authority_document_metadata_fails_closed(tmp_path, old, new, message):
    registry, _ = _authority_tree(tmp_path)
    path = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

    with pytest.raises(AuthorityError, match=message):
        AuthorityResolver(registry).resolve()


def test_document_path_must_map_to_exact_root_file(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["GLOBAL"]["path"] = "authority/current/GLOBAL.md"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document path mismatch: GLOBAL"):
        AuthorityResolver(registry).resolve()


def test_registry_rejects_duplicate_document(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    registry.write_text(
        '{"schema_version": 4, "documents": {"GLOBAL": {}, "GLOBAL": {}}, "entries": {}}',
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
                VISUAL={
                    "role": "LIVE_AUTHORITY",
                    "identity": "rev-1",
                    "revision": "rev-1",
                    "path": "VISUAL.md",
                }
            ),
            "unexpected authority documents: VISUAL",
        ),
        (lambda payload: payload["entries"].pop("GLOBAL"), "missing current authority entries: GLOBAL"),
        (
            lambda payload: payload["entries"].update(
                SALES={
                    "normative_authority": "SALES",
                    "authority_partition": None,
                    "references": [],
                }
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
        (
            "SALES_HUMAN",
            "normative_authority",
            "SALES_HUMAN_REFERENCE",
            "normative authority binding mismatch",
        ),
        ("SALES_HUMAN", "references", [], "reference binding mismatch"),
        ("VISUAL", "normative_authority", "SALES", "normative authority binding mismatch"),
        ("VISUAL", "authority_partition", "EXECUTION_LAB", "authority partition binding mismatch"),
        ("EXECUTION", "authority_partition", "VISUAL_JUDGE", "authority partition binding mismatch"),
    ],
)
def test_partition_bindings_fail_closed(tmp_path, owner, field, value, message):
    registry, payload = _authority_tree(tmp_path)
    payload["entries"][owner][field] = value
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=f"{message}: {owner}"):
        AuthorityResolver(registry).resolve()


def test_reference_only_document_cannot_be_promoted_by_registry(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["SALES_HUMAN_REFERENCE"]["role"] = "LIVE_AUTHORITY"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document role mismatch: SALES_HUMAN_REFERENCE"):
        AuthorityResolver(registry).resolve()


def test_checked_in_registry_declares_expected_bindings_and_identities():
    payload = json.loads(Path("authority/current/registry.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 4
    assert payload["entries"] == BINDINGS
    assert set(payload["entries"]) == {owner.value for owner in Owner}
    assert set(payload["documents"]) == set(DOCUMENTS)
    assert {
        name: item["role"] for name, item in payload["documents"].items()
    } == {name: role for name, (role, _, _) in DOCUMENTS.items()}
    assert {
        name: item["identity"] for name, item in payload["documents"].items()
    } == IDENTITIES
    assert "VISUAL" not in payload["documents"]
    assert "EXECUTION" not in payload["documents"]


def test_checked_in_documents_are_exact_unset_placeholders():
    payload = json.loads(Path("authority/current/registry.json").read_text(encoding="utf-8"))

    for name, (role, section, expected_path) in DOCUMENTS.items():
        document = payload["documents"][name]
        assert document["path"] == expected_path
        assert document["revision"] == "UNSET"
        lines = [
            line.strip()
            for line in Path(document["path"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert lines == [
            f"# {name}",
            f"ROLE: {role}",
            "STATUS: UNSET",
            "REVISION: UNSET",
            section,
            "UNSET",
        ]


def test_checked_in_unset_registry_fails_closed():
    with pytest.raises(AuthorityError, match="document revision unset: GLOBAL"):
        AuthorityResolver("authority/current/registry.json").resolve()
