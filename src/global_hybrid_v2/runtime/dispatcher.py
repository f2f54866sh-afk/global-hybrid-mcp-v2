from __future__ import annotations

from typing import Any
from uuid import uuid4

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    DomainResult,
    LibraryAccessKind,
    LibraryAccessRequest,
    OutputClassification,
    Owner,
    ResearchAdmissionReceipt,
    ResearchEvidenceSource,
    ResearchExecutionReceipt,
    ResearchExecutionStatus,
    ResearchProviderAvailability,
    ResearchRequest,
    TaskContract,
    TaskRequest,
)
from global_hybrid_v2.domains.base import DomainPort, LibraryProjectionPort
from global_hybrid_v2.domains.sales_media import SalesMediaDomain
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.domain_contract import DomainContractGate
from global_hybrid_v2.governance.effects import EffectGate
from global_hybrid_v2.governance.egress import (
    RUN_REQUIRED_RESEARCH,
    UNKNOWN_WITH_EXACT_BLOCKER,
    ResponseEgressValidator,
)
from global_hybrid_v2.governance.firewall import TaskFirewall
from global_hybrid_v2.governance.fitness import SystemFitnessFunctions
from global_hybrid_v2.governance.library_boundary import LibraryReadWriteBoundary
from global_hybrid_v2.governance.repeat_action import (
    REPEAT_BLOCKED_NO_NEW_EVIDENCE,
    RepeatActionGate,
)
from global_hybrid_v2.governance.risk import TaskRiskClassifier
from global_hybrid_v2.governance.router import OwnerRouter
from global_hybrid_v2.research import ResearchExecutor, UnavailableResearchPort
from global_hybrid_v2.runtime.trace import TraceBus

MAX_RESEARCH_ATTEMPTS = 2
PRE_RESEARCH_EGRESS_SUPPRESSION = "PRE_RESEARCH_EGRESS_SUPPRESSION"
RESEARCH_PROVIDER_UNAVAILABLE = "RESEARCH_PROVIDER_UNAVAILABLE"
RESEARCH_PROVIDER_EXECUTION_FAILED = "RESEARCH_PROVIDER_EXECUTION_FAILED"
RESEARCH_COVERAGE_INSUFFICIENT = "RESEARCH_COVERAGE_INSUFFICIENT"
RESEARCH_RECEIPT_INVALID = "RESEARCH_RECEIPT_INVALID"
RESEARCH_MAX_ATTEMPTS_REACHED = "RESEARCH_MAX_ATTEMPTS_REACHED"
RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION = "RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION"
RESEARCH_RESUME_DIFFERENT_BLOCKER = "RESEARCH_RESUME_DIFFERENT_BLOCKER"
NOT_EXECUTED_UPSTREAM_BLOCK = "NOT_EXECUTED_UPSTREAM_BLOCK"
SNAPSHOT_COMPILATION_FAIL = "SNAPSHOT_COMPILATION_FAIL"
EXECUTION_BINDING_CONSUMPTION_FAIL = "EXECUTION_BINDING_CONSUMPTION_FAIL"
SALES_LIBRARY_PROJECTION_FIELDS = {
    "library_request_id",
    "projection",
    "contract_version",
    "source_scope",
    "evidence_role",
    "evidence_items",
    "uncertainties",
}


