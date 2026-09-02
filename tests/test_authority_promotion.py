import base64
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from global_hybrid_v2.authority_promotion import (
    PromotionError,
    promote_activation,
)
from tests._authority_signing import TEST_KEY_ID, TEST_PRIVATE_KEY, TEST_PUBLIC_KEY


def _git(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
    ).stdout


def _promotion_tree(tmp_path: Path) -> tuple[Path, Path, str, bytes]:
    repo_root = tmp_path / "repo"
    current = repo_root / "authority" / "current"
    current.mkdir(parents=True)
    registry_bytes = b'{"schema_version":6,"candidate":"exact-registry-bytes"}\n'
    (current / "registry.json").write_bytes(registry_bytes)
    (current / "activation.json").write_text("existing\n", encoding="utf-8")

    _git(repo_root, "init")
    _git(repo_root, "config", "core.autocrlf", "true")
    _git(repo_root, "add", "--", "authority/current/registry.json")
    _git(repo_root, "add", "--", "authority/current/activation.json")

    signature = TEST_PRIVATE_KEY.sign(registry_bytes)
    activation = {
        "schema_version": 1,
        "key_id": TEST_KEY_ID,
        "signature_algorithm": "ed25519",
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    source_path = tmp_path / "owner-signed-activation.json"
    source_path.write_bytes(
        (json.dumps(activation, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8")
    )
    return repo_root, source_path, TEST_PUBLIC_KEY, signature


def test_promotion_copies_owner_file_then_readbacks_and_verifies_staged_bytes(tmp_path):
    repo_root, source_path, trusted_public_key, signature = _promotion_tree(tmp_path)

    result = promote_activation(
        repo_root=repo_root,
        owner_signed_activation_path=source_path,
        trusted_key_id=TEST_KEY_ID,
        trusted_public_key=trusted_public_key,
    )

    target_path = repo_root / "authority" / "current" / "activation.json"
    assert target_path.read_bytes() == source_path.read_bytes()
    staged_activation = _git(repo_root, "show", ":authority/current/activation.json")
    assert staged_activation != source_path.read_bytes()
    assert json.loads(staged_activation) == json.loads(source_path.read_bytes())
    assert result.verify == "PASS"
    assert result.registry_raw_sha256 == hashlib.sha256(
        _git(repo_root, "show", ":authority/current/registry.json")
    ).hexdigest()
    assert result.activation_signature_raw_sha256 == hashlib.sha256(signature).hexdigest()


def test_promotion_rejects_transcription_error_before_replacing_activation(tmp_path):
    repo_root, source_path, trusted_public_key, _ = _promotion_tree(tmp_path)
    target_path = repo_root / "authority" / "current" / "activation.json"
    original_target = target_path.read_bytes()
    activation = json.loads(source_path.read_text(encoding="utf-8"))
    signature = base64.b64decode(activation["signature"], validate=True)
    activation["signature"] = base64.b64encode(bytes([signature[0] ^ 1]) + signature[1:]).decode(
        "ascii"
    )
    source_path.write_bytes((json.dumps(activation, indent=2) + "\n").encode("utf-8"))

    with pytest.raises(PromotionError, match="OWNER_SIGNATURE_INVALID"):
        promote_activation(
            repo_root=repo_root,
            owner_signed_activation_path=source_path,
            trusted_key_id=TEST_KEY_ID,
            trusted_public_key=trusted_public_key,
        )

    assert target_path.read_bytes() == original_target
