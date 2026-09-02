from __future__ import annotations

import json
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
    SCHEMA_VERSION = 3
    REQUIRED = (
        Owner.GLOBAL,
        Owner.SALES_HUMAN,
        Owner.LIBRARY_FACT,
        Owner.VISUAL,
        Owner.EXECUTION,
    )
    DOCUMENTS = {
        "GLOBAL": (AuthorityDocumentRole.LIVE_AUTHORITY, "## Current Authority"),
        "SALES": (AuthorityDocumentRole.LIVE_AUTHORITY, "## Current Authority"),
        "SALES_HUMAN": (AuthorityDocumentRole.REFERENCE_ONLY, "## Reference Content"),
        "LIBRARY_FACT": (AuthorityDocumentRole.LIVE_AUTHORITY, "## Current Authority"),
        "VISUAL": (AuthorityDocumentRole.LIVE_AUTHORITY, "## Current Authority"),
        "EXECUTION": (AuthorityDocumentRole.LIVE_AUTHORITY, "## Current Authority"),
        "REAL_CAR": (AuthorityDocumentRole.CANONICAL, "## Canonical Content"),
    }
    BINDINGS = {
        Owner.GLOBAL: ("GLOBAL", (), ()),
        Owner.SALES_HUMAN: ("SALES", ("SALES_HUMAN",), ()),
        Owner.LIBRARY_FACT: ("LIBRARY_FACT", (), ()),
        Owner.VISUAL: ("VISUAL", (), ("REAL_CAR",)),
        Owner.EXECUTION: ("EXECUTION", (), ("REAL_CAR",)),
    }

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
        schema_version = raw.get("schema_version")
        if type(schema_version) is not int or schema_version != self.SCHEMA_VERSION:
            raise AuthorityError(f"unsupported authority registry schema: {schema_version}")

        raw_documents = raw.get("documents", {})
        if not isinstance(raw_documents, dict):
            raise AuthorityError("authority registry documents must be a JSON object")
        self._validate_exact_names("authority documents", set(self.DOCUMENTS), set(raw_documents))

        registry_root = self.registry_path.resolve().parents[2]
        documents: dict[str, AuthorityDocument] = {}
        for name, (expected_role, section) in self.DOCUMENTS.items():
            item = raw_documents.get(name)
            if not isinstance(item, dict):
                raise AuthorityError(f"invalid authority document entry: {name}")

            raw_role = item.get("role")
            raw_identity = item.get("identity")
            raw_revision = item.get("revision")
            raw_path = item.get("path")
            role = raw_role.strip() if isinstance(raw_role, str) else ""
            identity = raw_identity.strip() if isinstance(raw_identity, str) else ""
            revision = raw_revision.strip() if isinstance(raw_revision, str) else ""
            path = raw_path.strip() if isinstance(raw_path, str) else ""
            if role != expected_role.value:
                raise AuthorityError(f"authority document role mismatch: {name}")
            if not revision or revision.upper() == "UNSET":
                raise AuthorityError(f"authority document revision unset: {name}")
            if not identity or identity.upper() == "UNSET":
                raise AuthorityError(f"authority document identity unset: {name}")
            if revision != identity:
                raise AuthorityError(f"authority document revision does not match identity: {name}")
            if not path:
                raise AuthorityError(f"authority document path unset: {name}")

            expected_path = Path("authority") / "current" / f"{name}.md"
            configured_path = Path(path)
            if configured_path.is_absolute() or configured_path != expected_path:
                raise AuthorityError(f"authority document path mismatch: {name}")
            resolved_path = (registry_root / expected_path).resolve()
            if resolved_path.parent != self.registry_path.resolve().parent:
                raise AuthorityError(f"authority document path escapes current directory: {name}")

            self._validate_authority_file(resolved_path, name, expected_role, revision, section)
            documents[name] = AuthorityDocument(
                name=name,
                role=expected_role,
                identity=identity,
                revision=revision,
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

            live = item.get("live_authority")
            references = item.get("references")
            canonicals = item.get("canonicals")
            if not isinstance(live, str) or not self._is_string_list(references):
                raise AuthorityError(f"invalid current authority binding: {owner.value}")
            if not self._is_string_list(canonicals):
                raise AuthorityError(f"invalid current authority binding: {owner.value}")

            expected_live, expected_references, expected_canonicals = self.BINDINGS[owner]
            if live != expected_live:
                raise AuthorityError(f"live authority binding mismatch: {owner.value}")
            if tuple(references) != expected_references:
                raise AuthorityError(f"reference binding mismatch: {owner.value}")
            if tuple(canonicals) != expected_canonicals:
                raise AuthorityError(f"canonical binding mismatch: {owner.value}")

            live_document = documents[live]
            reference_documents = [documents[name] for name in references]
            canonical_documents = [documents[name] for name in canonicals]
            if live_document.role is not AuthorityDocumentRole.LIVE_AUTHORITY:
                raise AuthorityError(f"live authority role invalid: {owner.value}")
            if any(item.role is not AuthorityDocumentRole.REFERENCE_ONLY for item in reference_documents):
                raise AuthorityError(f"reference role invalid: {owner.value}")
            if any(item.role is not AuthorityDocumentRole.CANONICAL for item in canonical_documents):
                raise AuthorityError(f"canonical role invalid: {owner.value}")

            entries[owner] = AuthorityEntry(
                owner=owner,
                live_authority=live_document,
                references=reference_documents,
                canonicals=canonical_documents,
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

    @staticmethod
    def _validate_authority_file(
        path: Path,
        name: str,
        expected_role: AuthorityDocumentRole,
        expected_revision: str,
        expected_section: str,
    ) -> None:
        try:
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeError) as exc:
            raise AuthorityError(f"authority document unreadable: {name}") from exc

        if len(lines) < 5 or lines[0] != f"# {name}":
            raise AuthorityError(f"authority document name mismatch: {name}")

        role_prefix = "ROLE:"
        status_prefix = "STATUS:"
        revision_prefix = "REVISION:"
        if (
            not lines[1].startswith(role_prefix)
            or not lines[2].startswith(status_prefix)
            or not lines[3].startswith(revision_prefix)
        ):
            raise AuthorityError(f"authority document metadata invalid: {name}")

        role = lines[1][len(role_prefix) :].strip()
        status = lines[2][len(status_prefix) :].strip()
        revision = lines[3][len(revision_prefix) :].strip()
        if role != expected_role.value:
            raise AuthorityError(f"authority document file role mismatch: {name}")
        if status.upper() != "CURRENT":
            raise AuthorityError(f"authority document status is not CURRENT: {name}")
        if not revision or revision.upper() == "UNSET":
            raise AuthorityError(f"authority document file revision unset: {name}")
        if revision != expected_revision:
            raise AuthorityError(f"authority document revision mismatch: {name}")
        if lines[4] != expected_section or len(lines) < 6 or lines[5].upper() == "UNSET":
            raise AuthorityError(f"authority document content unset: {name}")
