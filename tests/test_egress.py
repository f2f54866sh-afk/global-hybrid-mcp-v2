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
from global_hybrid_v2.governance.egress import RUN_REQUIRED_RESEARCH, ResponseEgressValidator
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
SCOPE = "GLOBAL response-egress architecture enforcement"


def _receipt(
    *,
    semantic_key: OutputClassification = OutputClassification.PERSISTENT_REPAIR_DESIGN,
    scope: str = SCOPE,
    issued_at: datetime = NOW - timedelta(minutes=10),
    valid_until: datetime = NOW + timedelta(minutes=50),
    reference: str = "official-current-source:response-egress",
) -> ResearchAdmissionReceipt:
    return ResearchAdmissionReceipt(
        status=ResearchAdmissionStatus.PASS,
        semantic_key=semantic_key,
        scope=scope,
        issued_at=issued_at,
        valid_until=valid_until,
        evidence=[
            ResearchEvidence(
                source=ResearchEvidenceSource.OFFICIAL_SOURCE,
                reference=reference,
            )
        ],
    )


def _validator() -> ResponseEgressValidator:
    return ResponseEgressValidator(clock=lambda: NOW)


def test_case_a_persistent_repair_without_receipt_requires_research():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output={"REPAIR_DIRECTION": "Add a persistent architecture enforcement point."},
        research_scope=SCOPE,
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["state"] == RUN_REQUIRED_RESEARCH
    assert validated.output["result"] == "UNKNOWN"
    assert "Add a persistent" not in str(validated.output)
    assert validated.output["required_semantic_keys"] == ["PERSISTENT_REPAIR_DESIGN"]


def test_case_b_unverified_platform_capability_claim_is_blocked():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="我以為 ChatGPT 可以直接寫 Codex",
        evidence={"confidence": "likely; model knowledge alone"},
        research_scope="ChatGPT direct-write capability for Codex",
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["required_semantic_keys"] == [
        "CURRENT_PLATFORM_OR_CAPABILITY_CLAIM"
    ]
    assert validated.evidence["non_evidence_language_detected"] is True


def test_case_c_fresh_matching_scope_receipt_allows_repair_design():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output={"ARCHITECTURE_CHOICE": "Use the existing closure point."},
        research_scope=SCOPE,
        research_admission_receipts=[_receipt()],
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert validated.output == result.output
    assert validated.output_classifications == {
        OutputClassification.PERSISTENT_REPAIR_DESIGN
    }


def test_case_d_diagnosis_only_is_not_overblocked():
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output="The existing closure path does not validate domain output.",
        output_classifications={OutputClassification.DIAGNOSIS_ONLY},
    )

    validated = _validator().validate(result)

    assert validated.status == "READY"
    assert validated.output == result.output
    assert validated.research_admission_receipts == []


@pytest.mark.parametrize(
    "receipt",
    [
        _receipt(
            issued_at=NOW - timedelta(hours=2),
            valid_until=NOW - timedelta(hours=1),
        ),
        _receipt(semantic_key=OutputClassification.CURRENT_EXTERNAL_FACT_CLAIM),
        _receipt(scope="different architecture scope"),
        _receipt(reference="probably; inferred from memory; model knowledge alone"),
    ],
    ids=["stale", "wrong-semantic-key", "wrong-scope", "model-confidence-is-not-evidence"],
)
def test_case_e_nonmatching_research_receipt_is_blocked(receipt):
    result = DomainResult(
        owner=Owner.GLOBAL,
        status="READY",
        output={"IMPLEMENTATION_PATTERN": "Persist the proposed enforcement."},
        research_scope=SCOPE,
        research_admission_receipts=[receipt],
    )

    validated = _validator().validate(result)

    assert validated.status == RUN_REQUIRED_RESEARCH
    assert validated.output["required_semantic_keys"] == ["PERSISTENT_REPAIR_DESIGN"]


class _StaticAuthority(AuthorityResolver):
    def __init__(self):
        pass

    def resolve(self) -> AuthoritySnapshot:
        return AuthoritySnapshot(entries={})


class _RepairDomain:
    def run(self, contract: TaskContract) -> DomainResult:
        del contract
        return DomainResult(
            owner=Owner.GLOBAL,
            status="READY",
            output={"SHOULD_CHANGE": "Change the persistent runtime architecture."},
            research_scope=SCOPE,
        )


def test_dispatcher_enforces_egress_before_closure(capsys):
    dispatcher = Dispatcher(
        authority=_StaticAuthority(),
        domains={Owner.GLOBAL: _RepairDomain()},
        trace=TraceBus(),
        egress=_validator(),
    )

    result = dispatcher.dispatch(TaskRequest(request_text="repair architecture", intent=Intent.GOVERNANCE))
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert result.status == RUN_REQUIRED_RESEARCH
    assert [event["stage"] for event in events[-2:]] == ["response_egress", "closure"]
    assert events[-2]["decision"] == "BLOCK"
    assert events[-1]["decision"] == RUN_REQUIRED_RESEARCH
