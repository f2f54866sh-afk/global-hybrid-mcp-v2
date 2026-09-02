from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from pathlib import Path
from typing import Any, TypeGuard

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    Owner,
)


class AuthorityError(RuntimeError):
    pass


AUTHORITY_ACTIVATION_INVALID = "AUTHORITY_ACTIVATION_INVALID"
ACTIVATION_SCHEMA_VERSION = 1
SIGNATURE_ALGORITHM = "ed25519"
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityError(f"duplicate registry key: {key}")
        result[key] = value
    return result


class AuthorityResolver:
    SCHEMA_VERSION = 6
    REQUIRED = (
        Owner.GLOBAL,
        Owner.SALES_HUMAN,
        Owner.LIBRARY_FACT,
        Owner.VISUAL,
        Owner.EXECUTION,
    )
    DOCUMENTS = {
        "GLOBAL": (
            AuthorityDocumentRole.LIVE_AUTHORITY,
            Path("GLOBAL_WINDOW_CANONICAL.md"),
            "GLOBAL",
        ),
        "SALES": (
            AuthorityDocumentRole.LIVE_AUTHORITY,
            Path("SALES_CANONICAL.md"),
            "SALES",
        ),
        "SALES_HUMAN_REFERENCE": (
            AuthorityDocumentRole.REFERENCE_ONLY,
            Path("SALES_HUMAN_CANONICAL.md"),
            "SALES",
        ),
        "LIBRARY": (
            AuthorityDocumentRole.LIVE_AUTHORITY,
            Path("VEHICLE_KNOWLEDGE_BASE.md"),
            "LIBRARY",
        ),
        "REAL_CAR": (
            AuthorityDocumentRole.CANONICAL,
            Path("REAL_CAR_統一正式指令.md"),
            "REAL_CAR",
        ),
    }
    BINDINGS = {
        Owner.GLOBAL: ("GLOBAL", None, ()),
        Owner.SALES_HUMAN: ("SALES", None, ("SALES_HUMAN_REFERENCE",)),
        Owner.LIBRARY_FACT: ("LIBRARY", None, ()),
        Owner.VISUAL: ("REAL_CAR", "VISUAL_JUDGE", ()),
        Owner.EXECUTION: ("REAL_CAR", "EXECUTION_LAB", ()),
    }
    NATIVE_METADATA_KEYS = {"CURRENT_REVISION", "STATUS", "OWNER", "AUTHORITY_ROLE"}
    NATIVE_METADATA_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)\s*:\s*(.+?)\s*$")

    def __init__(
        self,
        registry_path: str | Path,
        *,
        trusted_key_id: str | None = None,
        trusted_public_key: str | None = None,
    ):
        self.registry_path = Path(registry_path)
        self.trusted_key_id = trusted_key_id
        self.trusted_public_key = trusted_public_key

    def resolve(self) -> AuthoritySnapshot:
        try:
            registry_bytes = self.registry_path.read_bytes()
        except OSError as exc:
            raise AuthorityError(AUTHORITY_ACTIVATION_INVALID) from exc

        self._verify_activation(registry_bytes)

        try:
            raw = json.loads(
                registry_bytes.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthorityError(f"authority registry unreadable: {self.registry_path}") from exc

        if not isinstance(raw, dict):
            raise AuthorityError("authority registry must be a JSON object")
        self._validate_exact_names(
            "authority registry fields",
            {"schema_version", "documents", "entries"},
            set(raw),
        )
        schema_version = raw.get("schema_version")
        if type(schema_version) is not int or schema_version != self.SCHEMA_VERSION:
            raise AuthorityError(f"unsupported authority registry schema: {schema_version}")

        raw_documents = raw.get("documents", {})
        if not isinstance(raw_documents, dict):
            raise AuthorityError("authority registry documents must be a JSON object")
        self._validate_exact_names("authority documents", set(self.DOCUMENTS), set(raw_documents))

        registry_root = self.registry_path.resolve().parents[2]
        documents: dict[str, AuthorityDocument] = {}
        for name, (expected_role, expected_path, expected_owner) in self.DOCUMENTS.items():
            item = raw_documents.get(name)
            if not isinstance(item, dict):
                raise AuthorityError(f"invalid authority document entry: {name}")
            self._validate_exact_names(
                f"authority document fields for {name}",
                {"role", "expected_revision", "content_sha256", "path"},
                set(item),
            )

            raw_role = item.get("role")
            raw_revision = item.get("expected_revision")
            raw_content_sha256 = item.get("content_sha256")
            raw_path = item.get("path")
            role = raw_role.strip() if isinstance(raw_role, str) else ""
            expected_revision = raw_revision.strip() if isinstance(raw_revision, str) else ""
            content_sha256 = (
                raw_content_sha256.strip() if isinstance(raw_content_sha256, str) else ""
            )
            path = raw_path.strip() if isinstance(raw_path, str) else ""
            if role != expected_role.value:
                raise AuthorityError(f"authority document role mismatch: {name}")
            if not expected_revision or expected_revision.upper() == "UNSET":
                raise AuthorityError(f"authority document expected revision unset: {name}")
            if not content_sha256 or content_sha256.upper() == "UNSET":
                raise AuthorityError(f"authority document content SHA-256 unset: {name}")
            if re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None:
                raise AuthorityError(f"authority document content SHA-256 invalid: {name}")
            if not path:
                raise AuthorityError(f"authority document path unset: {name}")

            configured_path = Path(path)
            if configured_path.is_absolute() or configured_path != expected_path:
                raise AuthorityError(f"authority document path mismatch: {name}")
            resolved_path = (registry_root / expected_path).resolve()
            if resolved_path.parent != registry_root:
                raise AuthorityError(f"authority document path escapes repository root: {name}")

            file_revision, native_owner, native_authority_role = (
                self._validate_native_authority_file(
                    resolved_path,
                    name,
                    expected_owner,
                    expected_revision,
                    content_sha256,
                )
            )
            documents[name] = AuthorityDocument(
                name=name,
                role=expected_role,
                revision=file_revision,
                path=path,
                native_owner=native_owner,
                native_authority_role=native_authority_role,
            )

        raw_entries = raw.get("entries", {})
        if not isinstance(raw_entries, dict):
            raise AuthorityError("authority registry entries must be a JSON object")
        self._validate_exact_names(
            "current authority entries",
            {owner.value for owner in self.REQUIRED},
            set(raw_entries),
        )

        entries: dict[Owner, AuthorityEntry] = {}
        for owner in self.REQUIRED:
            item = raw_entries.get(owner.value)
            if not isinstance(item, dict):
                raise AuthorityError(f"invalid current authority entry: {owner.value}")
            self._validate_exact_names(
                f"current authority binding fields for {owner.value}",
                {"normative_authority", "authority_partition", "references"},
                set(item),
            )

            normative = item.get("normative_authority")
            partition = item.get("authority_partition")
            references = item.get("references")
            if not isinstance(normative, str) or not self._is_string_list(references):
                raise AuthorityError(f"invalid current authority binding: {owner.value}")
            if partition is not None and not isinstance(partition, str):
                raise AuthorityError(f"invalid current authority binding: {owner.value}")

            expected_normative, expected_partition, expected_references = self.BINDINGS[owner]
            if normative != expected_normative:
                raise AuthorityError(f"normative authority binding mismatch: {owner.value}")
            if partition != expected_partition:
                raise AuthorityError(f"authority partition binding mismatch: {owner.value}")
            if tuple(references) != expected_references:
                raise AuthorityError(f"reference binding mismatch: {owner.value}")

            normative_document = documents[normative]
            reference_documents = [documents[name] for name in references]
            if normative_document.role is AuthorityDocumentRole.REFERENCE_ONLY:
                raise AuthorityError(f"normative authority role invalid: {owner.value}")
            if any(item.role is not AuthorityDocumentRole.REFERENCE_ONLY for item in reference_documents):
                raise AuthorityError(f"reference role invalid: {owner.value}")

            entries[owner] = AuthorityEntry(
                owner=owner,
                normative_authority=normative_document,
                authority_partition=partition,
                references=reference_documents,
            )

        return AuthoritySnapshot(entries=entries)

    def _verify_activation(self, registry_bytes: bytes) -> None:
        try:
            key_id = self.trusted_key_id or ""
            if KEY_ID_PATTERN.fullmatch(key_id) is None:
                raise ValueError("trusted key id is not configured")
            public_key_bytes = self._decode_base64(
                self.trusted_public_key,
                expected_length=32,
            )
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

            activation_path = self.registry_path.parent / "activation.json"
            activation = self._load_activation_json(activation_path)
            self._validate_exact_names(
                "authority activation fields",
                {
                    "schema_version",
                    "key_id",
                    "signature_algorithm",
                    "signature",
                },
                set(activation),
            )
            if activation.get("schema_version") != ACTIVATION_SCHEMA_VERSION:
                raise ValueError("unsupported activation schema")
            if activation.get("key_id") != key_id:
                raise ValueError("activation key id mismatch")
            if activation.get("signature_algorithm") != SIGNATURE_ALGORITHM:
                raise ValueError("activation signature algorithm mismatch")

            signature = self._decode_base64(activation.get("signature"), expected_length=64)
            public_key.verify(signature, registry_bytes)
        except (
            AuthorityError,
            InvalidSignature,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
            binascii.Error,
        ) as exc:
            raise AuthorityError(AUTHORITY_ACTIVATION_INVALID) from exc

    @staticmethod
    def _load_activation_json(path: Path) -> dict[str, Any]:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        if not isinstance(raw, dict):
            raise ValueError("activation metadata must be an object")
        return raw

    @staticmethod
    def _decode_base64(value: Any, *, expected_length: int) -> bytes:
        if not isinstance(value, str):
            raise ValueError("encoded activation value is invalid")
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != expected_length:
            raise ValueError("encoded activation value length is invalid")
        return decoded

    @staticmethod
    def _validate_exact_names(label: str, expected: set[str], actual: set[str]) -> None:
        missing = expected - actual
        if missing:
            names = ", ".join(sorted(missing))
            raise AuthorityError(f"missing {label}: {names}")
        unexpected = actual - expected
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise AuthorityError(f"unexpected {label}: {names}")

    @staticmethod
    def _is_string_list(value: Any) -> TypeGuard[list[str]]:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    @classmethod
    def _validate_native_authority_file(
        cls,
        path: Path,
        name: str,
        expected_owner: str,
        expected_revision: str,
        expected_content_sha256: str,
    ) -> tuple[str, str | None, str | None]:
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise AuthorityError(f"authority document unreadable: {name}") from exc

        actual_content_sha256 = hashlib.sha256(content).hexdigest()
        if actual_content_sha256 != expected_content_sha256:
            raise AuthorityError(f"authority document content SHA-256 mismatch: {name}")
        try:
            text = content.decode("utf-8")
        except UnicodeError as exc:
            raise AuthorityError(f"authority document unreadable: {name}") from exc

        if not text.strip() or text.strip().upper() == "UNSET":
            raise AuthorityError(f"authority document content unset: {name}")

        metadata: dict[str, str] = {}
        first_heading_seen = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                if first_heading_seen or metadata:
                    break
                first_heading_seen = True
                continue
            if stripped == "---" and metadata:
                break

            match = cls.NATIVE_METADATA_PATTERN.fullmatch(stripped)
            if not match or match.group(1) not in cls.NATIVE_METADATA_KEYS:
                continue
            key = match.group(1)
            if key in metadata:
                raise AuthorityError(f"duplicate native authority metadata: {name}.{key}")
            metadata[key] = cls._unwrap_metadata_value(match.group(2), name, key)

        revision = metadata.get("CURRENT_REVISION", "")
        status = metadata.get("STATUS", "")
        if not revision or revision.upper() == "UNSET":
            raise AuthorityError(f"native authority CURRENT_REVISION unset: {name}")
        if revision != expected_revision:
            raise AuthorityError(f"native authority revision mismatch: {name}")
        if status.upper() != "CURRENT":
            raise AuthorityError(f"native authority status is not CURRENT: {name}")

        declared_owner = metadata.get("OWNER")
        if declared_owner is not None and declared_owner != expected_owner:
            raise AuthorityError(f"native authority owner mismatch: {name}")
        return revision, declared_owner, metadata.get("AUTHORITY_ROLE")

    @staticmethod
    def _unwrap_metadata_value(value: str, name: str, key: str) -> str:
        value = value.strip()
        if value.startswith("`") or value.endswith("`"):
            if len(value) < 2 or not (value.startswith("`") and value.endswith("`")):
                raise AuthorityError(f"native authority metadata invalid: {name}.{key}")
            value = value[1:-1].strip()
        if not value:
            raise AuthorityError(f"native authority metadata invalid: {name}.{key}")
        return value
