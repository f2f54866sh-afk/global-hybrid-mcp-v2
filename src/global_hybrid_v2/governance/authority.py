from __future__ import annotations

import json
from pathlib import Path

from global_hybrid_v2.contracts import AuthorityEntry, AuthoritySnapshot, Owner


class AuthorityError(RuntimeError):
    pass


class AuthorityResolver:
    REQUIRED = {
        Owner.GLOBAL,
        Owner.SALES_HUMAN,
        Owner.LIBRARY_FACT,
        Owner.VISUAL,
        Owner.EXECUTION,
    }

    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path)

    def resolve(self) -> AuthoritySnapshot:
        if not self.registry_path.exists():
            raise AuthorityError(f"authority registry missing: {self.registry_path}")

        raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        raw_entries = raw.get("entries", {})

        entries: dict[Owner, AuthorityEntry] = {}
        for owner in self.REQUIRED:
            item = raw_entries.get(owner.value)
            if not item:
                raise AuthorityError(f"missing current authority entry: {owner.value}")
            revision = str(item.get("revision", "")).strip()
            path = str(item.get("path", "")).strip()
            if not revision or revision.upper() == "UNSET":
                raise AuthorityError(f"current authority revision unset: {owner.value}")
            if not path:
                raise AuthorityError(f"current authority path unset: {owner.value}")
            entries[owner] = AuthorityEntry(owner=owner, revision=revision, path=path)

        return AuthoritySnapshot(entries=entries)
