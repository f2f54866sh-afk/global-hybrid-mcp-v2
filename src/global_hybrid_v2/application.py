from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from global_hybrid_v2.contracts import Owner
from global_hybrid_v2.domains.base import DomainPort
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.settings import Settings


@dataclass(frozen=True)
class Application:
    repo_root: Path
    settings: Settings
    authority: AuthorityResolver
    trace: TraceBus
    dispatcher: Dispatcher


def create_application(
    *,
    repo_root: str | Path | None = None,
    settings: Settings | None = None,
    trace: TraceBus | None = None,
) -> Application:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[2]
    )
    runtime_settings = settings or Settings()
    registry_path = Path(runtime_settings.authority_registry)
    if not registry_path.is_absolute():
        registry_path = root / registry_path

    authority = AuthorityResolver(registry_path)
    runtime_trace = trace or TraceBus()
    domains: dict[Owner, DomainPort] = {
        owner: NotConfiguredDomain(owner)
        for owner in Owner
    }
    dispatcher = Dispatcher(
        authority=authority,
        domains=domains,
        trace=runtime_trace,
    )
    return Application(
        repo_root=root,
        settings=runtime_settings,
        authority=authority,
        trace=runtime_trace,
        dispatcher=dispatcher,
    )
