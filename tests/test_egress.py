import json
from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
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
from global_hybrid_v2.governance.research_consumption import (
    ActionPlan,
    FinalResponseObject,
    ResearchEvidencePacket,
    TurnContract,
)
from global_hybrid_v2.runtime.dispatcher import RESEARCH_PROVIDER_UNAVAILABLE, Dispatcher
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


def _full_repair_packet(*, entered: bool, bypass: bool) -> DomainResult:
    task_id = "task-repair"
    packet = ResearchEvidencePacket(
        task_id=task_id,
        user_goal="repair",
        research_question="repair",
        source_refs=["current:source"],
        verified_findings=["repair finding"],
        decision_inputs=["repair"],
    )
    contract = TurnContract(
        task_id=task_id,
        current_authority_version="current",
        current_user_goal="repair",
        next_external_user_action="none",
        deliverable_contract="repair",
        required_obligations=["repair"],
        current_evidence_refs=["current:source"],
    )
    plan = ActionPlan(
        kind="DELIVER_HANDOFF",
        payload="REPAIR_DIRECTION",
        deliverable_contract="repair",
        fulfilled_obligations=["repair"],
    )
    final = FinalResponseObject(
        task_id=task_id,
        consumed_packet_id=packet.packet_id,
        claims=["repair finding"],
    )
    return DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="REPAIR_DIRECTION",
        output_classifications={OutputClassification.PERSISTENT_REPAIR_DESIGN},
        research_scope=SCOPE,
        research_admission_receipts=[
            _receipt(semantic_key=OutputClassification.PERSISTENT_REPAIR_DESIGN)
        ],
        research_evidence_packet=packet.model_dump(mode="json"),
        final_response_object=final.model_dump(mode="json"),
        turn_contract=contract.model_dump(mode="json"),
        action_plan=plan.model_dump(mode="json"),
        evidence={
            "sources_callable": True,
            "entered_user_controlled_runtime": entered,
            "platform_bypass": bypass,
        },
    )


def test_full_packet_host_platform_repair_is_blocked():
    validated = _validator().validate(_full_repair_packet(entered=False, bypass=True))
    assert validated.evidence["evidence_packet_check"] == "PASS"
    assert validated.evidence["failure_locus"] == "HOST_PLATFORM"
    assert validated.evidence["repair_admission"] == "BLOCK"
    assert validated.evidence["stop_condition"] == "PLATFORM_BOUNDARY_PARKED"
    assert validated.status == "NO_SERIALIZE / UNKNOWN_WITH_EXACT_BLOCKER"


def test_full_packet_owned_runtime_repair_continues():
    validated = _validator().validate(_full_repair_packet(entered=True, bypass=False))
    assert validated.evidence["evidence_packet_check"] == "PASS"
    assert "failure_locus" not in validated.evidence or validated.evidence["failure_locus"] == "OWNED_RUNTIME"
    assert validated.status == "READY"


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


@pytest.mark.parametrize(
    ("output", "semantic_key"),
    [
        (
            "GitHub supports writing.",
            OutputClassification.CURRENT_PLATFORM_CAPABILITY,
        ),
        (
            "GitHub cannot write.",
            OutputClassification.CURRENT_PLATFORM_CAPABILITY,
        ),
        (
            "There is no available tool.",
            OutputClassification.CURRENT_TOOL_CAPABILITY,
        ),
    ],
    ids=["positive", "negative", "no-tool"],
)
def test_current_capability_claim_requires_evidence_without_architecture_language(
    output,
    semantic_key,
):
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output=output,
        research_scope="current capability claim",
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["required_semantic_keys"] == [semantic_key.value]


@pytest.mark.parametrize(
    ("source", "observed_result"),
    [
        (
            ResearchEvidenceSource.CURRENT_CALLABLE_TOOL_RESULT,
            "The current tool probe returned HTTP 403.",
        ),
        (
            ResearchEvidenceSource.CURRENT_OFFICIAL_DOCUMENTATION,
            "The current official capability page was read successfully.",
        ),
    ],
    ids=["tool-probe", "official-docs"],
)
def test_current_capability_claim_accepts_fresh_matching_evidence(source, observed_result):
    scope = "current connector availability"
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="The current connector tool is unavailable.",
        research_scope=scope,
        research_admission_receipts=[
            _receipt(
                semantic_key=OutputClassification.CURRENT_TOOL_CAPABILITY,
                scope=scope,
                source=source,
                observed_result=observed_result,
            )
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"


def test_user_observation_cannot_infer_platform_capability():
    scope = "current platform support"
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="Current ChatGPT 不支援 GitHub write。",
        research_scope=scope,
        research_admission_receipts=[
            _receipt(
                semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
                scope=scope,
                source=ResearchEvidenceSource.CURRENT_USER_PROVIDED_OBSERVATION,
                reference="current user observation",
                observed_result="平台不支援這個能力。",
            )
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH


def test_direct_user_observation_is_admissible_without_capability_inference():
    scope = "current GitHub call result"
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="The current GitHub write call returned 403.",
        research_scope=scope,
        research_admission_receipts=[
            _receipt(
                semantic_key=OutputClassification.CURRENT_TOOL_CAPABILITY,
                scope=scope,
                source=ResearchEvidenceSource.CURRENT_USER_PROVIDED_OBSERVATION,
                reference="current user-provided call output",
                observed_result="The observed call returned HTTP 403.",
            )
        ],
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"


@pytest.mark.parametrize(
    "receipt",
    [
        _receipt(
            semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
            scope="current GitHub capability",
            issued_at=NOW - timedelta(hours=2),
            valid_until=NOW - timedelta(hours=1),
        ),
        _receipt(
            semantic_key=OutputClassification.CURRENT_PLATFORM_CAPABILITY,
            scope="different capability scope",
        ),
    ],
    ids=["stale", "wrong-scope"],
)
def test_pure_capability_claim_rejects_stale_or_wrong_scope_evidence(receipt):
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="GitHub supports writing.",
        research_scope="current GitHub capability",
        research_admission_receipts=[receipt],
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH


def test_ordinary_prose_is_not_forced_to_research():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="Write the meeting notes in a concise style.",
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert validated.evidence["evidence_admission_check"] == "NOT_REQUIRED"


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
        document = AuthorityDocument(
            name="GLOBAL",
            role=AuthorityDocumentRole.LIVE_AUTHORITY,
            revision="GLOBAL_TEST_REVISION",
            path="GLOBAL_WINDOW_CANONICAL.md",
        )
        return AuthoritySnapshot(
            entries={
                Owner.GLOBAL: AuthorityEntry(
                    owner=Owner.GLOBAL,
                    normative_authority=document,
                )
            }
        )


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

    assert result.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert result.output["blocker"] == RESEARCH_PROVIDER_UNAVAILABLE
    egress = next(event for event in events if event["stage"] == "response_egress")
    assert CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE in egress["metadata"][
        "finding_codes"
    ]
    assert [event["stage"] for event in events[-4:]] == [
        "research_request_created",
        "research_loop_closed",
        "closure",
        "terminal_witness_consumption",
    ]
