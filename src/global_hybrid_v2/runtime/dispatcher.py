from __future__ import annotations

from global_hybrid_v2.contracts import DomainResult, Owner, TaskContract, TaskRequest
from global_hybrid_v2.domains.base import DomainPort
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.effects import EffectGate
from global_hybrid_v2.governance.egress import (
    RUN_REQUIRED_RESEARCH,
    UNKNOWN_WITH_EXACT_BLOCKER,
    ResponseEgressValidator,
)
from global_hybrid_v2.governance.firewall import TaskFirewall
from global_hybrid_v2.governance.repeat_action import (
    REPEAT_BLOCKED_NO_NEW_EVIDENCE,
    RepeatActionGate,
)
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
        repeat_action_gate: RepeatActionGate | None = None,
    ):
        self.authority = authority
        self.domains = domains
        self.trace = trace
        self.firewall = firewall or TaskFirewall()
        self.router = router or OwnerRouter()
        self.effect_gate = effect_gate or EffectGate()
        self.egress = egress or ResponseEgressValidator()
        self.repeat_action_gate = repeat_action_gate or RepeatActionGate()

    def dispatch(self, request: TaskRequest):
        snapshot = self.authority.resolve()

        owner = self.router.route(request.intent)
        context_admission = self.firewall.evaluate(request.context, snapshot)
        safe_context = context_admission.admitted

        contract = TaskContract(
            request_text=request.request_text,
            intent=request.intent,
            owner=owner,
            effects=request.effects,
            authority_snapshot_id=snapshot.snapshot_id,
            context=safe_context,
            context_admission_receipts=context_admission.receipts,
            retry_context=request.retry_context,
        )

        self.trace.emit(
            task_id=contract.task_id,
            stage="firewall",
            decision="PASS",
            owner=owner,
            metadata={
                "accepted_context": len(safe_context),
                "received_context": len(request.context),
                "admission_receipts": [
                    receipt.model_dump(mode="json") for receipt in context_admission.receipts
                ],
            },
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

        repeat_admission = self.repeat_action_gate.evaluate(
            effects=request.effects,
            retry_context=request.retry_context,
        )
        self.trace.emit(
            task_id=contract.task_id,
            stage="repeat_action_gate",
            decision=repeat_admission.decision,
            owner=owner,
            metadata=repeat_admission.metadata,
        )
        if not repeat_admission.allowed:
            result = DomainResult(
                owner=owner,
                status=REPEAT_BLOCKED_NO_NEW_EVIDENCE,
                output={
                    "state": REPEAT_BLOCKED_NO_NEW_EVIDENCE,
                    "blocker": "same failed side-effect operation has no admitted material change",
                },
                evidence={"repeat_action_gate": repeat_admission.metadata},
            )
            self.trace.emit(
                task_id=contract.task_id,
                stage="closure",
                decision=result.status,
                owner=owner,
                metadata={"evidence": result.evidence},
            )
            return result

        domain = self.domains.get(owner)
        if domain is None:
            raise RuntimeError(f"domain adapter missing: {owner.value}")

        result = self.egress.validate(domain.run(contract))

        self.trace.emit(
            task_id=contract.task_id,
            stage="response_egress",
            decision=(
                "BLOCK"
                if result.status in {RUN_REQUIRED_RESEARCH, UNKNOWN_WITH_EXACT_BLOCKER}
                else "PASS"
            ),
            owner=owner,
            metadata={
                "classifications": sorted(item.value for item in result.output_classifications),
                "status": result.status,
                "evidence_admission_check": result.evidence.get("evidence_admission_check"),
                "finding_codes": result.evidence.get("finding_codes", []),
                "defect_family": result.evidence.get("defect_family"),
                "fix_claimed": bool(result.evidence.get("fix_claimed", False)),
                "user_reported_recurrence": bool(
                    result.evidence.get("user_reported_recurrence", False)
                ),
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
