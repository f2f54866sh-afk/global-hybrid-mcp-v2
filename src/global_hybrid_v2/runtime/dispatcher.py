from __future__ import annotations

from typing import Any
from uuid import uuid4

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    DomainResult,
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
RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION = (
    "RESEARCH_REPEAT_BLOCKED_NO_NEW_INFORMATION"
)
RESEARCH_RESUME_DIFFERENT_BLOCKER = "RESEARCH_RESUME_DIFFERENT_BLOCKER"


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
    ):
        self.authority = authority
        self.domains = domains
        self.trace = trace
        self.firewall = firewall or TaskFirewall()
        self.router = router or OwnerRouter()
        self.effect_gate = effect_gate or EffectGate()
        self.repeat_action_gate = repeat_action_gate or RepeatActionGate()
        self.risk_classifier = risk_classifier or TaskRiskClassifier()
        self.research_executor = research_executor or ResearchExecutor(
            UnavailableResearchPort()
        )
        self.egress = egress or ResponseEgressValidator(
            research_available=(
                self.research_executor.availability
                is ResearchProviderAvailability.CALLABLE
            )
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

        owner = self.router.route(request.intent)
        authority_entry = snapshot.entries.get(owner)
        risk_class = self.risk_classifier.classify(request)
        context_admission = self.firewall.evaluate(request.context, snapshot)
        safe_context = context_admission.admitted

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
            stage="firewall",
            decision="PASS",
            owner=owner,
            span_owner="GLOBAL",
            metadata={
                "input_contract_id": contract.contract_id,
                "accepted_context": len(safe_context),
                "received_context": len(request.context),
                "admission_receipts": [
                    receipt.model_dump(mode="json") for receipt in context_admission.receipts
                ],
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

        domain = self.domains.get(owner)
        if domain is None:
            raise RuntimeError(f"domain adapter missing: {owner.value}")

        domain_result = domain.run(contract)
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
            and self.research_executor.availability
            is ResearchProviderAvailability.UNAVAILABLE
        ):
            result = self._research_block(
                result,
                RESEARCH_PROVIDER_UNAVAILABLE,
                "no callable production research provider is configured",
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
                "failure_locus": (
                    None if result.status in {"DONE", "PASS"} else owner.value
                ),
            },
        )
        return result

    def _validate_egress(self, contract: TaskContract, result: DomainResult) -> DomainResult:
        validated = self.egress.validate(result)
        self.trace.emit(
            task_id=contract.task_id,
            stage="response_egress",
            decision=(
                "BLOCK"
                if validated.status in {RUN_REQUIRED_RESEARCH, UNKNOWN_WITH_EXACT_BLOCKER}
                else "PASS"
            ),
            owner=contract.owner,
            metadata={
                "classifications": sorted(
                    item.value for item in validated.output_classifications
                ),
                "status": validated.status,
                "evidence_admission_check": validated.evidence.get(
                    "evidence_admission_check"
                ),
                "finding_codes": validated.evidence.get("finding_codes", []),
                "defect_family": validated.evidence.get("defect_family"),
                "fix_claimed": bool(validated.evidence.get("fix_claimed", False)),
                "user_reported_recurrence": bool(
                    validated.evidence.get("user_reported_recurrence", False)
                ),
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
            if (
                self.research_executor.availability
                is not ResearchProviderAvailability.CALLABLE
            ):
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
                    "admitted_semantic_keys": [
                        item.semantic_key.value for item in admitted
                    ],
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
                            "fresh evidence admission still fails after the maximum "
                            "research attempts",
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
                        "resume validation requires a materially different research scope "
                        "or semantic key",
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
        queries = [
            f"{query_prefix} {item.value} within the bounded scope: {scope}"
            for item in required
        ]
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
                "ALTERNATE_CURRENT_SOURCE_CONFIRMATION"
                if alternate
                else "PRIMARY_CURRENT_SOURCE"
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
            decision=(
                "BLOCK" if result.status == UNKNOWN_WITH_EXACT_BLOCKER else "PASS"
            ),
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
        if not set(item.reference for item in receipt.evidence).issubset(
            set(receipt.source_references)
        ):
            return "research execution receipt source references do not cover evidence"
        return None

    @staticmethod
    def _merge_admission_receipts(
        existing: list[ResearchAdmissionReceipt],
        additional: list[ResearchAdmissionReceipt],
    ) -> list[ResearchAdmissionReceipt]:
        merged = list(existing)
        identities = {
            (item.semantic_key, item.scope, item.issued_at, item.valid_until)
            for item in existing
        }
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
