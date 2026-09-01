from __future__ import annotations

from global_hybrid_v2.contracts import Intent, Owner


class RouteError(RuntimeError):
    pass


ROUTES = {
    Intent.GOVERNANCE: Owner.GLOBAL,
    Intent.SALES_HUMAN: Owner.SALES_HUMAN,
    Intent.LIBRARY_FACT: Owner.LIBRARY_FACT,
    Intent.VISUAL: Owner.VISUAL,
    Intent.EXECUTION: Owner.EXECUTION,
}


class OwnerRouter:
    def route(self, intent: Intent) -> Owner:
        try:
            return ROUTES[intent]
        except KeyError as exc:
            raise RouteError(f"no unique owner for intent: {intent}") from exc
