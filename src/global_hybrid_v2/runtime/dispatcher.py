from __future__ import annotations

from global_hybrid_v2.contracts import Owner, TaskContract, TaskRequest
from global_hybrid_v2.domains.base import DomainPort
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.effects import EffectGate
from global_hybrid_v2.governance.egress import RUN_REQUIRED_RESEARCH, ResponseEgressValidator
from global_hybrid_v2.governance.firewall import TaskFirewall
from global_hybrid_v2.governance.router import OwnerRouter
from global_hybrid_v2.runtime.trace import TraceBus


class Dispatcher:
    def __init__(
        self,
        *,
        authority: AuthorityResolver,
        domains: dict[Owner, DomainPort],
        trace: TraceBus,
        firewall: TaskFirewall | None = None,
        router: OwnerRouter | None = None,
        effect_gate: EffectGate | None = None,
        egress: ResponseEgressValidator | None = None,
    ):
        self.authority = authority
        self.domains = domains
        self.trace = trace
        self.firewall = firewall or TaskFirewall()
        self.router = router or OwnerRouter()
        self.effect_gate = effect_gate or EffectGate()
        self.egress = egress or ResponseEgressValidator()

    def dispatch(self, request: TaskRequest):
        snapshot = self.authority.resolve()

        owner = self.router.route(request.intent)
        safe_context = self.firewall.filter(request.context, snapshot)

        contract = TaskContract(
            request_text=request.request_text,
            intent=request.intent,
            owner=owner,
            effects=request.effects,
            authority_snapshot_id=snapshot.snapshot_id,
            context=safe_context,
        )

        self.trace.emit(
            task_id=contract.task_id,
            stage="firewall",
            decision="PASS",
            owner=owner,
            metadata={"accepted_context": len(safe_context), "received_context": len(request.context)},
        )

        try:
            self.effect_gate.authorize(owner, request.effects)
        except Exception as exc:
            self.trace.emit(
                task_id=contract.task_id,
                stage="effect_gate",
                decision="DENY",
                owner=owner,
                metadata={"error": str(exc)},
            )
            raise

        self.trace.emit(
            task_id=contract.task_id,
            stage="effect_gate",
            decision="PASS",
            owner=owner,
            metadata={"effects": [effect.value for effect in request.effects]},
        )

        domain = self.domains.get(owner)
        if domain is None:
            raise RuntimeError(f"domain adapter missing: {owner.value}")

        result = self.egress.validate(domain.run(contract))

        self.trace.emit(
            task_id=contract.task_id,
            stage="response_egress",
            decision="BLOCK" if result.status == RUN_REQUIRED_RESEARCH else "PASS",
            owner=owner,
            metadata={
                "classifications": sorted(item.value for item in result.output_classifications),
                "status": result.status,
            },
        )

        self.trace.emit(
            task_id=contract.task_id,
            stage="closure",
            decision=result.status,
            owner=owner,
            metadata={"evidence": result.evidence},
        )
        return result
