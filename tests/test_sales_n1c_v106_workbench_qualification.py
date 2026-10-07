from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from global_hybrid_v2.adapters.workbench_evidence import (
    WorkbenchEvidenceMaterializerV1,
    WorkbenchPublicEvidenceFactV1,
    WorkbenchPublicFactPolicyV1,
    WorkbenchVehicleEvidenceProjectionV1,
)
from global_hybrid_v2.governance.public_claim_coverage import (
    ClaimCoveragePayloadV1,
    ClaimCoverageSegmentV1,
    evaluate_claim_coverage,
)
from global_hybrid_v2.governance.sales_final_commit import (
    REQUIRED_PRODUCT_CHECKS,
    FinalOutputCommitGateV1,
    ProductCheckResultV1,
    sha256_text,
)
from global_hybrid_v2.sales_controlled_service import ControlledSalesServiceV1

NOW = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
POLICY = "RD-20261002-025_N1C_V106_WORKBENCH_QUALIFICATION"
PRODUCER = "controlled-sales-app-v1"
RUNTIME = "n1c-v106-workbench-qualification"

FILE_ID = "1OfUZ_rh94sdXdTZMjMrKj8IjHgEBUFua"
SHA = "2444595f11c593bf38ea922852540540aafcbc2df99851ba975f142dfc2c2ca1"
MTIME = "2026-10-05T11:13:16.855Z"
VEHICLE = "VIN:WVGZZZ5NZMW539101"

V106_INITIAL_FAIL = (
    "MST進氣＋BILSTEIN B8，這台R有東西可以看\n"
    "如果你在意 Tiguan R 現車已經有哪些配備與改裝，這台重點很直接："
    "MST Performance 進氣、BILSTEIN B8 系列避震，改裝內容不是一句「有改」帶過。\n"
    "車內也有日常會用到的東西：全景天窗、Digital Cockpit 數位儀表、"
    "駕駛座電動記憶、App-Connect。R 方向盤＋換檔撥片、四出尾管，"
    "則把 Tiguan R 的辨識度留得很完整。\n"
    "所以這台不是靠規格表撐場。你在意現車到底有什麼，這台就一項一項給你看。"
)
V106_REPAIRED_PASS = (
    "找 MST＋BILSTEIN B8 的 Tiguan R？這台可以直接看。\n"
    "如果你找的是已經有 MST Performance 進氣、BILSTEIN B8 避震的 Tiguan R，"
    "這台可以直接列入比較名單。\n"
    "條件合不合你的胃口，看實車最直接。"
)

INITIAL_FACT_ATOMS = [
    ("MST進氣", "tiguan-mst-intake"),
    ("BILSTEIN B8", "tiguan-bilstein-b8"),
    ("Tiguan R", "workbench-model"),
    ("MST Performance 進氣", "tiguan-mst-intake"),
    ("BILSTEIN B8 系列避震", "tiguan-bilstein-b8"),
    ("全景天窗", "tiguan-panoramic-roof"),
    ("Digital Cockpit 數位儀表", "tiguan-digital-cockpit"),
    ("駕駛座電動記憶", "tiguan-driver-memory"),
    ("App-Connect", "tiguan-app-connect"),
    ("R 方向盤", "tiguan-r-steering"),
    ("換檔撥片", "tiguan-paddles"),
    ("四出尾管", "tiguan-quad-exhaust"),
    ("Tiguan R", "workbench-model"),
]
REPAIRED_FACT_ATOMS = [
    ("MST", "tiguan-mst-intake"),
    ("BILSTEIN B8", "tiguan-bilstein-b8"),
    ("Tiguan R", "workbench-model"),
    ("MST Performance 進氣", "tiguan-mst-intake"),
    ("BILSTEIN B8 避震", "tiguan-bilstein-b8"),
    ("Tiguan R", "workbench-model"),
]


class FixedGenerator:
    def __init__(self, candidate: str) -> None:
        self.candidate = candidate

    def generate(self, snapshot) -> str:
        del snapshot
        return self.candidate


