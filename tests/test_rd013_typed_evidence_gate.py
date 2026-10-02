"""Exact bounded fixtures are safety qualification, never public semantic PASS."""
import json
from pathlib import Path

import pytest

from global_hybrid_v2.typed_evidence_gate import (
    Atom,
    EvidenceState,
    Proposition,
    PublicationPolicy,
    admit,
    evaluate,
)

PACKET = json.loads((Path(__file__).parent / "fixtures/rd013_typed_evidence_cases.json")
                    .read_text(encoding="utf-8"))
EVIDENCE = tuple(Proposition(**{**item, "evidence_state": EvidenceState(item["evidence_state"]),
                               "publication_policy": PublicationPolicy(item["publication_policy"])})
                 for item in PACKET["evidence_packet"])


def gate(text):
    return evaluate(text, evidence=EVIDENCE, target_entity="tiguan_2021")


@pytest.mark.parametrize("case", PACKET["cases"], ids=lambda case: case["id"])
def test_exact_preserved_bounded_fixture_and_lossless_coverage(case):
    result = gate(case["candidate"])
    assert result.allowed == (case["expected"] == "ALLOW")
    assert "".join(span.text for span in result.spans) == case["candidate"]
    assert all(span.text == case["candidate"][span.start:span.end] for span in result.spans)
    if any(span.disposition == "UNPARSED_OR_AMBIGUOUS" for span in result.spans):
        assert not result.allowed


def test_exact_aggregate_and_saved_counterexamples():
    results = [(case, gate(case["candidate"])) for case in PACKET["cases"]]
    assert len(results) == 45
    assert sum(result.allowed for _, result in results) == 4
    assert sum(not result.allowed for _, result in results) == 41
    assert sum(any(span.disposition == "UNPARSED_OR_AMBIGUOUS" for span in result.spans)
               for _, result in results) == 15
    saved = [(case, result) for case, result in results if case["id"].startswith("REG_")]
    assert len(saved) == 13 and all(not result.allowed for _, result in saved)


@pytest.mark.parametrize("item", PACKET["additional_coverage_checks"]["suffix_remainder_checks"])
def test_preserved_additional_remainder_is_lossless_and_withheld(item):
    positive = next(case["candidate"] for case in PACKET["cases"] if case["id"] == item["positive"])
    text = positive + item["suffix"]
    result = gate(text)
    assert not result.allowed
    assert "".join(span.text for span in result.spans) == text


@pytest.mark.parametrize("state", [EvidenceState.UNKNOWN, EvidenceState.ABSENT])
@pytest.mark.parametrize("polarity", [True, False])
def test_unknown_absent_support_neither_polarity(state, polarity):
    evidence = (Proposition("target", "ecu_tune", "STAGE2", True, state,
                            PublicationPolicy.ALLOW, "snapshot:source"),)
    assert admit(Atom("target", "ecu_tune", "STAGE2", polarity), evidence)


def test_truth_publication_and_conflicting_evidence_are_separate():
    atom = Atom("target", "ecu_tune", "STAGE2", False)
    false = Proposition("target", "ecu_tune", "STAGE2", True, EvidenceState.CONFIRMED_FALSE,
                        PublicationPolicy.ALLOW, "snapshot:source")
    assert admit(atom, (false,)) is None
    forbidden = Proposition("target", "ecu_tune", "STAGE2", False, EvidenceState.CONFIRMED_TRUE,
                            PublicationPolicy.FORBID, "snapshot:source")
    assert admit(atom, (forbidden,)) == "TYPED_EVIDENCE_PUBLICATION_FORBID"
    opposite = Proposition("target", "ecu_tune", "STAGE2", True, EvidenceState.CONFIRMED_TRUE,
                           PublicationPolicy.ALLOW, "snapshot:other")
    assert admit(atom, (false, opposite))


def test_entity_and_single_value_are_not_portable():
    assert admit(Atom("tiguan_2021", "vehicle_year", "2020"), EVIDENCE)
    assert admit(Atom("tiguan_2021", "horsepower", "300hp"), EVIDENCE) == "TYPED_EVIDENCE_ENTITY_MISMATCH"
    assert admit(Atom("tiguan_2021", "mst_exhaust", "PRESENT"), EVIDENCE)


def test_compound_cannot_pass_with_one_supported_atom():
    result = gate("這台車有MST Performance進氣，而且已完成二階ECU調校。")
    assert not result.allowed
    assert sum(len(span.atoms) for span in result.spans) == 2


def test_saved_remainders_have_no_encoding_replacement_characters():
    """Corrupt receipts cannot prove the original adversarial Chinese wording."""
    for item in PACKET["additional_coverage_checks"]["suffix_remainder_checks"]:
        assert "\ufffd" not in item["suffix"], item


def test_incumbent_positive_and_paired_high_risk_keep_public_copy_withheld(tmp_path):
    from global_hybrid_v2.existing_copy_policy_bridge import ExistingCopyPolicyBridge, acceptance_witness
    from global_hybrid_v2.public_copy_finalizer import (
        AppOwnedPublicCopyFinalizer,
        GuardCheck,
        GuardDecision,
        sha256_json,
    )
    from tests.test_existing_copy_policy_bridge import candidate, setup

    store, snapshot = setup(tmp_path)
    value = candidate()
    witness = acceptance_witness(snapshot, value, sha256_json(value))
    assert witness.hard_gate_blockers == ()
    assert "保養紀錄可查" in witness.unresolved_remainders
    assert "保養單可查" not in witness.unresolved_remainders
    finalizer = AppOwnedPublicCopyFinalizer(store=store, guard=ExistingCopyPolicyBridge())
    positive = finalizer.finalize(snapshot.task_handle, value)
    assert positive.guard_receipt.deterministic_hard_gates is GuardCheck.PASS
    assert positive.decision is GuardDecision.FAIL and positive.final_output is None
    assert positive.guard_receipt.capability_debt
    negative = finalizer.finalize(snapshot.task_handle, candidate(subtitle="日常代步，二階也完成。"))
    assert "TYPED_EVIDENCE_UNPARSED_REMAINDER" in negative.guard_receipt.blocker_codes
    assert negative.guard_receipt.deterministic_hard_gates is GuardCheck.FAIL
    assert negative.decision is GuardDecision.FAIL and negative.final_output is None
