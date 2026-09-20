import pytest

from global_hybrid_v2.contracts import (
    AuthorityDocument,
    AuthorityDocumentRole,
    AuthorityEntry,
    AuthoritySnapshot,
    DomainContractStatus,
    DomainInteractionMode,
    LibraryAccessKind,
    LibraryAccessRequest,
    Owner,
    TaskContract,
    VehicleConfigurationQuery,
)
from global_hybrid_v2.domains.library_projection import LibraryProjectionDomain
from global_hybrid_v2.domains.vehicle_configuration import (
    VehicleConfigurationLookupResult,
    VehicleConfigurationLookupState,
    VehicleConfigurationReference,
)


def _authority():
    document = AuthorityDocument(
        name="library",
        role=AuthorityDocumentRole.LIVE_AUTHORITY,
        revision="LIBRARY_TEST_REV",
        path="/library",
    )
    return AuthoritySnapshot(
        entries={
            Owner.LIBRARY_FACT: AuthorityEntry(
                owner=Owner.LIBRARY_FACT,
                normative_authority=document,
            )
        }
    )


def _query():
    return VehicleConfigurationQuery(
        market="TW", model_year=2018, make="BMW", model="318I"
    )


def _task(*, query=True):
    authority = _authority()
    return TaskContract(
        request_text="vehicle config",
        intent="sales_human",
        owner=Owner.SALES_HUMAN,
        effects=[],
        authority_snapshot_id=authority.snapshot_id,
        context=[],
        vehicle_configuration_query=_query() if query else None,
    ), authority


def _request(**changes):
    values = {
        "actor_owner": Owner.SALES_HUMAN,
        "access_kind": LibraryAccessKind.READ_PROJECTION,
        "task_scope": "vehicle-config",
        "projection": "vehicle_configuration_reference",
    }
    values.update(changes)
    return LibraryAccessRequest(**values)


def test_default_unavailable_vehicle_projection_and_ownership_boundary():
    task, authority = _task()
    contract = LibraryProjectionDomain().project(_request(), task=task, authority=authority)
    assert contract.provider_owner is Owner.LIBRARY_FACT
    assert contract.consumer_owner is Owner.SALES_HUMAN
    assert contract.status is DomainContractStatus.PASS
    assert contract.interaction_mode is DomainInteractionMode.SERVICE
    assert "VEHICLE_CONFIGURATION_REFERENCE_NEED" in contract.requirement_ids
    assert contract.payload["projection"] == "vehicle_configuration_reference"
    assert contract.payload["evidence_role"] == "LIBRARY_REFERENCE_NOT_INSTANCE_PROOF"
    assert contract.payload["lookup_state"] == "PROVIDER_UNAVAILABLE"
    assert contract.payload["lookup_state"] != "MISS"
    assert contract.payload["configurations"] == []
    assert contract.payload["provider_id"] and contract.payload["provider_version"]
    assert contract.payload["query"] == _query().model_dump(mode="json")
    assert "library-authority:LIBRARY_TEST_REV" in contract.provenance
    assert {
        "exact_instance_trim",
        "factory_provenance",
        "final_sales_copy",
        "creative_decision",
        "targeting_decision",
    } <= contract.blocked_foreign_fields


def test_vehicle_projection_admission_fails_closed():
    task, authority = _task(query=False)
    with pytest.raises(ValueError):
        LibraryProjectionDomain().project(_request(), task=task, authority=authority)
    task, authority = _task()
    with pytest.raises(ValueError):
        LibraryProjectionDomain().project(
            _request(actor_owner=Owner.VISUAL), task=task, authority=authority
        )
    with pytest.raises(ValueError):
        LibraryProjectionDomain().project(
            _request(access_kind=LibraryAccessKind.COMMIT_FACT),
            task=task,
            authority=authority,
        )
    with pytest.raises(ValueError):
        LibraryProjectionDomain().project(
            _request(projection="unsupported"), task=task, authority=authority
        )


class FakeProvider:
    def __init__(self, state):
        self.state = state

    def lookup(self, query):
        configurations = []
        if self.state is VehicleConfigurationLookupState.HIT:
            configurations = [
                VehicleConfigurationReference(
                    configuration_id="tw-2018-318i",
                    market="TW",
                    model_year=2018,
                    make="BMW",
                    model="318I",
                    powertrain={"fuel": "petrol"},
                    primary_source_pointers=["fixture:configuration"],
                    last_verified="2026-09-19",
                    conflict_state="NONE",
                    query_key="TW:2018:BMW:318I",
                )
            ]
        return VehicleConfigurationLookupResult(
            state=self.state,
            query=query,
            configurations=configurations,
            provenance=["provider:fixture:v1"],
            provider_id="fixture",
            provider_version="v1",
        )


@pytest.mark.parametrize(
    "state",
    [
        VehicleConfigurationLookupState.HIT,
        VehicleConfigurationLookupState.STALE,
        VehicleConfigurationLookupState.CONFLICT,
    ],
)
def test_provider_state_and_provenance_are_preserved(state):
    task, authority = _task()
    contract = LibraryProjectionDomain(FakeProvider(state)).project(
        _request(), task=task, authority=authority
    )
    assert contract.payload["lookup_state"] == state.value
    assert contract.payload["provider_id"] == "fixture"
    assert contract.payload["provider_version"] == "v1"
    assert "provider:fixture:v1" in contract.provenance
    assert "library-authority:LIBRARY_TEST_REV" in contract.provenance
    if state is VehicleConfigurationLookupState.HIT:
        assert contract.payload["configurations"][0]["configuration_id"] == "tw-2018-318i"


def test_media_projection_semantics_remain_unchanged():
    task, authority = _task(query=False)
    contract = LibraryProjectionDomain().project(
        _request(projection="sales_media_evidence"), task=task, authority=authority
    )
    assert contract.requirement_ids == ["SALES_MEDIA_FACT_NEED"]
    assert contract.payload["evidence_role"] == "LIBRARY_EVIDENCE_NOT_SALES_DECISION"
    assert contract.payload["projection"] == "sales_media_evidence"


def test_vehicle_required_fields_override_is_preserved():
    task, authority = _task()
    fields = {"projection", "lookup_state", "provider_id"}
    contract = LibraryProjectionDomain().project(
        _request(required_fields=fields), task=task, authority=authority
    )
    assert contract.required_fields == fields
    assert contract.used_fields == fields