def public_fact(
    fact_id: str,
    source_field: str,
    statement: str,
    public_safe_forms: list[str],
    *,
    provenance: str = "WORKBENCH",
) -> WorkbenchPublicEvidenceFactV1:
    return WorkbenchPublicEvidenceFactV1(
        fact_id=fact_id,
        source_field=source_field,
        statement=statement,
        public_safe_forms=public_safe_forms,
        provenance=provenance,
    )


def projection() -> WorkbenchVehicleEvidenceProjectionV1:
    return WorkbenchVehicleEvidenceProjectionV1(
        source_file_id=FILE_ID,
        source_modified_time=MTIME,
        source_sha256=SHA,
        source_row=13,
        source_observation_id="SRC-ROW-13@20260925T0808Z",
        vehicle_instance_id=VEHICLE,
        instance_state="INSTANCE_ANCHORED_BINDING / PARTIAL_VERIFIED_VEHICLE_RECORD",
        company_source_state="CURRENT_MATCHED",
        company_source_row_current=13,
        model_year=2021,
        make="VW",
        model="TIGUAN R",
        color="藍",
        mileage_km=99764,
        asking_price_twd=None,
        asking_price_disclosure_state=None,
        public_evidence_facts=[
            public_fact(
                "tiguan-mst-intake",
                "改裝狀態:MST Performance 進氣",
                "MST Performance 進氣",
                ["MST", "MST進氣", "MST Performance 進氣"],
            ),
            public_fact(
                "tiguan-bilstein-b8",
                "改裝狀態:BILSTEIN B8",
                "BILSTEIN B8 前懸吊避震器/支柱",
                ["BILSTEIN B8", "BILSTEIN B8 避震", "BILSTEIN B8 前避震", "BILSTEIN B8 系列避震"],
                provenance="DIRECT_USER",
            ),
            public_fact(
                "tiguan-panoramic-roof",
                "實際配備狀態:全景天窗",
                "全景天窗",
                ["全景天窗"],
            ),
            public_fact(
                "tiguan-digital-cockpit",
                "實際配備狀態:Digital Cockpit數位儀表",
                "Digital Cockpit 數位儀表",
                ["Digital Cockpit 數位儀表"],
            ),
            public_fact(
                "tiguan-driver-memory",
                "實際配備狀態:駕駛座記憶按鍵",
                "駕駛座電動記憶",
                ["駕駛座電動記憶"],
            ),
            public_fact(
                "tiguan-app-connect",
                "實際配備狀態:App-Connect介面",
                "App-Connect",
                ["App-Connect"],
            ),
            public_fact(
                "tiguan-r-steering",
                "實際配備狀態:R方向盤",
                "R 方向盤",
                ["R 方向盤"],
            ),
            public_fact(
                "tiguan-paddles",
                "實際配備狀態:換檔撥片",
                "換檔撥片",
                ["換檔撥片"],
            ),
            public_fact(
                "tiguan-quad-exhaust",
                "實際配備狀態:四出尾管",
                "四出尾管",
                ["四出尾管"],
            ),
        ],
    )


def policy() -> WorkbenchPublicFactPolicyV1:
    return WorkbenchPublicFactPolicyV1(
        public_fields={"model_year", "make", "model", "color", "mileage_km"},
        allowed_price_disclosure_states=set(),
    )


