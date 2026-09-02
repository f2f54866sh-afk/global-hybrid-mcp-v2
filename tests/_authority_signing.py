from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

TEST_KEY_ID = "test-owner-ephemeral"
TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
TEST_PUBLIC_KEY = base64.b64encode(
    TEST_PRIVATE_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
).decode("ascii")


def activate_registry(
    registry: Path,
    *,
    signing_key: Ed25519PrivateKey = TEST_PRIVATE_KEY,
    key_id: str = TEST_KEY_ID,
) -> None:
    signature = signing_key.sign(registry.read_bytes())
    activation = {
        "schema_version": 1,
        "key_id": key_id,
        "signature_algorithm": "ed25519",
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    (registry.parent / "activation.json").write_text(
        json.dumps(activation, indent=2) + "\n",
        encoding="utf-8",
    )
