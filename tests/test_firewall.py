import json

import pytest

from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    ContextAdmissionDecision,
    ContextAdmissionReason,
    ContextClass,
    ContextItem,
    ContextOrigin,
    Intent,
    Owner,
    TaskRequest,
)
from global_hybrid_v2.domains.stubs import NotConfiguredDomain
from global_hybrid_v2.governance.firewall import TaskFirewall
from global_hybrid_v2.runtime.dispatcher import Dispatcher
from global_hybrid_v2.runtime.trace import TraceBus


def _snapshot():
    return AuthoritySnapshot(
        entries={
            owner: AuthorityEntry(
                owner=owner,
                normative_authority=AuthorityDocument(
                    name=owner.value,
                    role=AuthorityDocumentRole.LIVE_AUTHORITY,
                    revision=f"{owner.value}-1",
                    path=f"{owner.value}.md",
                ),
            )
            for owner in Owner
        }
    )


def _item(
    *,
    origin: ContextOrigin,
    context_class: ContextClass,
    current_binding: bool = False,
    provenance: list[str] | None = None,
) -> ContextItem:
    return ContextItem(
        id="context-1",
        origin=origin,
        context_class=context_class,
        purpose="support current task",
        task_scope="task-1",
        payload="context payload",
        provenance=provenance if provenance is not None else ["source:fixture"],
        current_binding=current_binding,
    )


def _evaluate(item: ContextItem):
    result = TaskFirewall().evaluate([item], _snapshot())
    return result, result.receipts[0]


def test_memory_stable_user_preference_is_bounded_advisory():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.MEMORY,
            context_class=ContextClass.STABLE_USER_PREFERENCE,
        )
    )

    assert [item.id for item in result.admitted] == ["context-1"]
    assert receipt.decision is ContextAdmissionDecision.ADVISORY
    assert receipt.reason_code is ContextAdmissionReason.ADVISORY_MEMORY_ACCEPTED


def test_memory_cannot_supply_normative_authority():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.MEMORY,
            context_class=ContextClass.NORMATIVE_AUTHORITY,
        )
    )

    assert result.admitted == []
    assert receipt.decision is ContextAdmissionDecision.QUARANTINE
    assert receipt.reason_code is ContextAdmissionReason.LEGACY_AUTHORITY_FORBIDDEN


def test_history_domain_heuristic_is_advisory_only():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.HISTORY,
            context_class=ContextClass.DOMAIN_HEURISTIC,
        )
    )

    assert len(result.admitted) == 1
    assert receipt.decision is ContextAdmissionDecision.ADVISORY
    assert receipt.reason_code is ContextAdmissionReason.ADVISORY_HISTORY_ACCEPTED


def test_case_history_without_current_binding_is_quarantined():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.HISTORY,
            context_class=ContextClass.CASE_HISTORY,
        )
    )

    assert result.admitted == []
    assert receipt.reason_code is ContextAdmissionReason.CASE_HISTORY_NOT_CURRENTLY_BOUND


def test_case_history_with_explicit_current_binding_is_bounded_advisory():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.HISTORY,
            context_class=ContextClass.CASE_HISTORY,
            current_binding=True,
        )
    )

    assert len(result.admitted) == 1
    assert receipt.decision is ContextAdmissionDecision.ADVISORY
    assert receipt.reason_code is ContextAdmissionReason.CASE_HISTORY_CURRENTLY_BOUND


def test_memory_current_capability_fact_requires_fresh_evidence():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.MEMORY,
            context_class=ContextClass.CURRENT_CAPABILITY_FACT,
        )
    )

    assert result.admitted == []
    assert (
        receipt.reason_code
        is ContextAdmissionReason.CURRENT_CAPABILITY_REQUIRES_FRESH_EVIDENCE
    )


def test_stale_or_superseded_rule_is_always_blocked():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.CURRENT_USER,
            context_class=ContextClass.STALE_OR_SUPERSEDED_RULE,
        )
    )

    assert result.admitted == []
    assert receipt.reason_code is ContextAdmissionReason.STALE_RULE_BLOCKED


def test_unknown_context_class_is_quarantined_with_reason():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.CURRENT_USER,
            context_class=ContextClass.UNKNOWN,
        )
    )

    assert result.admitted == []
    assert receipt.reason_code is ContextAdmissionReason.UNKNOWN_CONTEXT_CLASS


