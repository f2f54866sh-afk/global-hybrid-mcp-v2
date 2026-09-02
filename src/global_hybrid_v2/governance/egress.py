from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from global_hybrid_v2.contracts import (
    DomainResult,
    OutputClassification,
    ResearchAdmissionReceipt,
    ResearchAdmissionStatus,
)

RUN_REQUIRED_RESEARCH = "RUN_REQUIRED_RESEARCH"


class ResponseEgressValidator:
    REPAIR_MARKERS = (
        "REPAIR_DIRECTION",
        "SHOULD_CHANGE",
        "ARCHITECTURE_CHOICE",
        "CANDIDATE_RULE",
        "IMPLEMENTATION_PATTERN",
        "PERSISTENT_MUTATION",
    )
    RESEARCH_REQUIRED = {
        OutputClassification.PERSISTENT_REPAIR_DESIGN,
        OutputClassification.CURRENT_EXTERNAL_FACT_CLAIM,
        OutputClassification.CURRENT_PLATFORM_OR_CAPABILITY_CLAIM,
    }
    PLATFORM_PATTERN = re.compile(r"\b(chatgpt|codex|openai|github|mcp|connector)\b", re.I)
    CAPABILITY_PATTERN = re.compile(
        r"(可以|能不能|能夠|能否|支援|支持|同步|寫入|可寫|直接寫|寫|"
        r"\bwrite\b|\bwritable\b|\bsupport(?:s|ed)?\b|\bsync(?:s|ed)?\b|"
        r"\bcapabilit(?:y|ies)\b|\bavailable\b|\bavailability\b)",
        re.I,
    )
    NON_EVIDENCE_PATTERN = re.compile(
        r"(我以為|我猜|我覺得|應該|可能|\bprobably\b|\blikely\b|"
        r"\binferred from memory\b|\bmodel knowledge alone\b)",
        re.I,
    )

    def __init__(self, *, clock: Callable[[], datetime] | None = None):
        self.clock = clock or (lambda: datetime.now(UTC))

    def validate(self, result: DomainResult) -> DomainResult:
        classifications = self.classify(result)
        required = classifications & self.RESEARCH_REQUIRED
        if not required:
            return result.model_copy(update={"output_classifications": classifications})

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
            return result.model_copy(update={"output_classifications": classifications})

        blocker = self._blocker(missing, scope)
        return DomainResult(
            owner=result.owner,
            status=RUN_REQUIRED_RESEARCH,
            output={
                "state": RUN_REQUIRED_RESEARCH,
                "result": "UNKNOWN",
                "blocker": blocker,
                "required_semantic_keys": [item.value for item in missing],
            },
            evidence={
                "egress_decision": "BLOCK",
                "reason": blocker,
                "research_tool": "UNAVAILABLE",
                "non_evidence_language_detected": self._contains_non_evidence_language(result),
            },
            output_classifications=classifications,
            research_scope=result.research_scope,
            research_admission_receipts=result.research_admission_receipts,
        )

    def classify(self, result: DomainResult) -> set[OutputClassification]:
        classifications = set(result.output_classifications)
        flattened = "\n".join(self._flatten(result.output))
        normalized = re.sub(r"[\s-]+", "_", flattened.upper())
        if any(marker in normalized for marker in self.REPAIR_MARKERS):
            classifications.add(OutputClassification.PERSISTENT_REPAIR_DESIGN)
        if self.PLATFORM_PATTERN.search(flattened) and self.CAPABILITY_PATTERN.search(flattened):
            classifications.add(OutputClassification.CURRENT_PLATFORM_OR_CAPABILITY_CLAIM)
        if not classifications:
            classifications.add(OutputClassification.DIAGNOSIS_ONLY)
        return classifications

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
                cls.NON_EVIDENCE_PATTERN.search(item.reference) is None
                for item in receipt.evidence
            ):
                continue
            if receipt.issued_at.tzinfo is None or receipt.valid_until.tzinfo is None:
                continue
            if receipt.issued_at <= now < receipt.valid_until:
                return True
        return False

    @staticmethod
    def _blocker(missing: list[OutputClassification], scope: str) -> str:
        keys = ", ".join(item.value for item in missing)
        if not scope:
            return f"research_scope is missing for: {keys}"
        return (
            "fresh matching-scope RESEARCH_ADMISSION_RECEIPT=PASS is missing for: "
            f"{keys}; research execution is not configured at response egress"
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