class _SalesConsumptionBlock(RuntimeError):
    def __init__(self, stage: str, cause: Exception):
        super().__init__(str(cause))
        self.stage = stage
        self.blocker_type = type(cause).__name__


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
        research_executor: ResearchExecutor | None = None,
        risk_classifier: TaskRiskClassifier | None = None,
        domain_contract_gate: DomainContractGate | None = None,
        library_boundary: LibraryReadWriteBoundary | None = None,
    ):
        self.authority = authority
        self.domains = domains
        self.trace = trace
        self.firewall = firewall or TaskFirewall()
        self.router = router or OwnerRouter()
        self.effect_gate = effect_gate or EffectGate()
        self.repeat_action_gate = repeat_action_gate or RepeatActionGate()
        self.risk_classifier = risk_classifier or TaskRiskClassifier()
        self.domain_contract_gate = domain_contract_gate or DomainContractGate()
        self.library_boundary = library_boundary or LibraryReadWriteBoundary()
        self.research_executor = research_executor or ResearchExecutor(UnavailableResearchPort())
        self.egress = egress or ResponseEgressValidator(
            research_available=(self.research_executor.availability is ResearchProviderAvailability.CALLABLE)
        )

    def dispatch(self, request: TaskRequest):
        task_id = str(uuid4())
        task_trace_id = self.trace.start_task(task_id)
        contract_id = str(uuid4())
        try:
            snapshot = self.authority.resolve()
        except Exception as exc:
            self.trace.emit(
                task_id=task_id,
                stage="authority_resolution",
                decision="DENY",
                span_owner="GLOBAL",
                metadata={
                    "input_contract_id": contract_id,
                    "failure_locus": "AUTHORITY",
                    "error_type": type(exc).__name__,
                },
            )
            raise

        self.trace.emit(
            task_id=task_id,
            stage="current_authority",
            decision="PASS",
            span_owner="GLOBAL",
            metadata={
                "state": "CURRENT_AUTHORITY_RESOLVED",
                "input_ref": str(getattr(self.authority, "registry_path", "resolved-snapshot")),
                "output_ref": snapshot.snapshot_id,
                "result": "PASS",
                "failure_class": None,
                "resolved_owners": [item.value for item in snapshot.entries],
            },
        )

        owner = self.router.route(request.intent)
        sales_media_task = owner is Owner.SALES_HUMAN and SalesMediaDomain.supports(request.request_text)
        authority_entry = snapshot.entries.get(owner)
        risk_class = self.risk_classifier.classify(request)
        context_admission = self.firewall.evaluate(request.context, snapshot)
        safe_context = context_admission.admitted
        self.trace.store_quarantined_evidence(
            task_id,
            context_admission.quarantined_external,
        )

        contract = TaskContract(
            task_id=task_id,
            task_trace_id=task_trace_id,
            contract_id=contract_id,
            request_text=request.request_text,
            intent=request.intent,
            owner=owner,
            effects=request.effects,
            authority_snapshot_id=snapshot.snapshot_id,
            context=safe_context,
            context_admission_receipts=context_admission.receipts,
            retry_context=request.retry_context,
            risk_class=risk_class,
        )

        self.trace.emit(
            task_id=contract.task_id,
            stage="task_contract",
            decision="PASS",
            owner=owner,
            span_owner="GLOBAL",
            metadata={
                "state": "TASK_CONTRACT_COMPILED",
                "input_ref": task_id,
                "output_ref": contract.contract_id,
                "result": "PASS",
                "failure_class": None,
                "context_count": len(safe_context),
            },
        )

        self.trace.emit(
            task_id=task_id,
            stage="owner_route",
            decision="PASS",
            owner=owner,
            span_owner="GLOBAL",
            metadata={
                "state": "OWNER_ROUTED",
                "input_ref": contract.contract_id,
                "output_ref": owner.value,
                "result": "PASS",
                "failure_class": None,
            },
        )

        self.trace.emit(
            task_id=contract.task_id,
            stage="firewall",
            decision="PASS",
            owner=owner,
            span_owner="GLOBAL",
            metadata={
                "state": "CONTEXT_ADMISSION_EVALUATED",
                "input_ref": contract.contract_id,
                "output_ref": f"{contract.contract_id}:context",
                "result": "PASS",
                "failure_class": None,
                "input_contract_id": contract.contract_id,
                "accepted_context": len(safe_context),
                "received_context": len(request.context),
                "admission_receipts": [
                    receipt.model_dump(mode="json") for receipt in context_admission.receipts
                ],
                "admitted_context_ids": [item.id for item in safe_context],
                "admitted_context_directive_free": all(
                    not TaskFirewall.contains_external_directive(item.payload) for item in safe_context
                ),
                "quarantined_external_count": len(context_admission.quarantined_external),
            },
        )

        try:
            effect_decision = self.effect_gate.authorize(owner, request.effects)
        except Exception as exc:
            self.trace.emit(
                task_id=contract.task_id,
                stage="effect_gate",
                decision="DENY",
                owner=owner,
                span_owner="GLOBAL",
                metadata={
                    "input_contract_id": contract.contract_id,
                    "error": str(exc),
                    "failure_locus": "GOVERNANCE",
                    "enforcement_point": "DISPATCHER_PRE_DOMAIN",
                },
            )
            raise

        self.trace.emit(
            task_id=contract.task_id,
            stage="effect_gate",
            decision="PASS",
            owner=owner,
            span_owner="GLOBAL",
            metadata={
                "input_contract_id": contract.contract_id,
                "effects": [effect.value for effect in request.effects],
                "policy_decision_point": effect_decision.policy_decision_point,
                "enforcement_point": effect_decision.enforcement_point,
            },
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
                metadata={
                    "input_contract_id": contract.contract_id,
                    "authority_revision": authority_entry.revision if authority_entry else None,
                    "action_class": request.intent.value,
                    "consumed_fields": [item.id for item in safe_context],
                    "output_id": f"{contract.task_id}:{result.status}",
                    "evidence_pointer": sorted(result.evidence),
                    "status": result.status,
                    "failure_locus": "GOVERNANCE",
                },
            )
            return result

        if sales_media_task:
            try:
                contract = self._compile_sales_snapshot(contract, snapshot)
            except _SalesConsumptionBlock as exc:
                return self._sales_upstream_block(
                    contract=contract,
                    authority_revision=(authority_entry.revision if authority_entry else None),
                    root_status=SNAPSHOT_COMPILATION_FAIL,
                    failed_stage=exc.stage,
                    blocker_type=exc.blocker_type,
                )
            except Exception as exc:
                return self._sales_upstream_block(
                    contract=contract,
                    authority_revision=(authority_entry.revision if authority_entry else None),
                    root_status=SNAPSHOT_COMPILATION_FAIL,
                    failed_stage="snapshot_compiled",
                    blocker_type=type(exc).__name__,
                )

        domain = self.domains.get(owner)
        if domain is None:
            raise RuntimeError(f"domain adapter missing: {owner.value}")

        if sales_media_task:
            configured = not isinstance(domain, NotConfiguredDomain)
            if not configured:
                return self._sales_upstream_block(
                    contract=contract,
                    authority_revision=(authority_entry.revision if authority_entry else None),
                    root_status=EXECUTION_BINDING_CONSUMPTION_FAIL,
                    failed_stage="sales_adapter_bound",
                    blocker_type="NotConfiguredDomain",
                )
            self.trace.emit(
                task_id=contract.task_id,
                stage="sales_adapter_bound",
                decision="PASS",
                owner=owner,
                metadata={
                    "state": "ADAPTER_CONFIGURED",
                    "input_ref": contract.contract_id,
                    "output_ref": type(domain).__name__,
                    "result": "PASS",
                    "failure_class": None,
                },
            )
            packet = contract.domain_contracts[0]
            self.trace.emit(
                task_id=contract.task_id,
                stage="sales_context_delivered",
                decision="PASS",
                owner=owner,
                metadata={
                    "state": "CONTEXT_DELIVERED",
                    "input_ref": packet.contract_id,
                    "output_ref": contract.contract_id,
                    "result": "PASS",
                    "failure_class": None,
                    "actual_consumed_context": sorted(packet.used_fields),
                },
            )

        try:
            domain_result = domain.run(contract)
        except Exception as exc:
            if sales_media_task:
                return self._sales_upstream_block(
                    contract=contract,
                    authority_revision=(authority_entry.revision if authority_entry else None),
                    root_status=EXECUTION_BINDING_CONSUMPTION_FAIL,
                    failed_stage="sales_result",
                    blocker_type=type(exc).__name__,
                )
            raise
        if sales_media_task:
            self.trace.emit(
                task_id=contract.task_id,
                stage="sales_result",
                decision="PASS",
                owner=owner,
                metadata={
                    "state": "RESULT_RETURNED",
                    "input_ref": contract.contract_id,
                    "output_ref": f"{contract.task_id}:{domain_result.status}",
                    "result": "PASS",
                    "failure_class": None,
                    "status": domain_result.status,
                },
            )
        result = self._validate_egress(contract, domain_result)
        if result.status == RUN_REQUIRED_RESEARCH:
            result = self._run_research_loop(
                contract=contract,
                domain=domain,
                initial_result=result,
                snapshot=snapshot,
            )
        elif (
            result.status == UNKNOWN_WITH_EXACT_BLOCKER
            and result.evidence.get("evidence_admission_check") == "FAIL"
            and self.research_executor.availability is ResearchProviderAvailability.UNAVAILABLE
        ):
            result = self._research_block(
                result,
                RESEARCH_PROVIDER_UNAVAILABLE,
                "no callable production research provider is configured",
            )

        if sales_media_task:
            fitness = SystemFitnessFunctions.evaluate_sales_consumption(
                snapshot=snapshot,
                contract=contract,
                result=result,
                trace=self.trace,
            )
            fitness_map = {item.name: item.passed for item in fitness.checks}
            result = result.model_copy(
                update={
                    "evidence": {
                        **result.evidence,
                        "consumption_fitness": fitness_map,
                        "consumption_fitness_pass": fitness.passed,
                    }
                }
            )
            self.trace.emit(
                task_id=contract.task_id,
                stage="fitness",
                decision="PASS" if fitness.passed else "FAIL",
                owner=owner,
                span_owner="GLOBAL",
                metadata={
                    "state": "FITNESS_EVALUATED",
                    "input_ref": contract.contract_id,
                    "output_ref": f"{contract.task_id}:fitness",
                    "result": "PASS" if fitness.passed else "FAIL",
                    "failure_class": None if fitness.passed else "CONSUMPTION_FITNESS_FAIL",
                    "checks": fitness_map,
                },
            )

        self.trace.emit(
            task_id=contract.task_id,
            stage="closure",
            decision=result.status,
            owner=owner,
            metadata={
                "state": "CLOSURE_RECORDED",
                "input_ref": contract.contract_id,
                "output_ref": f"{contract.task_id}:{result.status}",
                "result": result.status,
                "failure_class": (
                    None
                    if result.evidence.get("consumption_fitness_pass") is True
                    or result.status in {"DONE", "PASS"}
                    else owner.value
                ),
                "input_contract_id": contract.contract_id,
                "authority_revision": authority_entry.revision if authority_entry else None,
                "action_class": request.intent.value,
                "consumed_fields": [item.id for item in safe_context],
                "output_id": f"{contract.task_id}:{result.status}",
                "evidence_pointer": sorted(result.evidence),
                "status": result.status,
                "failure_locus": (
                    None
                    if result.evidence.get("consumption_fitness_pass") is True
                    or result.status in {"DONE", "PASS"}
                    else owner.value
                ),
            },
        )
        return result

    def _compile_sales_snapshot(
        self,
        contract: TaskContract,
        snapshot: AuthoritySnapshot,
    ) -> TaskContract:
        library_domain = self.domains.get(Owner.LIBRARY_FACT)
        if not isinstance(library_domain, LibraryProjectionPort):
            raise _SalesConsumptionBlock(
                "library_request",
                RuntimeError("Library projection adapter is not configured"),
            )
        request = LibraryAccessRequest(
            actor_owner=Owner.SALES_HUMAN,
            access_kind=LibraryAccessKind.READ_PROJECTION,
            task_scope=contract.request_text,
            projection="sales_media_evidence",
            required_fields=SALES_LIBRARY_PROJECTION_FIELDS,
        )
        self.trace.emit(
            task_id=contract.task_id,
            stage="library_request",
            decision="PASS",
            owner=Owner.LIBRARY_FACT,
            span_owner=Owner.SALES_HUMAN.value,
            metadata={
                "state": "LIBRARY_REQUEST_CREATED",
                "input_ref": contract.contract_id,
                "output_ref": request.request_id,
                "result": "PASS",
                "failure_class": None,
                "consumer": Owner.SALES_HUMAN.value,
                "projection": request.projection,
                "contract_version": request.contract_version,
                "required_fields": sorted(request.required_fields),
            },
        )
        try:
            boundary = self.library_boundary.authorize(request)
            if not boundary.allowed or boundary.mutation_allowed:
                raise RuntimeError("Library read projection boundary denied")
        except Exception as exc:
            raise _SalesConsumptionBlock("library_boundary", exc) from exc
        self.trace.emit(
            task_id=contract.task_id,
            stage="library_boundary",
            decision="PASS",
            owner=Owner.LIBRARY_FACT,
            span_owner=Owner.SALES_HUMAN.value,
            metadata={
                "state": "LIBRARY_READ_PROJECTION_AUTHORIZED",
                "input_ref": request.request_id,
                "output_ref": boundary.reason,
                "result": "PASS",
                "failure_class": None,
                "access_kind": boundary.access_kind.value,
                "mutation_allowed": boundary.mutation_allowed,
            },
        )
        try:
            packet = library_domain.project(
                request,
                task=contract,
                authority=snapshot,
            )
            self.domain_contract_gate.admit(
                packet,
                consumer=Owner.SALES_HUMAN,
                authority=snapshot,
            )
        except Exception as exc:
            raise _SalesConsumptionBlock("library_packet", exc) from exc
        self.trace.emit(
            task_id=contract.task_id,
            stage="library_packet",
            decision="PASS",
            owner=Owner.LIBRARY_FACT,
            metadata={
                "state": "LIBRARY_PACKET_ADMITTED",
                "input_ref": request.request_id,
                "output_ref": packet.contract_id,
                "result": "PASS",
                "failure_class": None,
                "consumer": packet.consumer_owner.value,
                "projection": packet.payload["projection"],
                "contract_version": packet.schema_version,
                "provenance": packet.provenance,
                "currentness": packet.currentness.value,
                "uncertainties": packet.payload["uncertainties"],
                "used_fields": sorted(packet.used_fields),
            },
        )
        try:
            compiled = contract.model_copy(update={"domain_contracts": [packet]})
        except Exception as exc:
            raise _SalesConsumptionBlock("snapshot_compiled", exc) from exc
        self.trace.emit(
            task_id=contract.task_id,
            stage="snapshot_compiled",
            decision="PASS",
            owner=Owner.SALES_HUMAN,
            span_owner="GLOBAL",
            metadata={
                "state": "SNAPSHOT_COMPILED",
                "input_ref": packet.contract_id,
                "output_ref": compiled.contract_id,
                "result": "PASS",
                "failure_class": None,
                "library_request_id": request.request_id,
                "library_packet_id": packet.contract_id,
                "actual_consumer_context_ids": [item.id for item in compiled.context],
            },
        )
        return compiled

    def _sales_upstream_block(
        self,
        *,
        contract: TaskContract,
        authority_revision: str | None,
        root_status: str,
        failed_stage: str,
        blocker_type: str,
    ) -> DomainResult:
        ordered = [
            "library_request",
            "library_boundary",
            "library_packet",
            "snapshot_compiled",
            "sales_adapter_bound",
            "sales_context_delivered",
            "sales_result",
            "fitness",
        ]
        failed_index = ordered.index(failed_stage)
        failure_owner = (
            Owner.LIBRARY_FACT
            if failed_stage in {"library_request", "library_boundary", "library_packet"}
            else Owner.SALES_HUMAN
        )
        self.trace.emit(
            task_id=contract.task_id,
            stage=failed_stage,
            decision="FAIL",
            owner=failure_owner,
            span_owner=(Owner.SALES_HUMAN.value if failure_owner is Owner.LIBRARY_FACT else "GLOBAL"),
            metadata={
                "state": root_status,
                "input_ref": contract.contract_id,
                "output_ref": None,
                "result": "FAIL",
                "failure_class": root_status,
                "blocker_type": blocker_type,
            },
        )
        for stage in ordered[failed_index + 1 :]:
            downstream_owner = (
                Owner.LIBRARY_FACT if stage in {"library_boundary", "library_packet"} else Owner.SALES_HUMAN
            )
            self.trace.emit(
                task_id=contract.task_id,
                stage=stage,
                decision=NOT_EXECUTED_UPSTREAM_BLOCK,
                owner=downstream_owner,
                metadata={
                    "state": NOT_EXECUTED_UPSTREAM_BLOCK,
                    "input_ref": contract.contract_id,
                    "output_ref": None,
                    "result": NOT_EXECUTED_UPSTREAM_BLOCK,
                    "failure_class": root_status,
                },
            )
        blocked = DomainResult(
            owner=Owner.SALES_HUMAN,
            status=root_status,
            output={"state": root_status, "blocker_type": blocker_type},
            evidence={
                "failure_locus": failed_stage,
                "failure_class": root_status,
            },
            output_classifications={OutputClassification.DIAGNOSIS_ONLY},
        )
        result = self._validate_egress(contract, blocked)
        self.trace.emit(
            task_id=contract.task_id,
            stage="closure",
            decision=result.status,
            owner=Owner.SALES_HUMAN,
            metadata={
                "state": "CLOSURE_RECORDED",
                "input_ref": contract.contract_id,
                "output_ref": f"{contract.task_id}:{result.status}",
                "result": result.status,
                "failure_class": root_status,
                "input_contract_id": contract.contract_id,
                "authority_revision": authority_revision,
                "action_class": contract.intent.value,
                "consumed_fields": [],
                "output_id": f"{contract.task_id}:{result.status}",
                "evidence_pointer": sorted(result.evidence),
                "status": result.status,
                "failure_locus": failed_stage,
            },
        )
        return result

    def _validate_egress(self, contract: TaskContract, result: DomainResult) -> DomainResult:
        result = result.model_copy(
            update={
                "evidence": {
                    **result.evidence,
                    "sources_callable": any(
                        item.origin.value in {"current_tool_result", "current_authority"}
                        for item in contract.context
                    ),
                },
            }
        )
        validated = self.egress.validate(result)
        self.trace.emit(
            task_id=contract.task_id,
            stage="response_egress",
            decision=(
                "BLOCK" if validated.status in {RUN_REQUIRED_RESEARCH, UNKNOWN_WITH_EXACT_BLOCKER} else "PASS"
            ),
            owner=contract.owner,
            metadata={
                "classifications": sorted(item.value for item in validated.output_classifications),
                "status": validated.status,
                "evidence_admission_check": validated.evidence.get("evidence_admission_check"),
                "finding_codes": validated.evidence.get("finding_codes", []),
                "defect_family": validated.evidence.get("defect_family"),
                "fix_claimed": bool(validated.evidence.get("fix_claimed", False)),
                "user_reported_recurrence": bool(validated.evidence.get("user_reported_recurrence", False)),
            },
        )
        return validated

    def _run_research_loop(
        self,
        *,
        contract: TaskContract,
        domain: DomainPort,
        initial_result: DomainResult,
        snapshot: AuthoritySnapshot,
    ) -> DomainResult:
        required = self._required_keys(initial_result)
        scope = (initial_result.research_scope or "").strip()
        authority_entry = snapshot.entries.get(contract.owner)
        if not required or not scope or authority_entry is None:
            return self._close_research_loop(
                contract,
                self._research_block(
                    initial_result,
                    RESEARCH_RECEIPT_INVALID,
                    "bounded research request is missing scope, semantic keys, or authority",
                ),
            )

        research_key = self._research_key(scope, required)
        self.trace.emit(
            task_id=contract.task_id,
            stage="research_required",
            decision=RUN_REQUIRED_RESEARCH,
            owner=contract.owner,
            metadata={
                "research_scope": scope,
                "required_semantic_keys": [item.value for item in required],
            },
        )
        self.trace.emit(
            task_id=contract.task_id,
            stage="pre_research_egress_suppression",
            decision="PASS",
            owner=contract.owner,
            metadata={"policy": PRE_RESEARCH_EGRESS_SUPPRESSION},
        )

        execution_receipts: list[ResearchExecutionReceipt] = []
        admission_receipts: list[ResearchAdmissionReceipt] = []
        planned_research: set[tuple[Any, ...]] = set()

        for attempt in range(1, MAX_RESEARCH_ATTEMPTS + 1):
            research_request = self._build_research_request(
                contract=contract,
                scope=scope,
                required=required,
                authority_revision=authority_entry.revision,
                attempt=attempt,
            )
            fingerprint = self._research_fingerprint(research_request)
            if fingerprint in planned_research:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        initial_result,
                        RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION,
                        "the next research attempt has no material query, source, provider, "
                        "or retrieval-strategy change",
                        execution_receipts=execution_receipts,
                        admission_receipts=admission_receipts,
                    ),
                )
            planned_research.add(fingerprint)

            self.trace.emit(
                task_id=contract.task_id,
                stage="research_request_created",
                decision="PASS",
                owner=contract.owner,
                metadata={
                    "request_id": research_request.request_id,
                    "attempt": attempt,
                    "provider": self.research_executor.provider,
                    "research_scope": scope,
                    "required_semantic_keys": [item.value for item in required],
                    "retrieval_strategy": research_request.retrieval_strategy,
                },
            )
            if self.research_executor.availability is not ResearchProviderAvailability.CALLABLE:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        initial_result,
                        RESEARCH_PROVIDER_UNAVAILABLE,
                        "no callable production research provider is configured",
                    ),
                )

            self.trace.emit(
                task_id=contract.task_id,
                stage="research_execution_started",
                decision="STARTED",
                owner=contract.owner,
                metadata={
                    "request_id": research_request.request_id,
                    "attempt": attempt,
                    "provider": self.research_executor.provider,
                },
            )
            try:
                receipt = self.research_executor.execute(research_request)
            except Exception as exc:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        initial_result,
                        RESEARCH_PROVIDER_EXECUTION_FAILED,
                        f"research provider execution failed: {type(exc).__name__}",
                        execution_receipts=execution_receipts,
                    ),
                )

            receipt_error = self._validate_execution_receipt(
                research_request,
                receipt,
            )
            if receipt_error is not None:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        initial_result,
                        RESEARCH_RECEIPT_INVALID,
                        receipt_error,
                        execution_receipts=execution_receipts,
                    ),
                )
            execution_receipts.append(receipt)
            self.trace.emit(
                task_id=contract.task_id,
                stage="research_execution_completed",
                decision=receipt.status.value,
                owner=contract.owner,
                metadata={
                    "request_id": receipt.request_id,
                    "attempt": attempt,
                    "provider": receipt.provider,
                    "queries_executed": len(receipt.queries_executed),
                    "source_references": len(receipt.source_references),
                    "coverage_complete": receipt.coverage.complete,
                },
            )
            if receipt.status is ResearchExecutionStatus.FAILED:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        initial_result,
                        RESEARCH_PROVIDER_EXECUTION_FAILED,
                        receipt.blocker or receipt.error or "research provider failed",
                        execution_receipts=execution_receipts,
                    ),
                )

            covered = set(receipt.coverage.covered_semantic_keys)
            if not receipt.coverage.complete or not set(required).issubset(covered):
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        initial_result,
                        RESEARCH_COVERAGE_INSUFFICIENT,
                        "research coverage is incomplete for the required semantic keys",
                        execution_receipts=execution_receipts,
                    ),
                )

            admitted, missing = self.egress.admit_research_evidence(
                semantic_keys=required,
                scope=scope,
                evidence=receipt.evidence,
            )
            admission_receipts.extend(admitted)
            self.trace.emit(
                task_id=contract.task_id,
                stage="research_evidence_admission",
                decision="FAIL" if missing else "PASS",
                owner=contract.owner,
                metadata={
                    "request_id": receipt.request_id,
                    "admitted_semantic_keys": [item.semantic_key.value for item in admitted],
                    "missing_semantic_keys": [item.value for item in missing],
                },
            )
            if missing:
                if attempt >= MAX_RESEARCH_ATTEMPTS:
                    return self._close_research_loop(
                        contract,
                        self._research_block(
                            initial_result,
                            RESEARCH_MAX_ATTEMPTS_REACHED,
                            "fresh evidence admission still fails after the maximum research attempts",
                            execution_receipts=execution_receipts,
                            admission_receipts=admission_receipts,
                        ),
                    )
                continue

            resumed_contract = contract.model_copy(
                update={
                    "research_admission_receipts": admission_receipts,
                    "research_execution_receipts": execution_receipts,
                }
            )
            self.trace.emit(
                task_id=contract.task_id,
                stage="task_resumed",
                decision="RESUMED",
                owner=contract.owner,
                metadata={
                    "attempt": attempt,
                    "authority_snapshot_id": contract.authority_snapshot_id,
                    "research_receipts": len(execution_receipts),
                },
            )
            resumed_raw = domain.run(resumed_contract)
            resumed_raw = resumed_raw.model_copy(
                update={
                    "research_admission_receipts": self._merge_admission_receipts(
                        resumed_raw.research_admission_receipts,
                        admission_receipts,
                    ),
                    "research_execution_receipts": [
                        *resumed_raw.research_execution_receipts,
                        *execution_receipts,
                    ],
                }
            )
            resumed = self._validate_egress(contract, resumed_raw)
            if resumed.status != RUN_REQUIRED_RESEARCH:
                return self._close_research_loop(contract, resumed)

            resumed_required = self._required_keys(resumed)
            resumed_scope = (resumed.research_scope or "").strip()
            if self._research_key(resumed_scope, resumed_required) != research_key:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        resumed,
                        RESEARCH_RESUME_DIFFERENT_BLOCKER,
                        "resume validation requires a materially different research scope or semantic key",
                        execution_receipts=execution_receipts,
                        admission_receipts=admission_receipts,
                    ),
                )
            if attempt >= MAX_RESEARCH_ATTEMPTS:
                return self._close_research_loop(
                    contract,
                    self._research_block(
                        resumed,
                        RESEARCH_MAX_ATTEMPTS_REACHED,
                        "resume validation still requires the same evidence after the "
                        "maximum research attempts",
                        execution_receipts=execution_receipts,
                        admission_receipts=admission_receipts,
                    ),
                )

        return self._close_research_loop(
            contract,
            self._research_block(
                initial_result,
                RESEARCH_MAX_ATTEMPTS_REACHED,
                "maximum research attempts reached",
                execution_receipts=execution_receipts,
                admission_receipts=admission_receipts,
            ),
        )

    def _build_research_request(
        self,
        *,
        contract: TaskContract,
        scope: str,
        required: list[OutputClassification],
        authority_revision: str,
        attempt: int,
    ) -> ResearchRequest:
        alternate = attempt > 1
        query_prefix = (
            "Find independent current-source corroboration for"
            if alternate
            else "Verify current evidence for"
        )
        queries = [f"{query_prefix} {item.value} within the bounded scope: {scope}" for item in required]
        return ResearchRequest(
            task_id=contract.task_id,
            original_owner=contract.owner,
            original_task_scope=contract.request_text,
            research_scope=scope,
            required_semantic_keys=required,
            queries=queries,
            allowed_source_classes=[
                ResearchEvidenceSource.CURRENT_CALLABLE_TOOL_RESULT,
                ResearchEvidenceSource.CURRENT_REPOSITORY_READBACK,
                ResearchEvidenceSource.CURRENT_RUNTIME_READBACK,
                ResearchEvidenceSource.CURRENT_OFFICIAL_DOCUMENTATION,
                ResearchEvidenceSource.CURRENT_WEB_SOURCE,
            ],
            authority_revision=authority_revision,
            attempt=attempt,
            retrieval_strategy=(
                "ALTERNATE_CURRENT_SOURCE_CONFIRMATION" if alternate else "PRIMARY_CURRENT_SOURCE"
            ),
        )

    def _close_research_loop(
        self,
        contract: TaskContract,
        result: DomainResult,
    ) -> DomainResult:
        self.trace.emit(
            task_id=contract.task_id,
            stage="research_loop_closed",
            decision=("BLOCK" if result.status == UNKNOWN_WITH_EXACT_BLOCKER else "PASS"),
            owner=contract.owner,
            metadata={
                "status": result.status,
                "blocker_code": result.evidence.get("blocker_code"),
            },
        )
        return result

    @staticmethod
    def _required_keys(result: DomainResult) -> list[OutputClassification]:
        if not isinstance(result.output, dict):
            return []
        raw = result.output.get("required_semantic_keys")
        if not isinstance(raw, list):
            return []
        required: list[OutputClassification] = []
        for item in raw:
            try:
                semantic_key = OutputClassification(item)
            except (TypeError, ValueError):
                return []
            if semantic_key not in required:
                required.append(semantic_key)
        return required

    @staticmethod
    def _research_key(
        scope: str,
        required: list[OutputClassification],
    ) -> tuple[str, tuple[str, ...]]:
        return scope, tuple(sorted(item.value for item in required))

    def _research_fingerprint(self, request: ResearchRequest) -> tuple[Any, ...]:
        return (
            self.research_executor.provider,
            tuple(request.queries),
            tuple(item.value for item in request.allowed_source_classes),
            request.retrieval_strategy,
        )

    def _validate_execution_receipt(
        self,
        request: ResearchRequest,
        receipt: Any,
    ) -> str | None:
        if not isinstance(receipt, ResearchExecutionReceipt):
            return "research provider did not return a structured execution receipt"
        if receipt.request_id != request.request_id:
            return "research execution receipt request_id mismatch"
        if receipt.provider != self.research_executor.provider:
            return "research execution receipt provider mismatch"
        if not set(item.reference for item in receipt.evidence).issubset(set(receipt.source_references)):
            return "research execution receipt source references do not cover evidence"
        return None

    @staticmethod
    def _merge_admission_receipts(
        existing: list[ResearchAdmissionReceipt],
        additional: list[ResearchAdmissionReceipt],
    ) -> list[ResearchAdmissionReceipt]:
        merged = list(existing)
        identities = {(item.semantic_key, item.scope, item.issued_at, item.valid_until) for item in existing}
        for item in additional:
            identity = (item.semantic_key, item.scope, item.issued_at, item.valid_until)
            if identity not in identities:
                merged.append(item)
                identities.add(identity)
        return merged

    @staticmethod
    def _research_block(
        source: DomainResult,
        blocker_code: str,
        detail: str,
        *,
        execution_receipts: list[ResearchExecutionReceipt] | None = None,
        admission_receipts: list[ResearchAdmissionReceipt] | None = None,
    ) -> DomainResult:
        return DomainResult(
            owner=source.owner,
            status=UNKNOWN_WITH_EXACT_BLOCKER,
            output={
                "state": UNKNOWN_WITH_EXACT_BLOCKER,
                "result": "UNKNOWN",
                "blocker": blocker_code,
                "detail": detail,
            },
            evidence={
                "egress_decision": "BLOCK",
                "pre_research_egress_suppression": "PASS",
                "research_loop": "BLOCK",
                "blocker_code": blocker_code,
                "reason": detail,
                "finding_codes": source.evidence.get("finding_codes", []),
            },
            output_classifications=source.output_classifications,
            research_scope=source.research_scope,
            research_admission_receipts=admission_receipts or [],
            research_execution_receipts=execution_receipts or [],
            retrieval_key=source.retrieval_key,
            retrieval_receipts=source.retrieval_receipts,
            retrieval_false_negative_evidence=source.retrieval_false_negative_evidence,
        )
