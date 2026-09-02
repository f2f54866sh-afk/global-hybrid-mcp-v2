import pytest

from global_hybrid_v2.contracts import TraceEvent
from global_hybrid_v2.governance.egress import (
    ASSUMPTION_USED_AS_EVIDENCE,
    CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
    RESEARCH_GATE_BYPASS,
)
from global_hybrid_v2.observer.witness import ReadOnlyWitness


def test_witness_has_no_mutation_api():
    witness = ReadOnlyWitness()
    forbidden = {"write", "mutate", "execute", "promote", "update_authority", "tool"}
    assert not forbidden.intersection(set(dir(witness)))


def _egress_event(*, finding_codes: list[str], **metadata: object) -> TraceEvent:
    return TraceEvent(
        trace_id="trace-1",
        task_id="task-1",
        stage="response_egress",
        decision="BLOCK",
        metadata={"finding_codes": finding_codes, **metadata},
    )


@pytest.mark.parametrize(
    "code",
    [
        ASSUMPTION_USED_AS_EVIDENCE,
        CURRENT_CAPABILITY_CLAIM_WITHOUT_CURRENT_EVIDENCE,
        RESEARCH_GATE_BYPASS,
    ],
)
def test_witness_recognizes_evidence_admission_regressions(code):
    finding = ReadOnlyWitness().observe(_egress_event(finding_codes=[code]))

    assert finding is not None
    assert finding.code == code


def test_witness_marks_recurrence_after_same_defect_was_claimed_fixed():
    witness = ReadOnlyWitness()
    claimed_fixed = _egress_event(
        finding_codes=[],
        defect_family="UNSUPPORTED_ASSUMPTION_TO_ARCHITECTURE_DECISION",
        fix_claimed=True,
    )
    recurrence = _egress_event(
        finding_codes=[RESEARCH_GATE_BYPASS],
        defect_family="UNSUPPORTED_ASSUMPTION_TO_ARCHITECTURE_DECISION",
        user_reported_recurrence=True,
    )

    assert witness.observe(claimed_fixed) is None
    finding = witness.observe(recurrence)

    assert finding is not None
    assert finding.code == "RECURRENT_DEFECT"
