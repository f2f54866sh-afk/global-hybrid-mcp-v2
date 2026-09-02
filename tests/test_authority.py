import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from global_hybrid_v2.contracts import AuthorityDocumentRole, EffectType, Owner
from global_hybrid_v2.governance.authority import (
    AUTHORITY_ACTIVATION_INVALID,
    AuthorityError,
    AuthorityResolver,
)
from global_hybrid_v2.governance.effects import EffectAuthorizationError, EffectGate
from tests._authority_signing import (
    TEST_KEY_ID,
    TEST_PUBLIC_KEY,
    activate_registry,
)

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

CURRENT_DOCUMENTS = {
    "GLOBAL": (
        "GLOBAL_CANONICAL_20260902_REPAIR_RESEARCH_EGRESS_MEDIATION",
        "33bbc43d6f4293daa5d2f411b46808d3132ccc4db404f20474ca501a4df148ab",
    ),
    "SALES": (
        "SALES_CANONICAL_20260901_SINGLE_LIVE_RUNNER_CONTRACT_NORMALIZATION",
        "1988b9a3bad15d4357c6f5717c81e7220be82623871ac1ab7065e0cb51e0f0a8",
    ),
    "SALES_HUMAN_REFERENCE": (
        "SALES_HUMAN_CANONICAL_20260901_REFERENCE_ONLY_CONSTRAINT_COMPACTION",
        "fdfbaa34c77186524a85fb2d12b00b67488539ed6c1ca5757cac4660485166d8",
    ),
    "LIBRARY": (
        "VEHICLE_KNOWLEDGE_BASE_20260901_SCHEMA_DATA_SEPARATION",
        "601cf5525e3e88cf8263f8b559a4bfea69816dea4ec0eeabb889810ac84a4252",
    ),
    "REAL_CAR": (
        "REAL_CAR_20260902_TEST_CIRCUIT_BREAKER_END_TO_END_RELEVANCE_GATE",
        "99e1b50ff133e7102e62a1a8cc8417c45df82e0b50856a740cd1ffb82c8545f7",
    ),
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
    _write_registry(registry, payload)
    return registry, payload


def _write_registry(registry: Path, payload: dict) -> None:
    registry.write_text(json.dumps(payload), encoding="utf-8")
    activate_registry(registry)


def _resolver(
    registry: str | Path,
    *,
    trusted_public_key: str = TEST_PUBLIC_KEY,
) -> AuthorityResolver:
    return AuthorityResolver(
        registry,
        trusted_key_id=TEST_KEY_ID,
        trusted_public_key=trusted_public_key,
    )


def _refresh_content_hash(registry: Path, payload: dict, name: str, path: Path) -> None:
    payload["documents"][name]["content_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    _write_registry(registry, payload)


@pytest.mark.parametrize("document_name", DOCUMENTS)
def test_unset_expected_revision_fails_closed(tmp_path, document_name):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"][document_name]["expected_revision"] = "UNSET"
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match=f"expected revision unset: {document_name}"):
        _resolver(registry).resolve()


@pytest.mark.parametrize("document_name", DOCUMENTS)
def test_unset_content_sha256_fails_closed(tmp_path, document_name):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"][document_name]["content_sha256"] = "UNSET"
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match=f"content SHA-256 unset: {document_name}"):
        _resolver(registry).resolve()


