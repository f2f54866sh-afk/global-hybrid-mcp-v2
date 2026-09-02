import json
from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.contracts import (
    AuthoritySnapshot,
    DomainResult,
    Intent,
    OutputClassification,
    Owner,
    ResearchAdmissionReceipt,
    ResearchAdmissionStatus,
    ResearchEvidence,
    ResearchEvidenceSource,
    TaskContract,
    TaskRequest,
)
from global_hybrid_v2.governance.authority import AuthorityResolver
from global_hybrid_v2.governance.egress import (
    ASSUMPTION_USED_AS_EVIDENCE,
    CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
    RESEARCH_GATE_BYPASS,
    RUN_REQUIRED_RESEARCH,
    UNKNOWN_WITH_EXACT_BLOCKER,
    ResponseEgressValidator,
)
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
SCOPE = "current GitHub write capability for architecture workflow"


def _receipt(
    *,
    semantic_key: OutputClassification,
    scope: str = SCOPE,
    source: ResearchEvidenceSource = ResearchEvidenceSource.CURRENT_OFFICIAL_DOCUMENTATION,
    reference: str = "official-current-source:capability",
    observed_result: str = "Current source was read successfully.",
    issued_at: datetime = NOW - timedelta(minutes=10),
    valid_until: datetime = NOW + timedelta(minutes=50),
) -> ResearchAdmissionReceipt:
    return ResearchAdmissionReceipt(
        status=ResearchAdmissionStatus.PASS,
        semantic_key=semantic_key,
        scope=scope,
        issued_at=issued_at,
        valid_until=valid_until,
        evidence=[
            ResearchEvidence(
                source=source,
                reference=reference,
                observed_result=observed_result,
            )
        ],
    )


def _validator(*, research_available: bool = True) -> ResponseEgressValidator:
    return ResponseEgressValidator(
        clock=lambda: NOW,
        research_available=research_available,
    )


def test_case_a_chatgpt_github_assumption_blocks_architecture_decision():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output=(
            "我以為 ChatGPT 可以直接寫 GitHub，因此 "
            "ARCHITECTURE_CHOICE 是依賴直接寫入。"
        ),
        research_scope=SCOPE,
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["result"] == "UNKNOWN"
    assert "依賴直接寫入" not in str(validated.output)
    assert set(validated.output["required_semantic_keys"]) == {
        "CURRENT_PLATFORM_CAPABILITY",
        "PERSISTENT_REPAIR_DESIGN",
    }


def test_case_b_chatgpt_codex_sync_assumption_is_blocked():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="模型認為 ChatGPT 與 Codex 已同步，workflow 可以依賴這個能力。",
        research_scope="current ChatGPT and Codex synchronization capability",
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["required_semantic_keys"] == ["CURRENT_PLATFORM_CAPABILITY"]
    assert CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE in validated.evidence[
        "finding_codes"
    ]


