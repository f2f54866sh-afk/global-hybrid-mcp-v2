from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from global_hybrid_v2.contracts import (
    DomainResult,
    OutputClassification,
    ResearchAdmissionReceipt,
    ResearchAdmissionStatus,
    ResearchEvidence,
    ResearchEvidenceSource,
    RetrievalReceipt,
    RetrievalState,
)
from global_hybrid_v2.governance.research_consumption import (
    FinalResponseObject,
    ResearchConsumptionGate,
    ResearchEvidencePacket,
)

RUN_REQUIRED_RESEARCH = "RUN_REQUIRED_RESEARCH"
UNKNOWN_WITH_EXACT_BLOCKER = "UNKNOWN_WITH_EXACT_BLOCKER"

ASSUMPTION_USED_AS_EVIDENCE = "ASSUMPTION_USED_AS_EVIDENCE"
CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE = (
    "CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE"
)
RESEARCH_GATE_BYPASS = "RESEARCH_GATE_BYPASS"
NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE = (
    "NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE"
)
RETRIEVAL_FALSE_NEGATIVE = "RETRIEVAL_FALSE_NEGATIVE"


class ResponseEgressValidator:
    REPAIR_MARKERS = (
        "REPAIR_DIRECTION",
        "SHOULD_CHANGE",
        "ARCHITECTURE_CHOICE",
        "CANDIDATE_RULE",
        "IMPLEMENTATION_PATTERN",
        "PERSISTENT_MUTATION",
    )
    CURRENT_CLAIMS = {
        OutputClassification.CURRENT_EXTERNAL_FACT,
        OutputClassification.CURRENT_PLATFORM_CAPABILITY,
        OutputClassification.CURRENT_TOOL_CAPABILITY,
    }
    CAPABILITY_CLAIMS = {
        OutputClassification.CURRENT_PLATFORM_CAPABILITY,
        OutputClassification.CURRENT_TOOL_CAPABILITY,
    }
    PLATFORM_PATTERN = re.compile(r"\b(chatgpt|codex|openai|github|mcp)\b|平台", re.I)
    TOOL_PATTERN = re.compile(
        r"\b(connector|plugin|tool|api|call|runtime)\b|工具|連接器|外掛|插件",
        re.I,
    )
    CAPABILITY_PATTERN = re.compile(
        r"(可以|能不能|能夠|能否|支援|支持|同步|寫入|可寫|直接寫|寫|有工具|"
        r"不行|不能|不支援|不支持|沒有工具|無法|沒辦法|不可用|"
        r"\bwrite\b|\bwritable\b|\bsupport(?:s|ed)?\b|\bsync(?:s|ed)?\b|"
        r"\bcapabilit(?:y|ies)\b|\bavailable\b|\bavailability\b|\b403\b|"
        r"\bcannot\b|\bcan['’]?t\b|\bunsupported\b|\bunavailable\b|"
        r"\bnot available\b|\bno access\b)",
        re.I,
    )
    ARCHITECTURE_PATTERN = re.compile(
        r"(架構|修正|修復|決策|方向|工作流|持久|"
        r"\barchitecture\b|\brepair\b|\bdecision\b|\bdirection\b|\bworkflow\b|"
        r"\bpersistent\b)",
        re.I,
    )
    NON_EVIDENCE_PATTERN = re.compile(
        r"(我以為|我猜|我覺得|我認為|模型認為|應該可以|應該|可能是|可能|"
        r"照理說|之前的假設|先前假設|先前對話假設|model memory|previous assumption|"
        r"prior conversation assumption|semantic plausibility|\bprobably\b|\blikely\b|"
        r"\bmodel thinks\b|\binferred from memory\b|\bmodel knowledge alone\b)",
        re.I,
    )
    USER_OBSERVATION_INFERENCE_PATTERN = re.compile(
        r"(平台不支援|平台不能|平台無法|沒有工具|工具不可用|"
        r"\bplatform (?:does not|doesn't) support\b|\bplatform cannot\b|"
        r"\bno (?:available )?tool\b|\btool (?:is )?unavailable\b|\bno access\b)",
        re.I,
    )
    PRIOR_CONTEXT_ABSENCE_PATTERN = re.compile(
        r"(找不到|沒有找到|以前沒有|你沒說過|沒有這條規則|沒有相關紀錄|"
        r"不存在|使用者從未說過|沒有先前指令|"
        r"\bi couldn['’]?t find\b|\bnot found\b|\bno prior rule\b|"
        r"\bno previous instruction\b|\bno record\b|\bdoes not exist\b|"
        r"\buser never said\b|\bno prior instruction\b)",
        re.I,
    )

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        research_available: bool = False,
    ):
        self.clock = clock or (lambda: datetime.now(UTC))
        self.research_available = research_available

    def validate(self, result: DomainResult) -> DomainResult:
        packet_decision = self._validate_packet_consumption(result)
        if packet_decision is not None:
            return packet_decision
        result = self._record_retrieval_false_negative(result)
        classifications = self.classify(result)
        retrieval_decision = self._validate_prior_context_absence(result, classifications)
        if retrieval_decision is not None:
            if retrieval_decision.evidence.get("negative_retrieval_egress_check") == "FAIL":
                return retrieval_decision
            result = retrieval_decision
        required = self._required_semantic_keys(classifications)
        if not required:
            return result.model_copy(
                update={
                    "evidence": {
                        **result.evidence,
                        "evidence_admission_check": "NOT_REQUIRED",
                    },
                    "output_classifications": classifications,
                }
            )

        now = self.clock()
        scope = (result.research_scope or "").strip()
        missing = [
            semantic_key
            for semantic_key in sorted(required, key=lambda item: item.value)
            if not self._has_fresh_matching_receipt(
                result.research_admission_receipts,
                semantic_key,
                scope,
                now,
            )
        ]
        if not missing:
            return result.model_copy(
                update={
                    "evidence": {
                        **result.evidence,
                        "evidence_admission_check": "PASS",
                    },
                    "output_classifications": classifications,
                }
            )

        state = RUN_REQUIRED_RESEARCH if self.research_available else UNKNOWN_WITH_EXACT_BLOCKER
        blocker = self._blocker(missing, scope, self.research_available)
        finding_codes = self._finding_codes(result, missing)
        return DomainResult(
            owner=result.owner,
            status=state,
            output={
                "state": state,
                "result": "UNKNOWN",
                "blocker": blocker,
                "required_semantic_keys": [item.value for item in missing],
            },
            evidence={
                **result.evidence,
                "egress_decision": "BLOCK",
                "evidence_admission_check": "FAIL",
                "reason": blocker,
                "research_tool": "AVAILABLE" if self.research_available else "UNAVAILABLE",
                "non_evidence_language_detected": self._contains_non_evidence_language(result),
                "finding_codes": finding_codes,
                "defect_family": result.evidence.get("defect_family"),
                "fix_claimed": bool(result.evidence.get("fix_claimed", False)),
                "user_reported_recurrence": bool(
                    result.evidence.get("user_reported_recurrence", False)
                ),
            },
            output_classifications=classifications,
            research_scope=result.research_scope,
            research_admission_receipts=result.research_admission_receipts,
            research_execution_receipts=result.research_execution_receipts,
            retrieval_key=result.retrieval_key,
            retrieval_receipts=result.retrieval_receipts,
            retrieval_false_negative_evidence=result.retrieval_false_negative_evidence,
        )

    @staticmethod
    def _validate_packet_consumption(result: DomainResult) -> DomainResult | None:
        if result.research_evidence_packet is None or result.final_response_object is None:
            return None
        try:
            packet = ResearchEvidencePacket.model_validate(result.research_evidence_packet)
            final = FinalResponseObject.model_validate(result.final_response_object)
            ResearchConsumptionGate.validate_final(packet, final)
        except ValueError as exc:
            return DomainResult(
                owner=result.owner,
                status=UNKNOWN_WITH_EXACT_BLOCKER,
                output={"state": UNKNOWN_WITH_EXACT_BLOCKER, "blocker": str(exc)},
                evidence={**result.evidence, "egress_decision": "BLOCK", "evidence_packet_check": "FAIL"},
                research_evidence_packet=result.research_evidence_packet,
                final_response_object=result.final_response_object,
            )
        return result.model_copy(update={"evidence": {**result.evidence, "evidence_packet_check": "PASS"}})

    def classify(self, result: DomainResult) -> set[OutputClassification]:
        classifications = set(result.output_classifications)
        flattened = "\n".join(self._flatten(result.output))
        normalized = re.sub(r"[\s-]+", "_", flattened.upper())
        if any(marker in normalized for marker in self.REPAIR_MARKERS):
            classifications.add(OutputClassification.PERSISTENT_REPAIR_DESIGN)

        capability_claim = self.CAPABILITY_PATTERN.search(flattened) is not None
        if capability_claim and self.TOOL_PATTERN.search(flattened):
            classifications.add(OutputClassification.CURRENT_TOOL_CAPABILITY)
        elif capability_claim and self.PLATFORM_PATTERN.search(flattened):
            classifications.add(OutputClassification.CURRENT_PLATFORM_CAPABILITY)

        current_claim = bool(classifications & self.CURRENT_CLAIMS)
        assumption_language = self.NON_EVIDENCE_PATTERN.search(flattened) is not None
        architecture_language = self.ARCHITECTURE_PATTERN.search(flattened) is not None
        if current_claim and (assumption_language or architecture_language):
            classifications.add(OutputClassification.ARCHITECTURE_AFFECTING_ASSUMPTION)

        if self.PRIOR_CONTEXT_ABSENCE_PATTERN.search(flattened) is not None:
            classifications.add(OutputClassification.PRIOR_CONTEXT_ABSENCE_CLAIM)

        if not classifications:
            classifications.add(OutputClassification.DIAGNOSIS_ONLY)
        return classifications

    def _validate_prior_context_absence(
        self,
        result: DomainResult,
        classifications: set[OutputClassification],
    ) -> DomainResult | None:
        if OutputClassification.PRIOR_CONTEXT_ABSENCE_CLAIM not in classifications:
            return None

        retrieval_key = (result.retrieval_key or "").strip()
        matching = [
            receipt
            for receipt in result.retrieval_receipts
            if retrieval_key and receipt.retrieval_key == retrieval_key
        ]
        if any(receipt.state is RetrievalState.VERIFIED_ABSENT for receipt in matching):
            return result.model_copy(
                update={
                    "evidence": {
                        **result.evidence,
                        "negative_retrieval_egress_check": "PASS",
                        "retrieval_state": RetrievalState.VERIFIED_ABSENT.value,
                    },
                    "output_classifications": classifications,
                }
            )

        retrieval_state = self._retrieval_state(matching)
        blocker = (
            "prior-context absence claim requires a matching VERIFIED_ABSENT retrieval "
            f"receipt; actual retrieval state: {retrieval_state}"
        )
        finding_codes = self._merge_finding_codes(
            result.evidence,
            [NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE],
        )
        return DomainResult(
            owner=result.owner,
            status=UNKNOWN_WITH_EXACT_BLOCKER,
            output={
                "state": UNKNOWN_WITH_EXACT_BLOCKER,
                "result": "UNKNOWN",
                "blocker": blocker,
                "retrieval_state": retrieval_state,
            },
            evidence={
                **result.evidence,
                "egress_decision": "BLOCK",
                "negative_retrieval_egress_check": "FAIL",
                "reason": blocker,
                "retrieval_state": retrieval_state,
                "finding_codes": finding_codes,
            },
            output_classifications=classifications,
            research_scope=result.research_scope,
            research_admission_receipts=result.research_admission_receipts,
            research_execution_receipts=result.research_execution_receipts,
            retrieval_key=result.retrieval_key,
            retrieval_receipts=result.retrieval_receipts,
            retrieval_false_negative_evidence=result.retrieval_false_negative_evidence,
        )

    @staticmethod
    def _retrieval_state(receipts: list[RetrievalReceipt]) -> str:
        if not receipts:
            return "NO_RECEIPT"
        states = {receipt.state for receipt in receipts}
        for state in (
            RetrievalState.SOURCE_INACCESSIBLE,
            RetrievalState.COVERAGE_INCOMPLETE,
            RetrievalState.NOT_RETRIEVED,
            RetrievalState.FOUND,
        ):
            if state in states:
                return state.value
        return "NO_RECEIPT"

    @classmethod
    def _record_retrieval_false_negative(cls, result: DomainResult) -> DomainResult:
        confirmed = [
            item
            for item in result.retrieval_false_negative_evidence
            if item.prior_negative_claim and item.later_matching_content_found
        ]
        if not confirmed:
            return result
        return result.model_copy(
            update={
                "evidence": {
                    **result.evidence,
                    "retrieval_false_negative": [
                        {
                            "retrieval_key": item.retrieval_key,
                            "reason": item.reason.value,
                        }
                        for item in confirmed
                    ],
                    "finding_codes": cls._merge_finding_codes(
                        result.evidence,
                        [RETRIEVAL_FALSE_NEGATIVE],
                    ),
                }
            }
        )

    @staticmethod
    def _merge_finding_codes(evidence: dict[str, Any], additional: list[str]) -> list[str]:
        existing = evidence.get("finding_codes", [])
        codes = list(existing) if isinstance(existing, list) else []
        for code in additional:
            if code not in codes:
                codes.append(code)
        return codes

    @classmethod
    def _required_semantic_keys(
        cls,
        classifications: set[OutputClassification],
    ) -> set[OutputClassification]:
        required: set[OutputClassification] = set()
        if OutputClassification.PERSISTENT_REPAIR_DESIGN in classifications:
            required.add(OutputClassification.PERSISTENT_REPAIR_DESIGN)

        required.update(classifications & cls.CAPABILITY_CLAIMS)

        current_claims = classifications & cls.CURRENT_CLAIMS
        architecture_affecting = bool(
            classifications
            & {
                OutputClassification.ARCHITECTURE_AFFECTING_ASSUMPTION,
                OutputClassification.PERSISTENT_REPAIR_DESIGN,
            }
        )
        if architecture_affecting:
            required.update(current_claims)
        if (
            OutputClassification.ARCHITECTURE_AFFECTING_ASSUMPTION in classifications
            and not current_claims
        ):
            required.add(OutputClassification.ARCHITECTURE_AFFECTING_ASSUMPTION)
        return required

    @classmethod
    def _has_fresh_matching_receipt(
        cls,
        receipts: list[ResearchAdmissionReceipt],
        semantic_key: OutputClassification,
        scope: str,
        now: datetime,
    ) -> bool:
        if not scope or now.tzinfo is None:
            return False
        for receipt in receipts:
            if receipt.status is not ResearchAdmissionStatus.PASS:
                continue
            if receipt.semantic_key is not semantic_key or receipt.scope != scope:
                continue
            if not any(
                cls._admissible_evidence(item, semantic_key)
                for item in receipt.evidence
            ):
                continue
            if receipt.issued_at.tzinfo is None or receipt.valid_until.tzinfo is None:
                continue
            if receipt.issued_at <= now < receipt.valid_until:
                return True
        return False

    def admit_research_evidence(
        self,
        *,
        semantic_keys: list[OutputClassification],
        scope: str,
        evidence: list[ResearchEvidence],
        valid_for: timedelta = timedelta(minutes=15),
    ) -> tuple[list[ResearchAdmissionReceipt], list[OutputClassification]]:
        now = self.clock()
        admitted: list[ResearchAdmissionReceipt] = []
        missing: list[OutputClassification] = []
        if not scope or now.tzinfo is None or valid_for <= timedelta(0):
            return admitted, list(semantic_keys)

        for semantic_key in semantic_keys:
            matching = [
                item for item in evidence if self._admissible_evidence(item, semantic_key)
            ]
            if not matching:
                missing.append(semantic_key)
                continue
            admitted.append(
                ResearchAdmissionReceipt(
                    status=ResearchAdmissionStatus.PASS,
                    semantic_key=semantic_key,
                    scope=scope,
                    issued_at=now,
                    valid_until=now + valid_for,
                    evidence=matching,
                )
            )
        return admitted, missing

    @classmethod
    def _admissible_evidence(
        cls,
        evidence: ResearchEvidence,
        semantic_key: OutputClassification,
    ) -> bool:
        if evidence.source not in set(ResearchEvidenceSource):
            return False
        if cls.NON_EVIDENCE_PATTERN.search(evidence.reference) is not None:
            return False
        if cls.NON_EVIDENCE_PATTERN.search(evidence.observed_result) is not None:
            return False
        return not (
            evidence.source is ResearchEvidenceSource.CURRENT_USER_PROVIDED_OBSERVATION
            and semantic_key in cls.CAPABILITY_CLAIMS
            and cls.USER_OBSERVATION_INFERENCE_PATTERN.search(evidence.observed_result)
            is not None
        )

    @classmethod
    def _finding_codes(
        cls,
        result: DomainResult,
        missing: list[OutputClassification],
    ) -> list[str]:
        additional = [RESEARCH_GATE_BYPASS]
        if cls._contains_non_evidence_language(result):
            additional.insert(0, ASSUMPTION_USED_AS_EVIDENCE)
        if set(missing) & cls.CAPABILITY_CLAIMS:
            additional.insert(0, CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE)
        return cls._merge_finding_codes(result.evidence, additional)

    @staticmethod
    def _blocker(
        missing: list[OutputClassification],
        scope: str,
        research_available: bool,
    ) -> str:
        keys = ", ".join(item.value for item in missing)
        if not scope:
            return f"research_scope is missing for: {keys}"
        if research_available:
            return (
                "fresh matching-scope evidence admission is missing for: "
                f"{keys}; run required current research and re-evaluate"
            )
        return (
            "fresh matching-scope evidence admission is missing for: "
            f"{keys}; no current evidence source is available"
        )

    @classmethod
    def _flatten(cls, value: Any) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield str(key)
                yield from cls._flatten(item)
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                yield from cls._flatten(item)
        elif value is not None:
            yield str(value)

    @classmethod
    def _contains_non_evidence_language(cls, result: DomainResult) -> bool:
        text = "\n".join(cls._flatten((result.output, result.evidence)))
        return cls.NON_EVIDENCE_PATTERN.search(text) is not None
