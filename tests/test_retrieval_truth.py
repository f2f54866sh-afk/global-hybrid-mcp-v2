import pytest
from pydantic import ValidationError

from global_hybrid_v2.contracts import (
    DomainResult,
    OutputClassification,
    Owner,
    RetrievalFalseNegativeEvidence,
    RetrievalFalseNegativeReason,
    RetrievalReceipt,
    RetrievalState,
)
from global_hybrid_v2.governance.egress import (
    CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
    NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE,
    RETRIEVAL_FALSE_NEGATIVE,
    UNKNOWN_WITH_EXACT_BLOCKER,
    ResponseEgressValidator,
)

RETRIEVAL_KEY = "prior-instruction:authority-promotion"


def _receipt(state: RetrievalState, *, key: str = RETRIEVAL_KEY) -> RetrievalReceipt:
    if state is RetrievalState.VERIFIED_ABSENT:
        return RetrievalReceipt(
            retrieval_key=key,
            state=state,
            searched_source_classes=["current_conversation", "authorized_repository"],
            query_variants=["authority promotion", "owner-signed activation"],
            coverage_complete=True,
            unresolved_source_gap=False,
            evidence_references=["retrieval-run:1"],
        )
    return RetrievalReceipt(
        retrieval_key=key,
        state=state,
        searched_source_classes=["current_conversation"],
        query_variants=["authority promotion"],
        coverage_complete=False,
        unresolved_source_gap=True,
    )


def _result(
    *,
    output: str = "沒有相關紀錄",
    receipts: list[RetrievalReceipt] | None = None,
    retrieval_key: str | None = RETRIEVAL_KEY,
) -> DomainResult:
    return DomainResult(
        owner=Owner.GLOBAL,
        status="OK",
        output=output,
        retrieval_key=retrieval_key,
        retrieval_receipts=receipts or [],
    )


def test_absence_claim_without_retrieval_receipt_is_blocked():
    validated = ResponseEgressValidator().validate(_result())

    assert validated.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert validated.output["retrieval_state"] == "NO_RECEIPT"
    assert (
        NEGATIVE_RETRIEVAL_CLAIM_WITHOUT_VERIFIED_ABSENCE
        in validated.evidence["finding_codes"]
    )


@pytest.mark.parametrize(
    "state",
    [
        RetrievalState.NOT_RETRIEVED,
        RetrievalState.COVERAGE_INCOMPLETE,
        RetrievalState.SOURCE_INACCESSIBLE,
    ],
)
def test_nonterminal_retrieval_state_cannot_prove_absence(state):
    validated = ResponseEgressValidator().validate(_result(receipts=[_receipt(state)]))

    assert validated.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert validated.output["retrieval_state"] == state.value
    assert validated.evidence["negative_retrieval_egress_check"] == "FAIL"


def test_valid_verified_absent_receipt_allows_matching_absence_claim():
    validated = ResponseEgressValidator().validate(
        _result(receipts=[_receipt(RetrievalState.VERIFIED_ABSENT)])
    )

    assert validated.status == "OK"
    assert validated.output == "沒有相關紀錄"
    assert validated.evidence["negative_retrieval_egress_check"] == "PASS"
    assert (
        OutputClassification.PRIOR_CONTEXT_ABSENCE_CLAIM
        in validated.output_classifications
    )


def test_verified_absent_receipt_must_match_retrieval_key():
    validated = ResponseEgressValidator().validate(
        _result(receipts=[_receipt(RetrievalState.VERIFIED_ABSENT, key="different-key")])
    )

    assert validated.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert validated.output["retrieval_state"] == "NO_RECEIPT"


def test_verified_absence_does_not_bypass_current_capability_evidence_gate():
    validated = ResponseEgressValidator().validate(
        _result(
            output="No previous instruction; ChatGPT can write GitHub.",
            receipts=[_receipt(RetrievalState.VERIFIED_ABSENT)],
        )
    )

    assert validated.status == UNKNOWN_WITH_EXACT_BLOCKER
    assert validated.evidence["negative_retrieval_egress_check"] == "PASS"
    assert (
        CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE
        in validated.evidence["finding_codes"]
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"coverage_complete": False},
        {"unresolved_source_gap": True},
        {"searched_source_classes": []},
        {"query_variants": []},
    ],
)
def test_verified_absent_requires_closed_coverage_proof(overrides):
    values = {
        "retrieval_key": RETRIEVAL_KEY,
        "state": RetrievalState.VERIFIED_ABSENT,
        "searched_source_classes": ["current_conversation"],
        "query_variants": ["authority promotion"],
        "coverage_complete": True,
        "unresolved_source_gap": False,
        **overrides,
    }

    with pytest.raises(ValidationError, match="VERIFIED_ABSENT requires"):
        RetrievalReceipt(**values)


def test_found_receipt_does_not_affect_normal_nonabsence_output():
    validated = ResponseEgressValidator().validate(
        _result(
            output="Prior instruction was retrieved and applied.",
            receipts=[_receipt(RetrievalState.FOUND)],
        )
    )

    assert validated.status == "OK"
    assert validated.output == "Prior instruction was retrieved and applied."
    assert validated.output_classifications == {OutputClassification.DIAGNOSIS_ONLY}


def test_false_negative_requires_explicit_current_two_part_evidence():
    validated = ResponseEgressValidator().validate(
        _result(output="Retrieval was corrected.").model_copy(
            update={
                "retrieval_false_negative_evidence": [
                    RetrievalFalseNegativeEvidence(
                        retrieval_key=RETRIEVAL_KEY,
                        prior_negative_claim=True,
                        later_matching_content_found=True,
                        reason=RetrievalFalseNegativeReason.CONTEXT_FIREWALL_DROP,
                    )
                ]
            }
        )
    )

    assert RETRIEVAL_FALSE_NEGATIVE in validated.evidence["finding_codes"]
    assert validated.evidence["retrieval_false_negative"] == [
        {
            "retrieval_key": RETRIEVAL_KEY,
            "reason": "CONTEXT_FIREWALL_DROP",
        }
    ]


def test_incomplete_false_negative_evidence_does_not_guess_prior_miss():
    validated = ResponseEgressValidator().validate(
        _result(output="Retrieval result reviewed.").model_copy(
            update={
                "retrieval_false_negative_evidence": [
                    RetrievalFalseNegativeEvidence(
                        retrieval_key=RETRIEVAL_KEY,
                        prior_negative_claim=False,
                        later_matching_content_found=True,
                        reason=RetrievalFalseNegativeReason.UNKNOWN,
                    )
                ]
            }
        )
    )

    assert RETRIEVAL_FALSE_NEGATIVE not in validated.evidence.get("finding_codes", [])
