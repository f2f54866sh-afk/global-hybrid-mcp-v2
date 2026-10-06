from __future__ import annotations

from dataclasses import dataclass

from global_hybrid_v2.governance.public_claim_coverage import (
    ClaimCoveragePayloadV1,
    ClaimCoverageSegmentV1,
    evaluate_claim_coverage,
)
from global_hybrid_v2.governance.sales_final_commit import (
    REQUIRED_PRODUCT_CHECKS,
    AuthoritativeSalesTaskSnapshotV1,
    Disposition,
    ProductCheckResultV1,
    sha256_json,
    sha256_text,
)


@dataclass(frozen=True)
class BoundedFactAtomV1:
    fact_id: str
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class BoundedFactSummaryPlanV1:
    candidate: str | None
    atoms: tuple[BoundedFactAtomV1, ...] = ()
    blocker: str | None = None


class ZeroCostBoundedSalesPolicyV1:
    """Closed-world ordinary fact-summary grammar. No model calls or authority promotion."""

    @staticmethod
    def _pick(
        forms: list[str],
        *,
        prefix: str = "",
        suffix: str = "",
        require_comma: bool = False,
    ) -> str | None:
        for value in forms:
            if prefix and not value.startswith(prefix):
                continue
            if suffix and not value.endswith(suffix):
                continue
            if require_comma and "," not in value:
                continue
            return value
        if prefix or suffix or require_comma:
            return None
        return forms[0] if forms else None

    def plan(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> BoundedFactSummaryPlanV1:
        manifest = snapshot.task_bound_evidence_manifest
        if manifest is None:
            return BoundedFactSummaryPlanV1(
                candidate=None,
                blocker="EVIDENCE_MANIFEST_MISSING",
            )

        facts = {fact.fact_id: fact for fact in manifest.facts}
        required = {
            "year": ("workbench-model-year", {"suffix": "年"}),
            "make": ("workbench-make", {}),
            "model": ("workbench-model", {}),
            "color": ("workbench-color", {"suffix": "色"}),
            "mileage": (
                "workbench-mileage-km",
                {"prefix": "里程", "require_comma": True},
            ),
            "price": (
                "workbench-asking-price-twd",
                {"prefix": "目前售價", "require_comma": True},
            ),
        }

        selected: dict[str, tuple[str, str]] = {}
        for label, (fact_id, pick_args) in required.items():
            fact = facts.get(fact_id)
            if fact is None:
                return BoundedFactSummaryPlanV1(
                    candidate=None,
                    blocker=f"REQUIRED_FACT_MISSING:{fact_id}",
                )
            form = self._pick(fact.public_safe_forms, **pick_args)
            if form is None:
                return BoundedFactSummaryPlanV1(
                    candidate=None,
                    blocker=f"PUBLIC_SAFE_FORM_MISSING:{fact_id}",
                )
            selected[label] = (fact_id, form)

        request = snapshot.current_user_request
        if "里程" in request and any(token in request for token in ("售價", "價格", "開價")):
            ordered = ("make", "model", "mileage", "price")
            candidate = (
                f"{selected['make'][1]} {selected['model'][1]}，"
                f"{selected['mileage'][1]}，{selected['price'][1]}。"
            )
        elif any(token in request for token in ("藍色", "顏色", "車況")):
            ordered = ("color", "make", "model", "year", "mileage")
            candidate = (
                f"{selected['color'][1]} {selected['make'][1]} {selected['model'][1]}，"
                f"{selected['year'][1]}，{selected['mileage'][1]}。"
            )
        elif any(token in request for token in ("8891", "刊登", "介紹")):
            ordered = ("year", "make", "model", "color", "mileage", "price")
            candidate = (
                f"{selected['year'][1]} {selected['make'][1]} {selected['model'][1]}，"
                f"{selected['color'][1]}，{selected['mileage'][1]}，{selected['price'][1]}。"
            )
        else:
            return BoundedFactSummaryPlanV1(
                candidate=None,
                blocker="UNSUPPORTED_ORDINARY_TASK_SHAPE",
            )

        atoms: list[BoundedFactAtomV1] = []
        cursor = 0
        for label in ordered:
            fact_id, text = selected[label]
            start = candidate.index(text, cursor)
            end = start + len(text)
            atoms.append(
                BoundedFactAtomV1(
                    fact_id=fact_id,
                    text=text,
                    start=start,
                    end=end,
                )
            )
            cursor = end

        return BoundedFactSummaryPlanV1(
            candidate=candidate,
            atoms=tuple(atoms),
        )


class ZeroCostBoundedSalesCandidateGeneratorV1:
    """CandidateGenerator port for the bounded zero-cost N2 shadow route."""

    def __init__(self, *, policy: ZeroCostBoundedSalesPolicyV1 | None = None) -> None:
        self.policy = policy or ZeroCostBoundedSalesPolicyV1()

    def generate(self, snapshot: AuthoritativeSalesTaskSnapshotV1) -> str:
        plan = self.policy.plan(snapshot)
        return plan.candidate or ""


class ZeroCostBoundedSalesProductEvaluatorV1:
    """Typed-evidence deterministic evaluator for the same bounded grammar."""

    def __init__(self, *, policy: ZeroCostBoundedSalesPolicyV1 | None = None) -> None:
        self.policy = policy or ZeroCostBoundedSalesPolicyV1()

    @staticmethod
    def _detached_payload(candidate: str) -> ClaimCoveragePayloadV1:
        segments: list[ClaimCoverageSegmentV1] = []
        start: int | None = None
        for index, char in enumerate(candidate + "\0"):
            semantic = index < len(candidate) and char.isalnum()
            if semantic and start is None:
                start = index
            elif not semantic and start is not None:
                segments.append(
                    ClaimCoverageSegmentV1(
                        start=start,
                        end=index,
                        text=candidate[start:index],
                        kind="FACTUAL",
                        authority_fact_ids=[],
                        support=None,
                    )
                )
                start = None
        return ClaimCoveragePayloadV1(
            manifest_digest=None,
            segments=segments,
        )

    @staticmethod
    def _production_payload(
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        plan: BoundedFactSummaryPlanV1,
    ) -> ClaimCoveragePayloadV1:
        manifest = snapshot.task_bound_evidence_manifest
        if manifest is None:
            return ClaimCoveragePayloadV1(manifest_digest=None, segments=[])
        return ClaimCoveragePayloadV1(
            manifest_digest=manifest.manifest_digest,
            segments=[
                ClaimCoverageSegmentV1(
                    start=atom.start,
                    end=atom.end,
                    text=atom.text,
                    kind="FACTUAL",
                    authority_fact_ids=[atom.fact_id],
                    support="SUPPORTED",
                )
                for atom in plan.atoms
            ],
        )

    @staticmethod
    def _ref(
        *,
        check_id: str,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
        disposition: Disposition,
        detail: str,
    ) -> str:
        return "app:n2-zero-cost:" + check_id.lower() + ":" + sha256_json(
            {
                "snapshot_digest": snapshot.snapshot_digest,
                "candidate_digest": sha256_text(candidate),
                "disposition": disposition,
                "detail": detail,
            }
        )

    def _results(
        self,
        *,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
        dispositions: dict[str, Disposition],
        detail: str,
    ) -> list[ProductCheckResultV1]:
        return [
            ProductCheckResultV1(
                check_id=check_id,
                disposition=dispositions[check_id],
                result_ref=self._ref(
                    check_id=check_id,
                    snapshot=snapshot,
                    candidate=candidate,
                    disposition=dispositions[check_id],
                    detail=detail,
                ),
                snapshot_digest=snapshot.snapshot_digest,
                candidate_digest=sha256_text(candidate),
            )
            for check_id in REQUIRED_PRODUCT_CHECKS
        ]

    def evaluate(
        self,
        snapshot: AuthoritativeSalesTaskSnapshotV1,
        candidate: str,
    ) -> list[ProductCheckResultV1]:
        plan = self.policy.plan(snapshot)
        serialization: Disposition = (
            "PASS" if candidate.encode("utf-8").decode("utf-8") == candidate else "HOLD"
        )

        if plan.blocker is not None or plan.candidate is None:
            dispositions: dict[str, Disposition] = {
                check_id: "HOLD" for check_id in REQUIRED_PRODUCT_CHECKS
            }
            dispositions["PUBLIC_SERIALIZATION"] = serialization
            return self._results(
                snapshot=snapshot,
                candidate=candidate,
                dispositions=dispositions,
                detail=plan.blocker or "PLAN_UNAVAILABLE",
            )

        if candidate != plan.candidate:
            dispositions = {
                "PRODUCTION_PRODUCT": "FAIL",
                "DETACHED_PRODUCT": "PASS",
                "CONTEXT_ISOLATION": "PASS",
                "DISPOSITION_INVARIANCE": "FAIL",
                "COPY_EGRESS": "FAIL",
                "PUBLIC_SERIALIZATION": serialization,
                "PUBLIC_CLAIM_COVERAGE": "FAIL",
                "PUBLIC_ACCEPTANCE_WITNESS": "FAIL",
            }
            return self._results(
                snapshot=snapshot,
                candidate=candidate,
                dispositions=dispositions,
                detail="CANDIDATE_OUTSIDE_BOUNDED_GRAMMAR",
            )

        claim = evaluate_claim_coverage(
            candidate=candidate,
            manifest=snapshot.task_bound_evidence_manifest,
            production=self._production_payload(snapshot, plan),
            detached=self._detached_payload(candidate),
        )
        if claim.disposition != "PASS":
            dispositions = {
                "PRODUCTION_PRODUCT": claim.disposition,
                "DETACHED_PRODUCT": "PASS",
                "CONTEXT_ISOLATION": "PASS",
                "DISPOSITION_INVARIANCE": claim.disposition,
                "COPY_EGRESS": claim.disposition,
                "PUBLIC_SERIALIZATION": serialization,
                "PUBLIC_CLAIM_COVERAGE": claim.disposition,
                "PUBLIC_ACCEPTANCE_WITNESS": claim.disposition,
            }
            return self._results(
                snapshot=snapshot,
                candidate=candidate,
                dispositions=dispositions,
                detail="PUBLIC_CLAIM_COVERAGE:" + ",".join(claim.reason_codes),
            )

        dispositions = {check_id: "PASS" for check_id in REQUIRED_PRODUCT_CHECKS}
        dispositions["PUBLIC_SERIALIZATION"] = serialization
        return self._results(
            snapshot=snapshot,
            candidate=candidate,
            dispositions=dispositions,
            detail="BOUNDED_GRAMMAR_EXACT_MATCH+APPLICATION_OWNED_CLAIM_COVERAGE",
        )
