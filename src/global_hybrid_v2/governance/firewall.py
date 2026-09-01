from __future__ import annotations

from global_hybrid_v2.contracts import AuthoritySnapshot, ContextItem, ContextOrigin


class FirewallError(RuntimeError):
    pass


class TaskFirewall:
    ALLOWED_ORIGINS = {
        ContextOrigin.CURRENT_USER,
        ContextOrigin.CURRENT_AUTHORITY,
        ContextOrigin.CURRENT_TOOL_RESULT,
    }

    def filter(self, items: list[ContextItem], authority: AuthoritySnapshot) -> list[ContextItem]:
        accepted: list[ContextItem] = []
        for item in items:
            if item.origin not in self.ALLOWED_ORIGINS:
                continue
            if not item.purpose.strip() or not item.task_scope.strip():
                continue
            if item.origin == ContextOrigin.CURRENT_AUTHORITY:
                if not item.authority_owner or not item.authority_revision:
                    continue
                expected = authority.entries[item.authority_owner].revision
                if item.authority_revision != expected:
                    continue
            accepted.append(item)
        return accepted