def test_case_c_current_github_403_overrides_prior_write_assumption():
    scope = "current GitHub write call outcome for architecture"
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output=(
            "Current GitHub write call returned 403; the architecture decision must not assume "
            "direct write availability."
        ),
        research_scope=scope,
        research_admission_receipts=[
            _receipt(
                semantic_key=OutputClassification.CURRENT_TOOL_CAPABILITY,
                scope=scope,
                source=ResearchEvidenceSource.CURRENT_CALLABLE_TOOL_RESULT,
                reference="github-write-call:request-42",
                observed_result="HTTP 403 Forbidden",
            )
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert "403" in validated.output
    assert OutputClassification.CURRENT_TOOL_CAPABILITY in validated.output_classifications


def test_case_d_fresh_official_evidence_allows_platform_claim():
    scope = "current ChatGPT GitHub write capability for architecture"
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output=(
            "Current ChatGPT GitHub write capability affects the architecture decision: "
            "direct write is unavailable."
        ),
        research_scope=scope,
        research_admission_receipts=[
            _receipt(
                semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
                scope=scope,
                observed_result="Official current documentation says direct write is unavailable.",
            )
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert OutputClassification.CURRENT_PLATFORM_CAPABILITY in validated.output_classifications


def test_case_e_model_confidence_is_not_admissible_evidence():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="我以為 ChatGPT 可以直接寫 GitHub，probably，architecture 可以依賴它。",
        research_scope=SCOPE,
        research_admission_receipts=[
            _receipt(
                semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
                reference="model memory",
                observed_result="likely; model knowledge alone",
            )
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert ASSUMPTION_USED_AS_EVIDENCE in validated.evidence["finding_codes"]
    assert RESEARCH_GATE_BYPASS in validated.evidence["finding_codes"]


def test_case_f_diagnosis_only_is_not_forced_to_research():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="Diagnosis: the closure path omitted deterministic validation.",
        output_classifications={OutputClassification.DIAGNOSIS_ONLY},
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert validated.output == result.output
    assert validated.research_admission_receipts == []


def test_current_external_fact_without_architecture_impact_is_not_overblocked():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="A current low-risk observation for this one-time response.",
        output_classifications={OutputClassification.CURRENT_EXTERNAL_FACT},
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"


def test_no_available_evidence_source_returns_unknown_with_exact_blocker():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="我以為 ChatGPT 可以直接寫 GitHub，architecture 應依賴它。",
        research_scope=SCOPE,
    )

    validated = _validator(research_available=False).validate(result)

    assert validated.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert validated.output["state"] == UNKNOWN_WITH_EXACT_BLOCKER
    assert "no current evidence source is available" in validated.output["blocker"]


@pytest.mark.parametrize(
    "receipt",
    [
        _receipt(
            semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
            issued_at=NOW - timedelta(hours=2),
            valid_until=NOW - timedelta(hours=1),
        ),
        _receipt(
            semantic_key=OutputClassification.CURRENT_TOOL_CAPABILITY,
        ),
        _receipt(
            semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
            scope="different architecture scope",
        ),
    ],
    ids=["stale", "wrong-semantic-key", "wrong-scope"],
)
def test_nonmatching_current_evidence_is_blocked(receipt):
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="我以為 ChatGPT 可以直接寫 GitHub，architecture 應依賴它。",
        research_scope=SCOPE,
        research_admission_receipts=[receipt],
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["required_semantic_keys"] == ["CURRENT_PLATFORM_CAPABILITY"]


def test_fresh_matching_receipt_allows_persistent_repair_design():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output={"IMPLEMENTATION_PATTERN": "Use the existing closure consumption point."},
        research_scope=SCOPE,
        research_admission_receipts=[
            _receipt(semantic_key=OutputClassification.PERSISTENT_REPAIR_DESIGN)
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert validated.output_classifications == {
        OutputClassification.PERSISTENT_REPAIR_DESIGN
    }


class _StaticAuthority(AuthorityResolver):
    def __init__(self):
        pass

    def resolve(self) -> AuthoritySnapshot:
        return AuthoritySnapshot(entries={})


class _AssumptionDomain:
    def run(self, contract: TaskContract) -> DomainResult:
        del contract
        return DomainResult(
            owner=Owner.GLOBAL,
            status="READY",
            output="我以為 ChatGPT 可以直接寫 GitHub，architecture 應依賴它。",
            research_scope=SCOPE,
        )


def test_dispatcher_enforces_evidence_admission_before_closure(capsys):
    dispatcher = Dispatcher(
        authority=_StaticAuthority(),
        domains={Owner.GLOBAL: _AssumptionDomain()},
        trace=TraceBus(),
        egress=_validator(),
    )

    result = dispatcher.dispatch(TaskRequest(request_text="repair architecture", intent=Intent.GOVERNANCE))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert result.status == RUN_REQUIRED_RESEARCH
    assert [event["stage"] for event in events[-2:]] == ["response_egress", "closure"]
    assert events[-2]["decision"] == "BLOCK"
    assert CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE in events[-2]["metadata"][
        "finding_codes"
    ]
    assert events[-1]["decision"] == RUN_REQUIRED_RESEARCH
