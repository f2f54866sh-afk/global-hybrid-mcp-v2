from __future__ import annotations

from global_hybrid_v2.contracts import Owner, TraceEvent, WitnessFinding
from global_hybrid_v2.governance.blind_spot import (
    BlindSpotScanReceipt,
    BlindSpotScanRequest,
    PreIncidentBlindSpotScan,
)
from global_hybrid_v2.governance.egress import (
    ASSUMPTION_USED_AS_EVIDENCE,
    CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
    NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE,
    RESEARCH_GATE_BYPASS,
    RETRIEVAL_FALSE_NEGATIVE,
)
from global_hybrid_v2.governance.validation import (
    DissimilarValidationGate,
    FalsificationEvidence,
    ValidationReceipt,
)


class ReadOnlyWitness:
    """Observer has no mutator/tool dependency by construction."""

    def __init__(self):
        self._claimed_fixed_defects: set[str] = set()
        self._observed_runtime: dict[str, dict[str, TraceEvent]] = {}
        self._consumption_assessments: dict[str, dict[str, bool]] = {}
        self._validation = DissimilarValidationGate()
        self._blind_spot_scan = PreIncidentBlindSpotScan()

    def consumption_assessment_for_task(self, task_id: str) -> dict[str, bool]:
        return dict(self._consumption_assessments.get(task_id, {}))

    def assess_validation(
        self,
        *,
        primary_owner: Owner,
        primary_conclusion: str,
        evidence: list[FalsificationEvidence],
    ) -> ValidationReceipt:
        return self._validation.evaluate(
            primary_owner=primary_owner,
            primary_conclusion=primary_conclusion,
            evidence=evidence,
        )

    def scan_blind_spots(self, request: BlindSpotScanRequest) -> BlindSpotScanReceipt:
        return self._blind_spot_scan.scan(request)

    def observe(self, event: TraceEvent) -> WitnessFinding | None:
        observed = self._observed_runtime.setdefault(event.task_id, {})
        observed[event.stage] = event.model_copy(deep=True)
        if event.stage == "effect_gate" and event.decision == "DENY":
            return WitnessFinding(
                task_id=event.task_id,
                severity="warning",
                code="EFFECT_DENIED",
                message="Side effect was rejected by the control plane.",
            )
        if event.stage == "response_egress":
            return self._observe_response_egress(event)
        if event.stage == "firewall":
            receipts = event.metadata.get("admission_receipts", [])
            if isinstance(receipts, list) and any(
                isinstance(item, dict)
                and item.get("directive_detected") is True
                and item.get("directive_quarantined") is not True
                for item in receipts
            ):
                return WitnessFinding(
                    task_id=event.task_id,
                    severity="error",
                    code="EXTERNAL_EVIDENCE_CONTEXT_ISOLATION_FAIL",
                    message="Detected external directive was not quarantined.",
                )
        if event.stage == "fitness" and event.decision == "FAIL":
            return WitnessFinding(
                task_id=event.task_id,
                severity="error",
                code="CONSUMPTION_FITNESS_FAIL",
                message="Runtime consumption fitness reported a failed invariant.",
            )
        if event.stage == "closure" and self._is_sales_consumption_trace(observed):
            return self._observe_sales_consumption_closure(event, observed)
        return None

    @staticmethod
    def _is_sales_consumption_trace(observed: dict[str, TraceEvent]) -> bool:
        return any(
            stage in observed
            for stage in {
                "library_request",
                "library_boundary",
                "library_packet",
                "sales_adapter_bound",
                "sales_context_delivered",
                "sales_result",
            }
        )

    def _observe_sales_consumption_closure(
        self,
        event: TraceEvent,
        observed: dict[str, TraceEvent],
    ) -> WitnessFinding | None:
        def stage(name: str) -> TraceEvent | None:
            return observed.get(name)

        def passed(name: str) -> bool:
            value = stage(name)
            return value is not None and value.decision == "PASS"

        authority = stage("current_authority")
        task_contract = stage("task_contract")
        owner_route = stage("owner_route")
        firewall = stage("firewall")
        effect_gate = stage("effect_gate")
        library_request = stage("library_request")
        library_boundary = stage("library_boundary")
        library_packet = stage("library_packet")
        snapshot = stage("snapshot_compiled")
        adapter = stage("sales_adapter_bound")
        delivered = stage("sales_context_delivered")
        domain_result = stage("sales_result")
        fitness = stage("fitness")

        receipts = (
            firewall.metadata.get("admission_receipts", [])
            if firewall is not None
            else []
        )
        directive_receipts = [
            item
            for item in receipts
            if isinstance(item, dict) and item.get("directive_detected") is True
        ]
        quarantine_count = (
            firewall.metadata.get("quarantined_external_count", 0)
            if firewall is not None
            else 0
        )
        external_isolated = (
            firewall is not None
            and firewall.metadata.get("admitted_context_directive_free") is True
            and (
                quarantine_count == 0
                or (
                    bool(directive_receipts)
                    and all(
                        item.get("directive_quarantined") is True
                        and item.get("authority_effect") == "NO_AUTHORITY_EFFECT"
                        and item.get("persistence_effect") is False
                        for item in directive_receipts
                    )
                )
            )
        )
        history_isolated = all(
            not (
                isinstance(item, dict)
                and item.get("origin") in {"memory", "history", "archive"}
                and item.get("context_class") == "NORMATIVE_AUTHORITY"
                and item.get("decision") != "QUARANTINE"
            )
            for item in receipts
        )
        fitness_checks = (
            fitness.metadata.get("checks", {}) if fitness is not None else {}
        )
        checks = {
            "CURRENT_AUTHORITY": (
                passed("current_authority")
                and authority is not None
                and {"SALES_HUMAN", "LIBRARY_FACT"}
                <= set(authority.metadata.get("resolved_owners", []))
            ),
            "TASK_AND_OWNER": (
                passed("task_contract")
                and passed("owner_route")
                and task_contract is not None
                and owner_route is not None
                and owner_route.owner is Owner.SALES_HUMAN
                and task_contract.metadata.get("output_ref")
                == owner_route.metadata.get("input_ref")
            ),
            "LIBRARY_BOUNDARY": (
                passed("library_request")
                and passed("library_boundary")
                and passed("library_packet")
                and library_request is not None
                and library_boundary is not None
                and library_packet is not None
                and library_boundary.metadata.get("input_ref")
                == library_request.metadata.get("output_ref")
                and library_boundary.metadata.get("mutation_allowed") is False
                and library_packet.metadata.get("input_ref")
                == library_request.metadata.get("output_ref")
                and library_packet.metadata.get("consumer") == "SALES_HUMAN"
            ),
            "SALES_CONTEXT_CONSUMPTION": (
                passed("snapshot_compiled")
                and passed("sales_adapter_bound")
                and passed("sales_context_delivered")
                and passed("sales_result")
                and snapshot is not None
                and adapter is not None
                and delivered is not None
                and domain_result is not None
                and library_packet is not None
                and snapshot.metadata.get("input_ref")
                == library_packet.metadata.get("output_ref")
                and adapter.metadata.get("input_ref")
                == snapshot.metadata.get("output_ref")
                and delivered.metadata.get("input_ref")
                == library_packet.metadata.get("output_ref")
                and delivered.metadata.get("output_ref")
                == snapshot.metadata.get("output_ref")
                and set(delivered.metadata.get("actual_consumed_context", []))
                == set(library_packet.metadata.get("used_fields", []))
                and domain_result.metadata.get("input_ref")
                == snapshot.metadata.get("output_ref")
            ),
            "EXTERNAL_DIRECTIVE_ISOLATION": external_isolated,
            "HISTORY_ISOLATION": history_isolated,
            "SIDE_EFFECT_BOUNDARY": (
                effect_gate is not None
                and effect_gate.decision == "PASS"
                and set(effect_gate.metadata.get("effects", []))
                <= {"read_only", "model_inference"}
            ),
            "FITNESS": (
                passed("fitness")
                and bool(fitness_checks)
                and all(value is True for value in fitness_checks.values())
            ),
            "CLOSURE_EVIDENCE": (
                event.metadata.get("input_ref")
                == (snapshot.metadata.get("output_ref") if snapshot else None)
                and event.metadata.get("output_ref")
                == (domain_result.metadata.get("output_ref") if domain_result else None)
                and {
                    "adapter_configured",
                    "adapter_called",
                    "context_delivered",
                    "result_returned",
                    "consumption_fitness",
                }
                <= set(event.metadata.get("evidence_pointer", []))
            ),
        }
        self._consumption_assessments[event.task_id] = checks
        if all(checks.values()):
            return None
        failed = sorted(name for name, passed_check in checks.items() if not passed_check)
        return WitnessFinding(
            task_id=event.task_id,
            severity="error",
            code="RUNTIME_CONSUMPTION_PROOF_INCOMPLETE",
            message=f"Independent runtime consumption checks failed: {', '.join(failed)}",
        )

    def _observe_response_egress(self, event: TraceEvent) -> WitnessFinding | None:
        defect_family = event.metadata.get("defect_family")
        if isinstance(defect_family, str) and event.metadata.get("fix_claimed") is True:
            self._claimed_fixed_defects.add(defect_family)

        if (
            isinstance(defect_family, str)
            and event.metadata.get("user_reported_recurrence") is True
            and defect_family in self._claimed_fixed_defects
        ):
            return WitnessFinding(
                task_id=event.task_id,
                severity="error",
                code="RECURRENT_DEFECT",
                message=f"Previously fixed defect recurred: {defect_family}",
            )

        finding_codes = event.metadata.get("finding_codes", [])
        if not isinstance(finding_codes, list):
            return None
        messages = {
            ASSUMPTION_USED_AS_EVIDENCE: "Unsupported assumption was used as evidence.",
            CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE: (
                "Current capability claim lacked current evidence."
            ),
            RESEARCH_GATE_BYPASS: "Required research admission was bypassed.",
            NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE: (
                "Prior-context absence was claimed without verified absence."
            ),
            RETRIEVAL_FALSE_NEGATIVE: (
                "Matching prior content was found after an earlier negative retrieval claim."
            ),
        }
        for code in (
            ASSUMPTION_USED_AS_EVIDENCE,
            CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
            RESEARCH_GATE_BYPASS,
            NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE,
            RETRIEVAL_FALSE_NEGATIVE,
        ):
            if code in finding_codes:
                return WitnessFinding(
                    task_id=event.task_id,
                    severity="error",
                    code=code,
                    message=messages[code],
                )
        return None