def coverage_payload(
    candidate: str,
    atoms: list[tuple[str, str]],
    *,
    manifest_digest: str | None,
    production: bool,
) -> ClaimCoveragePayloadV1:
    segments: list[ClaimCoverageSegmentV1] = []
    cursor = 0
    for text, fact_id in atoms:
        start = candidate.index(text, cursor)
        if start > cursor:
            segments.append(
                ClaimCoverageSegmentV1(
                    start=cursor,
                    end=start,
                    text=candidate[cursor:start],
                    kind="NON_FACTUAL",
                    authority_fact_ids=[],
                    support="NOT_APPLICABLE",
                )
            )
        end = start + len(text)
        segments.append(
            ClaimCoverageSegmentV1(
                start=start,
                end=end,
                text=text,
                kind="FACTUAL",
                authority_fact_ids=[fact_id] if production else [],
                support="SUPPORTED" if production else None,
            )
        )
        cursor = end
    if cursor < len(candidate):
        segments.append(
            ClaimCoverageSegmentV1(
                start=cursor,
                end=len(candidate),
                text=candidate[cursor:],
                kind="NON_FACTUAL",
                authority_fact_ids=[],
                support="NOT_APPLICABLE",
            )
        )
    return ClaimCoveragePayloadV1(
        manifest_digest=manifest_digest if production else None,
        segments=segments,
    )


class V106WholeProductFixtureEvaluator:
    def __init__(self) -> None:
        self.last_claim_disposition: str | None = None
        self.last_manifest_fact_ids: set[str] = set()

    def evaluate(self, snapshot, candidate):
        manifest = snapshot.task_bound_evidence_manifest
        if manifest is None:
            self.last_claim_disposition = "HOLD"
            return self._rows(snapshot, candidate, {check_id: "HOLD" for check_id in REQUIRED_PRODUCT_CHECKS})

        self.last_manifest_fact_ids = {fact.fact_id for fact in manifest.facts}
        if candidate == V106_INITIAL_FAIL:
            atoms = INITIAL_FACT_ATOMS
            composition = "FAIL"
        elif candidate == V106_REPAIRED_PASS:
            atoms = REPAIRED_FACT_ATOMS
            composition = "PASS"
        else:
            self.last_claim_disposition = "HOLD"
            return self._rows(snapshot, candidate, {check_id: "HOLD" for check_id in REQUIRED_PRODUCT_CHECKS})

        claim = evaluate_claim_coverage(
            candidate=candidate,
            manifest=manifest,
            production=coverage_payload(
                candidate,
                atoms,
                manifest_digest=manifest.manifest_digest,
                production=True,
            ),
            detached=coverage_payload(
                candidate,
                atoms,
                manifest_digest=None,
                production=False,
            ),
        )
        self.last_claim_disposition = claim.disposition

        dispositions = {check_id: "PASS" for check_id in REQUIRED_PRODUCT_CHECKS}
        dispositions["PUBLIC_CLAIM_COVERAGE"] = claim.disposition
        if composition == "FAIL":
            dispositions["PRODUCTION_PRODUCT"] = "FAIL"
            dispositions["DETACHED_PRODUCT"] = "FAIL"
            dispositions["COPY_EGRESS"] = "FAIL"
            dispositions["PUBLIC_ACCEPTANCE_WITNESS"] = "FAIL"
        elif claim.disposition != "PASS":
            dispositions["PUBLIC_ACCEPTANCE_WITNESS"] = claim.disposition

        return self._rows(snapshot, candidate, dispositions, claim.coverage_digest)

    @staticmethod
    def _rows(snapshot, candidate, dispositions, detail="no-manifest"):
        digest = sha256_text(candidate)
        return [
            ProductCheckResultV1(
                check_id=check_id,
                disposition=dispositions[check_id],
                result_ref=f"n1c:v106:{check_id.lower()}:{detail}",
                snapshot_digest=snapshot.snapshot_digest,
                candidate_digest=digest,
            )
            for check_id in REQUIRED_PRODUCT_CHECKS
        ]


class V106FixtureMaterializer(WorkbenchEvidenceMaterializerV1):
    def _facts(self):
        facts = super()._facts()
        for fact in facts:
            if fact.fact_id == "workbench-model":
                fact.public_safe_forms.append("Tiguan R")
        return facts


