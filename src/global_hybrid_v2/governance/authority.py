from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypeGuard

from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    Owner,
)


class AuthorityError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorityError(f"duplicate registry key: {key}")
        result[key] = value
    return result


class AuthorityResolver:
    SCHEMA_VERSION = 5
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

    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path)

    def resolve(self) -> AuthoritySnapshot:
        if not self.registry_path.exists():
            raise AuthorityError(f"authority registry missing: {self.registry_path}")

        try:
            raw = json.loads(
                self.registry_path.read_text(encoding="utf-8"),
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
                {"role", "expected_revision", "path"},
                set(item),
            )

            raw_role = item.get("role")
            raw_revision = item.get("expected_revision")
            raw_path = item.get("path")
            role = raw_role.strip() if isinstance(raw_role, str) else ""
            expected_revision = raw_revision.strip() if isinstance(raw_revision, str) else ""
            path = raw_path.strip() if isinstance(raw_path, str) else ""
            if role != expected_role.value:
                raise AuthorityError(f"authority document role mismatch: {name}")
            if not expected_revision or expected_revision.upper() == "UNSET":
                raise AuthorityError(f"authority document expected revision unset: {name}")
            if not path:
                raise AuthorityError(f"authority document path unset: {name}")

            configured_path = Path(path)
            if configured_path.is_absolute() or configured_path != expected_path:
                raise AuthorityError(f"authority document path mismatch: {name}")
            resolved_path = (registry_root / expected_path).resolve()
            if resolved_path.parent != registry_root:
                raise AuthorityError(f"authority document path escapes repository root: {name}")

            file_revision = self._validate_native_authority_file(
                resolved_path,
                name,
                expected_role,
                expected_owner,
                expected_revision,
            )
            documents[name] = AuthorityDocument(
                name=name,
                role=expected_role,
                revision=file_revision,
                path=path,
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
        expected_role: AuthorityDocumentRole,
        expected_owner: str,
        expected_revision: str,
    ) -> str:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
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

        declared_role = metadata.get("AUTHORITY_ROLE")
        if declared_role is not None and declared_role != expected_role.value:
            raise AuthorityError(f"native authority role mismatch: {name}")
        declared_owner = metadata.get("OWNER")
        if declared_owner is not None and declared_owner != expected_owner:
            raise AuthorityError(f"native authority owner mismatch: {name}")
        return revision

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
