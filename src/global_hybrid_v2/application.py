from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from global_hybrid_v2.adapters.openai_research import configured_research_port
from global_hybrid_v2.contracts import Owner
from global_hybrid_v2.domains.base import DomainPort
from global_hybrid_v2.domains.library_projection import LibraryProjectionDomain
from global_hybrid_v2.domains.sales_media import SalesMediaDomain
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.effects import EffectGate
from global_hybrid_v2.governance.fitness import FitnessReport, SystemFitnessFunctions
from global_hybrid_v2.governance.host_projection import HostCurrentStateVerifier, HostProjectionGate
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.research import (
    ResearchExecutor,
    ResearchPort,
)
from global_hybrid_v2.runtime.deployment import RuntimeIdentity, read_runtime_identity
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus
from global_hybrid_v2.settings import Settings


@dataclass(frozen=True)
class Application:
    repo_root: Path
    settings: Settings
    authority: AuthorityResolver
    research_executor: ResearchExecutor
    runtime_identity: RuntimeIdentity
    trace: TraceBus
    dispatcher: Dispatcher
    composition_fitness: FitnessReport | None = None


def create_application(
    *,
    repo_root: str | Path | None = None,
    settings: Settings | None = None,
    trace: TraceBus | None = None,
    research: ResearchPort | None = None,
    runtime_identity: RuntimeIdentity | None = None,
    host_current_state_verifier: HostCurrentStateVerifier | None = None,
) -> Application:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[2]
    )
    runtime_settings = settings or Settings()
    effective_runtime_identity = runtime_identity or read_runtime_identity()
    registry_path = Path(runtime_settings.authority_registry)
    if not registry_path.is_absolute():
        registry_path = root / registry_path

    authority = AuthorityResolver(
        registry_path,
        trusted_key_id=runtime_settings.authority_trusted_key_id,
        trusted_public_key=runtime_settings.authority_trusted_public_key,
    )
    runtime_trace = trace or TraceBus()
    runtime_trace.attach_witness(ReadOnlyWitness())
    research_port = research if research is not None else configured_research_port(runtime_settings)
    research_executor = ResearchExecutor(research_port)
    domains: dict[Owner, DomainPort] = {
        owner: NotConfiguredDomain(owner)
        for owner in Owner
    }
    domains[Owner.LIBRARY_FACT] = LibraryProjectionDomain()
    domains[Owner.SALES_HUMAN] = SalesMediaDomain()
    composition_fitness = SystemFitnessFunctions.evaluate_composition(
        domains=domains,
        trace=runtime_trace,
    )
    if not composition_fitness.passed:
        blockers = ", ".join(
            check.blocker or check.name
            for check in composition_fitness.checks
            if not check.passed
        )
        raise RuntimeError(f"runtime composition fitness failed: {blockers}")
    dispatcher = Dispatcher(
        authority=authority,
        domains=domains,
        trace=runtime_trace,
        research_executor=research_executor,
        runtime_commit=effective_runtime_identity.git_commit,
        runtime_branch=effective_runtime_identity.git_branch,
        host_projection_gate=HostProjectionGate(verifier=host_current_state_verifier),
        effect_gate=EffectGate(live_execution=runtime_settings.live_execution),
    )
    return Application(
        repo_root=root,
        settings=runtime_settings,
        authority=authority,
        research_executor=research_executor,
        runtime_identity=effective_runtime_identity,
        trace=runtime_trace,
        dispatcher=dispatcher,
        composition_fitness=composition_fitness,
    )
