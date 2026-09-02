import hashlib
import json
from pathlib import Path

import pytest

from global_hybrid_v2.contracts import AuthorityDocumentRole, EffectType, Owner
from global_hybrid_v2.governance.authority import AuthorityError, AuthorityResolver
from global_hybrid_v2.governance.effects import EffectAuthorizationError, EffectGate

DOCUMENTS = {
    "GLOBAL": ("LIVE_AUTHORITY", "GLOBAL_WINDOW_CANONICAL.md", "GLOBAL"),
    "SALES": ("LIVE_AUTHORITY", "SALES_CANONICAL.md", "SALES"),
    "SALES_HUMAN_REFERENCE": (
        "REFERENCE_ONLY",
        "SALES_HUMAN_CANONICAL.md",
        "SALES",
    ),
    "LIBRARY": ("LIVE_AUTHORITY", "VEHICLE_KNOWLEDGE_BASE.md", "LIBRARY"),
    "REAL_CAR": ("CANONICAL", "REAL_CAR_統一正式指令.md", "REAL_CAR"),
}

NATIVE_AUTHORITY_ROLES = {
    "GLOBAL": "GLOBAL_CONTROL_PLANE",
    "SALES": "SALES_LIVE_RUNNER",
    "SALES_HUMAN_REFERENCE": (
        "HUMAN_INTERACTION_REFERENCE_FOR_SALES / NO_PARALLEL_LIVE_RUNNER"
    ),
    "LIBRARY": "VEHICLE_KNOWLEDGE",
    "REAL_CAR": "SHARED_VISUAL_EXECUTION_CANONICAL",
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


def _native_document(
    name: str,
    authority_role: str,
    owner: str,
    revision: str,
    *,
    include_optional_metadata: bool = True,
) -> str:
    optional = ""
    if include_optional_metadata:
        optional = f"OWNER: `{owner}`\nAUTHORITY_ROLE: `{authority_role}`\n"
    return (
        f"# Native canonical for {name}\n\n"
        f"CURRENT_REVISION: `{revision}`\n"
        "STATUS: `CURRENT`\n"
        f"{optional}"
        "\n---\n\n"
        "Native canonical content remains byte-for-byte owned by its source.\n"
        "\n## Historical notes\n\n"
        "CURRENT_REVISION: `historical-revision-that-must-not-be-read`\n"
    )


def _authority_tree(
    tmp_path: Path,
    *,
    revision: str = "rev-1",
    include_optional_metadata: bool = True,
) -> tuple[Path, dict]:
    current = tmp_path / "authority" / "current"
    current.mkdir(parents=True)
    documents = {}
    for name, (role, relative_path, owner) in DOCUMENTS.items():
        path = tmp_path / relative_path
        path.write_text(
            _native_document(
                name,
                NATIVE_AUTHORITY_ROLES[name],
                owner,
                revision,
                include_optional_metadata=include_optional_metadata,
            ),
            encoding="utf-8",
        )
        documents[name] = {
            "role": role,
            "expected_revision": revision,
            "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "path": relative_path,
        }

    registry = current / "registry.json"
    payload = {
        "schema_version": 6,
        "documents": documents,
        "entries": json.loads(json.dumps(BINDINGS)),
    }
    registry.write_text(json.dumps(payload), encoding="utf-8")
    return registry, payload


def _refresh_content_hash(registry: Path, payload: dict, name: str, path: Path) -> None:
    payload["documents"][name]["content_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    registry.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("document_name", DOCUMENTS)
def test_unset_expected_revision_fails_closed(tmp_path, document_name):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"][document_name]["expected_revision"] = "UNSET"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=f"expected revision unset: {document_name}"):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize("document_name", DOCUMENTS)
def test_unset_content_sha256_fails_closed(tmp_path, document_name):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"][document_name]["content_sha256"] = "UNSET"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=f"content SHA-256 unset: {document_name}"):
        AuthorityResolver(registry).resolve()


def test_native_canonical_headers_resolve_without_wrapper(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = AuthorityResolver(registry).resolve()

    assert set(snapshot.entries) == set(Owner)
    assert snapshot.entries[Owner.GLOBAL].revision == "rev-1"
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


def test_optional_native_owner_and_role_can_be_absent(tmp_path):
    registry, _ = _authority_tree(tmp_path, include_optional_metadata=False)

    snapshot = AuthorityResolver(registry).resolve()

    assert snapshot.entries[Owner.GLOBAL].revision == "rev-1"


def test_sales_human_domain_role_is_independent_from_reference_binding(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    header = (tmp_path / "SALES_HUMAN_CANONICAL.md").read_text(encoding="utf-8")
    assert (
        "AUTHORITY_ROLE: "
        "`HUMAN_INTERACTION_REFERENCE_FOR_SALES / NO_PARALLEL_LIVE_RUNNER`" in header
    )

    snapshot = AuthorityResolver(registry).resolve()

    sales_reference = snapshot.entries[Owner.SALES_HUMAN].references[0]
    assert sales_reference.role is AuthorityDocumentRole.REFERENCE_ONLY
    assert sales_reference.native_owner == "SALES"
    assert sales_reference.native_authority_role == (
        "HUMAN_INTERACTION_REFERENCE_FOR_SALES / NO_PARALLEL_LIVE_RUNNER"
    )


def test_later_historical_revision_does_not_override_native_header(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = AuthorityResolver(registry).resolve()

    assert all(entry.revision == "rev-1" for entry in snapshot.entries.values())


def test_shared_canonical_does_not_merge_effect_permissions(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    snapshot = AuthorityResolver(registry).resolve()
    assert snapshot.entries[Owner.VISUAL].revision == snapshot.entries[Owner.EXECUTION].revision

    with pytest.raises(EffectAuthorizationError, match="VISUAL cannot perform effects"):
        EffectGate().authorize(Owner.VISUAL, [EffectType.EXTERNAL_WRITE])
    EffectGate().authorize(Owner.EXECUTION, [EffectType.EXTERNAL_WRITE])


def test_missing_native_document_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    (tmp_path / "REAL_CAR_統一正式指令.md").unlink()

    with pytest.raises(AuthorityError, match="document unreadable: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_native_revision_must_match_expected_revision(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["REAL_CAR"]["expected_revision"] = "different-revision"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="native authority revision mismatch: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_native_content_hash_mismatch_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    path = tmp_path / "REAL_CAR_統一正式指令.md"
    path.write_bytes(path.read_bytes() + b"\nchanged after approval\n")

    with pytest.raises(AuthorityError, match="content SHA-256 mismatch: REAL_CAR"):
        AuthorityResolver(registry).resolve()


def test_native_status_must_be_current(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    path = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("STATUS: `CURRENT`", "STATUS: `DRAFT`"),
        encoding="utf-8",
    )
    _refresh_content_hash(registry, payload, "GLOBAL", path)

    with pytest.raises(AuthorityError, match="native authority status is not CURRENT: GLOBAL"):
        AuthorityResolver(registry).resolve()


def test_native_authority_owner_must_match_document_binding(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    path = tmp_path / "SALES_HUMAN_CANONICAL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("OWNER: `SALES`", "OWNER: `SALES_HUMAN`"),
        encoding="utf-8",
    )
    _refresh_content_hash(registry, payload, "SALES_HUMAN_REFERENCE", path)

    with pytest.raises(AuthorityError, match="native authority owner mismatch: SALES_HUMAN_REFERENCE"):
        AuthorityResolver(registry).resolve()


def test_duplicate_native_header_metadata_fails_closed(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    path = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "STATUS: `CURRENT`",
            "STATUS: `CURRENT`\nSTATUS: `CURRENT`",
        ),
        encoding="utf-8",
    )
    _refresh_content_hash(registry, payload, "GLOBAL", path)

    with pytest.raises(AuthorityError, match="duplicate native authority metadata: GLOBAL.STATUS"):
        AuthorityResolver(registry).resolve()


def test_legacy_wrapper_is_not_accepted_as_native_canonical(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    path = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    path.write_text(
        "# GLOBAL\n\n"
        "ROLE: LIVE_AUTHORITY\n"
        "STATUS: CURRENT\n"
        "REVISION: rev-1\n\n"
        "## Current Authority\n\n"
        + _native_document(
            "GLOBAL",
            NATIVE_AUTHORITY_ROLES["GLOBAL"],
            "GLOBAL",
            "rev-1",
        ),
        encoding="utf-8",
    )
    _refresh_content_hash(registry, payload, "GLOBAL", path)

    with pytest.raises(AuthorityError, match="native authority CURRENT_REVISION unset: GLOBAL"):
        AuthorityResolver(registry).resolve()


def test_document_path_must_map_to_exact_root_file(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["GLOBAL"]["path"] = "authority/current/GLOBAL_WINDOW_CANONICAL.md"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document path mismatch: GLOBAL"):
        AuthorityResolver(registry).resolve()


def test_duplicate_registry_binding_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    registry.write_text(
        '{"schema_version":6,"documents":{},"entries":{"GLOBAL":{},"GLOBAL":{}}}',
        encoding="utf-8",
    )

    with pytest.raises(AuthorityError, match="duplicate registry key: GLOBAL"):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version=5), "unsupported authority registry schema"),
        (lambda payload: payload.update(extra=True), "unexpected authority registry fields: extra"),
        (lambda payload: payload["documents"].pop("SALES"), "missing authority documents: SALES"),
        (
            lambda payload: payload["documents"].update(
                VISUAL={
                    "role": "LIVE_AUTHORITY",
                    "expected_revision": "rev-1",
                    "content_sha256": "0" * 64,
                    "path": "VISUAL.md",
                }
            ),
            "unexpected authority documents: VISUAL",
        ),
        (
            lambda payload: payload["documents"]["GLOBAL"].update(identity="not-allowed"),
            "unexpected authority document fields for GLOBAL: identity",
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
def test_registry_schema_and_exact_sets_fail_closed(tmp_path, mutation, message):
    registry, payload = _authority_tree(tmp_path)
    mutation(payload)
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=message):
        AuthorityResolver(registry).resolve()


@pytest.mark.parametrize(
    ("owner", "field", "value", "message"),
    [
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


def test_sales_human_reference_cannot_be_normative_authority(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["entries"]["SALES_HUMAN"]["normative_authority"] = "SALES_HUMAN_REFERENCE"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        AuthorityError,
        match="normative authority binding mismatch: SALES_HUMAN",
    ):
        AuthorityResolver(registry).resolve()


def test_reference_only_document_cannot_be_promoted_by_registry(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["SALES_HUMAN_REFERENCE"]["role"] = "LIVE_AUTHORITY"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match="document role mismatch: SALES_HUMAN_REFERENCE"):
        AuthorityResolver(registry).resolve()


def test_checked_in_registry_has_native_paths_and_unset_activation_metadata():
    payload = json.loads(Path("authority/current/registry.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 6
    assert payload["entries"] == BINDINGS
    assert set(payload["entries"]) == {owner.value for owner in Owner}
    assert set(payload["documents"]) == set(DOCUMENTS)
    for name, (role, path, _) in DOCUMENTS.items():
        assert payload["documents"][name] == {
            "role": role,
            "expected_revision": "UNSET",
            "content_sha256": "UNSET",
            "path": path,
        }


def test_checked_in_unset_registry_fails_closed_without_native_documents():
    with pytest.raises(AuthorityError, match="expected revision unset: GLOBAL"):
        AuthorityResolver("authority/current/registry.json").resolve()
