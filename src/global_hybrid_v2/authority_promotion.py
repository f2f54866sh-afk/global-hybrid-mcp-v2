from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ACTIVATION_PATH = Path("authority/current/activation.json")
REGISTRY_PATH = Path("authority/current/registry.json")
ACTIVATION_FIELDS = {"schema_version", "key_id", "signature_algorithm", "signature"}


class PromotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionResult:
    verify: str
    registry_raw_sha256: str
    trusted_public_key_raw_sha256: str
    activation_signature_raw_sha256: str
    trusted_key_id: str
    activation_key_id: str
    registry_path: str


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PromotionError("ACTIVATION_DUPLICATE_KEY")
        result[key] = value
    return result


def _parse_activation(data: bytes, *, trusted_key_id: str) -> tuple[dict[str, Any], bytes]:
    try:
        activation = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionError("ACTIVATION_UNREADABLE") from exc
    if not isinstance(activation, dict) or set(activation) != ACTIVATION_FIELDS:
        raise PromotionError("ACTIVATION_SCHEMA_INVALID")
    if activation.get("schema_version") != 1:
        raise PromotionError("ACTIVATION_SCHEMA_INVALID")
    if activation.get("key_id") != trusted_key_id:
        raise PromotionError("ACTIVATION_KEY_ID_MISMATCH")
    if activation.get("signature_algorithm") != "ed25519":
        raise PromotionError("ACTIVATION_ALGORITHM_MISMATCH")
    signature = _decode_base64(activation.get("signature"), expected_length=64)
    return activation, signature


def _decode_base64(value: Any, *, expected_length: int) -> bytes:
    if not isinstance(value, str):
        raise PromotionError("ACTIVATION_ENCODING_INVALID")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise PromotionError("ACTIVATION_ENCODING_INVALID") from exc
    if len(decoded) != expected_length:
        raise PromotionError("ACTIVATION_ENCODING_INVALID")
    return decoded


def _git(repo_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise PromotionError("GIT_OPERATION_FAILED")
    return completed.stdout


def _verify_signature(
    *,
    registry_bytes: bytes,
    signature: bytes,
    public_key_bytes: bytes,
) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature,
            registry_bytes,
        )
    except (InvalidSignature, ValueError) as exc:
        raise PromotionError("OWNER_SIGNATURE_INVALID") from exc


def promote_activation(
    *,
    repo_root: str | Path,
    owner_signed_activation_path: str | Path,
    trusted_key_id: str,
    trusted_public_key: str,
) -> PromotionResult:
    root = Path(repo_root).resolve()
    source_path = Path(owner_signed_activation_path).resolve()
    target_path = root / ACTIVATION_PATH
    if not source_path.is_file():
        raise PromotionError("OWNER_ACTIVATION_SOURCE_MISSING")
    if target_path.resolve().parent != (root / ACTIVATION_PATH.parent).resolve():
        raise PromotionError("ACTIVATION_TARGET_INVALID")

    source_bytes = source_path.read_bytes()
    source_activation, source_signature = _parse_activation(
        source_bytes,
        trusted_key_id=trusted_key_id,
    )
    public_key_bytes = _decode_base64(trusted_public_key.strip(), expected_length=32)
    registry_bytes = _git(root, "show", f":{REGISTRY_PATH.as_posix()}")

    # Preflight prevents an invalid owner file from replacing the current activation.
    _verify_signature(
        registry_bytes=registry_bytes,
        signature=source_signature,
        public_key_bytes=public_key_bytes,
    )

    target_path.write_bytes(source_bytes)
    if target_path.read_bytes() != source_bytes:
        raise PromotionError("ACTIVATION_READBACK_MISMATCH")

    _git(root, "add", "--", ACTIVATION_PATH.as_posix())
    staged_activation_bytes = _git(root, "show", f":{ACTIVATION_PATH.as_posix()}")
    staged_activation, staged_signature = _parse_activation(
        staged_activation_bytes,
        trusted_key_id=trusted_key_id,
    )
    if staged_activation != source_activation:
        raise PromotionError("ACTIVATION_STAGED_CONTENT_MISMATCH")
    staged_registry_bytes = _git(root, "show", f":{REGISTRY_PATH.as_posix()}")
    _verify_signature(
        registry_bytes=staged_registry_bytes,
        signature=staged_signature,
        public_key_bytes=public_key_bytes,
    )

    return PromotionResult(
        verify="PASS",
        registry_raw_sha256=hashlib.sha256(staged_registry_bytes).hexdigest(),
        trusted_public_key_raw_sha256=hashlib.sha256(public_key_bytes).hexdigest(),
        activation_signature_raw_sha256=hashlib.sha256(staged_signature).hexdigest(),
        trusted_key_id=trusted_key_id,
        activation_key_id=str(staged_activation["key_id"]),
        registry_path=REGISTRY_PATH.as_posix(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote an owner-signed activation file with exact-byte readback verification."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--owner-signed-activation", required=True)
    parser.add_argument("--trusted-key-id", required=True)
    parser.add_argument("--trusted-public-key-file", required=True)
    args = parser.parse_args()

    trusted_public_key = Path(args.trusted_public_key_file).read_text(encoding="utf-8").strip()
    result = promote_activation(
        repo_root=args.repo_root,
        owner_signed_activation_path=args.owner_signed_activation,
        trusted_key_id=args.trusted_key_id,
        trusted_public_key=trusted_public_key,
    )
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