def test_native_canonical_headers_resolve_without_wrapper(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = _resolver(registry).resolve()

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

    snapshot = _resolver(registry).resolve()

    assert snapshot.entries[Owner.GLOBAL].revision == "rev-1"


def test_sales_human_domain_role_is_independent_from_reference_binding(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    header = (tmp_path / "SALES_HUMAN_CANONICAL.md").read_text(encoding="utf-8")
    assert (
        "AUTHORITY_ROLE: "
        "`HUMAN_INTERACTION_REFERENCE_FOR_SALES / NO_PARALLEL_LIVE_RUNNER`" in header
    )

    snapshot = _resolver(registry).resolve()

    sales_reference = snapshot.entries[Owner.SALES_HUMAN].references[0]
    assert sales_reference.role is AuthorityDocumentRole.REFERENCE_ONLY
    assert sales_reference.native_owner == "SALES"
    assert sales_reference.native_authority_role == (
        "HUMAN_INTERACTION_REFERENCE_FOR_SALES / NO_PARALLEL_LIVE_RUNNER"
    )


def test_later_historical_revision_does_not_override_native_header(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = _resolver(registry).resolve()

    assert all(entry.revision == "rev-1" for entry in snapshot.entries.values())


def test_shared_canonical_does_not_merge_effect_permissions(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    snapshot = _resolver(registry).resolve()
    assert snapshot.entries[Owner.VISUAL].revision == snapshot.entries[Owner.EXECUTION].revision

    with pytest.raises(EffectAuthorizationError, match="VISUAL cannot perform effects"):
        EffectGate().authorize(Owner.VISUAL, [EffectType.EXTERNAL_WRITE])
    EffectGate().authorize(Owner.EXECUTION, [EffectType.EXTERNAL_WRITE])


def test_missing_native_document_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    (tmp_path / "REAL_CAR_統一正式指令.md").unlink()

    with pytest.raises(AuthorityError, match="document unreadable: REAL_CAR"):
        _resolver(registry).resolve()


def test_native_revision_must_match_expected_revision(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["REAL_CAR"]["expected_revision"] = "different-revision"
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match="native authority revision mismatch: REAL_CAR"):
        _resolver(registry).resolve()


def test_native_content_hash_mismatch_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    path = tmp_path / "REAL_CAR_統一正式指令.md"
    path.write_bytes(path.read_bytes() + b"\nchanged after approval\n")

    with pytest.raises(AuthorityError, match="content SHA-256 mismatch: REAL_CAR"):
        _resolver(registry).resolve()


def test_native_status_must_be_current(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    path = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("STATUS: `CURRENT`", "STATUS: `DRAFT`"),
        encoding="utf-8",
    )
    _refresh_content_hash(registry, payload, "GLOBAL", path)

    with pytest.raises(AuthorityError, match="native authority status is not CURRENT: GLOBAL"):
        _resolver(registry).resolve()


def test_native_authority_owner_must_match_document_binding(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    path = tmp_path / "SALES_HUMAN_CANONICAL.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("OWNER: `SALES`", "OWNER: `SALES_HUMAN`"),
        encoding="utf-8",
    )
    _refresh_content_hash(registry, payload, "SALES_HUMAN_REFERENCE", path)

    with pytest.raises(AuthorityError, match="native authority owner mismatch: SALES_HUMAN_REFERENCE"):
        _resolver(registry).resolve()


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
        _resolver(registry).resolve()


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
        _resolver(registry).resolve()


def test_document_path_must_map_to_exact_root_file(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["GLOBAL"]["path"] = "authority/current/GLOBAL_WINDOW_CANONICAL.md"
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match="document path mismatch: GLOBAL"):
        _resolver(registry).resolve()


def test_duplicate_registry_binding_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    registry.write_text(
        '{"schema_version":6,"documents":{},"entries":{"GLOBAL":{},"GLOBAL":{}}}',
        encoding="utf-8",
    )
    activate_registry(registry)

    with pytest.raises(AuthorityError, match="duplicate registry key: GLOBAL"):
        _resolver(registry).resolve()


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
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match=message):
        _resolver(registry).resolve()


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
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match=f"{message}: {owner}"):
        _resolver(registry).resolve()


def test_sales_human_reference_cannot_be_normative_authority(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["entries"]["SALES_HUMAN"]["normative_authority"] = "SALES_HUMAN_REFERENCE"
    _write_registry(registry, payload)

    with pytest.raises(
        AuthorityError,
        match="normative authority binding mismatch: SALES_HUMAN",
    ):
        _resolver(registry).resolve()


def test_reference_only_document_cannot_be_promoted_by_registry(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    payload["documents"]["SALES_HUMAN_REFERENCE"]["role"] = "LIVE_AUTHORITY"
    _write_registry(registry, payload)

    with pytest.raises(AuthorityError, match="document role mismatch: SALES_HUMAN_REFERENCE"):
        _resolver(registry).resolve()


def test_checked_in_registry_has_exact_current_activation_metadata():
    payload = json.loads(Path("authority/current/registry.json").read_text(encoding="utf-8"))

    assert payload["schema_version"] == 6
    assert payload["entries"] == BINDINGS
    assert set(payload["entries"]) == {owner.value for owner in Owner}
    assert set(payload["documents"]) == set(DOCUMENTS)
    for name, (role, path, _) in DOCUMENTS.items():
        revision, content_sha256 = CURRENT_DOCUMENTS[name]
        assert payload["documents"][name] == {
            "role": role,
            "expected_revision": revision,
            "content_sha256": content_sha256,
            "path": path,
        }


def test_checked_in_canonical_exact_bytes_match_registry_hashes():
    for name, (_, path, _) in DOCUMENTS.items():
        _, content_sha256 = CURRENT_DOCUMENTS[name]
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == content_sha256


def test_checked_in_candidate_waits_for_owner_trust_root():
    with pytest.raises(AuthorityError, match=AUTHORITY_ACTIVATION_INVALID):
        AuthorityResolver("authority/current/registry.json").resolve()


def test_valid_activation_signature_resolves_current_authority(tmp_path):
    registry, _ = _authority_tree(tmp_path)

    snapshot = _resolver(registry).resolve()

    assert set(snapshot.entries) == set(Owner)


def test_canonical_and_registry_change_without_resigning_fails_activation(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    canonical = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    canonical.write_bytes(canonical.read_bytes() + b"\ncandidate change\n")
    payload["documents"]["GLOBAL"]["content_sha256"] = hashlib.sha256(
        canonical.read_bytes()
    ).hexdigest()
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AuthorityError, match=AUTHORITY_ACTIVATION_INVALID):
        _resolver(registry).resolve()


def test_rewritten_activation_without_trusted_private_key_fails(tmp_path):
    registry, payload = _authority_tree(tmp_path)
    canonical = tmp_path / "GLOBAL_WINDOW_CANONICAL.md"
    canonical.write_bytes(canonical.read_bytes() + b"\nunauthorized candidate\n")
    payload["documents"]["GLOBAL"]["content_sha256"] = hashlib.sha256(
        canonical.read_bytes()
    ).hexdigest()
    registry.write_text(json.dumps(payload), encoding="utf-8")
    activate_registry(
        registry,
        signing_key=Ed25519PrivateKey.generate(),
    )

    with pytest.raises(AuthorityError, match=AUTHORITY_ACTIVATION_INVALID):
        _resolver(registry).resolve()


def test_repository_public_key_cannot_replace_external_trust_root(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    attacker_key = Ed25519PrivateKey.generate()
    attacker_public_key = base64.b64encode(
        attacker_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    activate_registry(
        registry,
        signing_key=attacker_key,
    )
    trust_dir = tmp_path / "authority" / "trust"
    trust_dir.mkdir(parents=True)
    (trust_dir / f"{TEST_KEY_ID}.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "key_id": TEST_KEY_ID,
                "signature_algorithm": "ed25519",
                "public_key": attacker_public_key,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AuthorityError, match=AUTHORITY_ACTIVATION_INVALID):
        _resolver(registry).resolve()


def test_wrong_external_public_key_fails_activation(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    wrong_key = Ed25519PrivateKey.generate()
    wrong_public_key = base64.b64encode(
        wrong_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")

    with pytest.raises(AuthorityError, match=AUTHORITY_ACTIVATION_INVALID):
        _resolver(registry, trusted_public_key=wrong_public_key).resolve()


def test_malformed_activation_fails_closed(tmp_path):
    registry, _ = _authority_tree(tmp_path)
    (registry.parent / "activation.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(AuthorityError, match=AUTHORITY_ACTIVATION_INVALID):
        _resolver(registry).resolve()