def service(candidate: str, evaluator: V106WholeProductFixtureEvaluator) -> ControlledSalesServiceV1:
    p = projection()
    return ControlledSalesServiceV1(
        candidate_generator=FixedGenerator(candidate),
        product_evaluator=evaluator,
        commit_gate=FinalOutputCommitGateV1(
            producer_id=PRODUCER,
            policy_ref=POLICY,
            runtime_commit=RUNTIME,
            now=lambda: NOW,
        ),
        producer_id=PRODUCER,
        policy_ref=POLICY,
        global_authority_revision="GLOBAL-current",
        sales_authority_revision="SALES-V106-current",
        library_authority_revision="LIBRARY-current",
        real_car_authority_revision="REAL_CAR-current",
        evidence_materializer=V106FixtureMaterializer(
            projection=p,
            policy=policy(),
        ),
        now=lambda: NOW,
        id_factory=lambda: "task-v106-n1c",
    )


def run(candidate: str, *, workbench_sha256: str = SHA):
    evaluator = V106WholeProductFixtureEvaluator()
    p = projection()
    outcome = service(candidate, evaluator).handle(
        current_user_request="幫我寫這台 2021 VW Tiguan R 的 8891 副標題跟特色說明。直接給可刊登版本。",
        conversation_or_session_id="n1c-v106-qualification",
        task_class="8891_COPY",
        target_surface="8891",
        direct_user_hard_requirements=[],
        vehicle_instance_id=VEHICLE,
        workbench_file_id=FILE_ID,
        workbench_version=MTIME,
        workbench_sha256=workbench_sha256,
        evidence_refs=[p.evidence_ref],
        persistence_required=False,
    )
    return evaluator, outcome


def test_v106_initial_truth_pass_but_whole_product_fail_is_withheld():
    evaluator, outcome = run(V106_INITIAL_FAIL)
    assert evaluator.last_claim_disposition == "PASS"
    assert outcome.public_output is None
    assert outcome.receipt.aggregate_product_disposition == "FAIL"
    assert outcome.receipt.final_output_commit == "FAIL"
    assert outcome.receipt.public_output_digest is None


def test_v106_repaired_exact_candidate_passes_same_controlled_path():
    evaluator, outcome = run(V106_REPAIRED_PASS)
    assert evaluator.last_claim_disposition == "PASS"
    assert outcome.public_output == V106_REPAIRED_PASS
    assert outcome.receipt.aggregate_product_disposition == "PASS"
    assert outcome.receipt.final_output_commit == "PASS"
    assert outcome.receipt.public_output_digest == sha256_text(V106_REPAIRED_PASS)


def test_verified_extra_equipment_does_not_need_to_appear_in_repaired_candidate():
    evaluator, outcome = run(V106_REPAIRED_PASS)
    assert {
        "tiguan-panoramic-roof",
        "tiguan-digital-cockpit",
        "tiguan-driver-memory",
        "tiguan-app-connect",
        "tiguan-r-steering",
        "tiguan-paddles",
        "tiguan-quad-exhaust",
    }.issubset(evaluator.last_manifest_fact_ids)
    assert "全景天窗" not in outcome.public_output
    assert "Digital Cockpit" not in outcome.public_output
    assert "App-Connect" not in outcome.public_output


def test_stale_workbench_fingerprint_holds_before_public_output():
    evaluator, outcome = run(V106_REPAIRED_PASS, workbench_sha256="0" * 64)
    assert evaluator.last_claim_disposition == "HOLD"
    assert outcome.public_output is None
    assert outcome.receipt.aggregate_product_disposition == "HOLD"
    assert outcome.receipt.final_output_commit == "HOLD"


def test_n1c_qualification_does_not_wire_n2_or_natural_mcp_egress():
    mcp_source = Path("src/global_hybrid_v2/adapters/mcp_server.py").read_text(encoding="utf-8")
    assert "ZeroCostBoundedSalesCandidateGeneratorV1" not in mcp_source
    assert "ZeroCostBoundedSalesProductEvaluatorV1" not in mcp_source
    assert "WorkbenchEvidenceMaterializerV1" not in mcp_source