def test_wrong_current_authority_revision_remains_quarantined():
    item = _item(
        origin=ContextOrigin.CURRENT_AUTHORITY,
        context_class=ContextClass.NORMATIVE_AUTHORITY,
    ).model_copy(
        update={
            "authority_owner": Owner.GLOBAL,
            "authority_revision": "OLD",
        }
    )

    result, receipt = _evaluate(item)

    assert result.admitted == []
    assert receipt.reason_code is ContextAdmissionReason.AUTHORITY_REVISION_MISMATCH


def test_matching_current_authority_revision_is_executable():
    item = _item(
        origin=ContextOrigin.CURRENT_AUTHORITY,
        context_class=ContextClass.NORMATIVE_AUTHORITY,
    ).model_copy(
        update={
            "authority_owner": Owner.GLOBAL,
            "authority_revision": "GLOBAL-1",
        }
    )

    result, receipt = _evaluate(item)

    assert len(result.admitted) == 1
    assert receipt.decision is ContextAdmissionDecision.EXECUTABLE
    assert receipt.reason_code is ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED


def test_legacy_current_fact_is_only_a_retrieval_hint():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.MEMORY,
            context_class=ContextClass.CURRENT_FACT,
        )
    )

    assert len(result.admitted) == 1
    assert receipt.decision is ContextAdmissionDecision.RETRIEVAL_HINT
    assert receipt.reason_code is ContextAdmissionReason.LEGACY_FACT_RETRIEVAL_HINT


def test_current_tool_capability_fact_is_executable_current_evidence():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.CURRENT_TOOL_RESULT,
            context_class=ContextClass.CURRENT_CAPABILITY_FACT,
        )
    )

    assert len(result.admitted) == 1
    assert receipt.decision is ContextAdmissionDecision.EXECUTABLE
    assert receipt.reason_code is ContextAdmissionReason.CURRENT_CONTEXT_ACCEPTED


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("purpose", ContextAdmissionReason.MISSING_PURPOSE),
        ("task_scope", ContextAdmissionReason.MISSING_SCOPE),
    ],
)
def test_missing_context_contract_field_is_quarantined(field, reason):
    item = _item(
        origin=ContextOrigin.MEMORY,
        context_class=ContextClass.STABLE_USER_PREFERENCE,
    ).model_copy(update={field: ""})

    result, receipt = _evaluate(item)

    assert result.admitted == []
    assert receipt.reason_code is reason


def test_missing_provenance_is_quarantined():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.MEMORY,
            context_class=ContextClass.STABLE_USER_PREFERENCE,
            provenance=[],
        )
    )

    assert result.admitted == []
    assert receipt.reason_code is ContextAdmissionReason.MISSING_PROVENANCE


def test_reference_pointer_is_retrieval_hint_not_fact_evidence():
    result, receipt = _evaluate(
        _item(
            origin=ContextOrigin.ARCHIVE,
            context_class=ContextClass.REFERENCE_POINTER,
        )
    )

    assert len(result.admitted) == 1
    assert receipt.decision is ContextAdmissionDecision.RETRIEVAL_HINT
    assert receipt.reason_code is ContextAdmissionReason.REFERENCE_POINTER_ACCEPTED


class _StaticAuthority:
    def resolve(self):
        return _snapshot()


def test_dispatcher_trace_contains_context_admission_reason_codes(capsys):
    dispatcher = Dispatcher(
        authority=_StaticAuthority(),
        domains={Owner.GLOBAL: NotConfiguredDomain(Owner.GLOBAL)},
        trace=TraceBus(),
    )
    dispatcher.dispatch(
        TaskRequest(
            request_text="inspect context admission",
            intent=Intent.GOVERNANCE,
            context=[
                _item(
                    origin=ContextOrigin.MEMORY,
                    context_class=ContextClass.STABLE_USER_PREFERENCE,
                )
            ],
        )
    )

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    firewall = next(event for event in events if event["stage"] == "firewall")
    receipt = firewall["metadata"]["admission_receipts"][0]
    assert receipt == {
        "context_id": "context-1",
        "origin": "memory",
        "context_class": "STABLE_USER_PREFERENCE",
        "decision": "ADVISORY",
        "reason_code": "ADVISORY_MEMORY_ACCEPTED",
    }
