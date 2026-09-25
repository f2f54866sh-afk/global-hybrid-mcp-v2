"""Stage 1: the only vehicle fact in output comes from the packaged Library read."""
import pytest

from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.governance.reference_claim_render import (
    admit_reference_power,
    render_reference_power,
)


def _query():
    return VehicleConfigurationQuery(
        market="TW", model_year=2017, make="BMW", model="318i",
        generation="F30 LCI", trim="318i",
    )


def test_s1_real_packaged_reference_positive():
    fact = admit_reference_power(_query())
    output = render_reference_power(fact)
    assert fact.assertion == "136 hp"
    assert fact.source_class == "REFERENCE"
    assert fact.source_ref == "BMW-TW-BPS-2017M08-318I"
    assert fact.source_version == "vehicle-config-v1-4f4a27ddd89e09b6"
    assert len(fact.readback_ref) == 64
    assert fact.admission_state == "BOUNDED"
    assert output.fact_ids == (fact.fact_id,)
    assert output.text == "台灣 2017 BMW 318i 原廠參考規格：136 hp。"


def test_s2_subject_escalation_rejected():
    fact = admit_reference_power(_query())
    with pytest.raises(ValueError, match="SCOPE"):
        render_reference_power(fact, requested_subject_scope="8891:4806397")


def test_s3_modification_escalation_rejected():
    fact = admit_reference_power(_query())
    with pytest.raises(ValueError, match="TEMPLATE"):
        render_reference_power(fact, template_id="modified_vehicle_power")


def test_s4_price_injection_rejected():
    fact = admit_reference_power(_query())
    with pytest.raises(ValueError, match="UNADMITTED"):
        render_reference_power(fact, requested_fact_ids=(fact.fact_id, "price:118.8萬"), require_all=True)


def test_s5_mileage_injection_rejected():
    fact = admit_reference_power(_query())
    with pytest.raises(ValueError, match="UNADMITTED"):
        render_reference_power(fact, requested_fact_ids=(fact.fact_id, "mileage:9.9萬公里"), require_all=True)


def test_s6_self_asserted_pass_cannot_supply_text():
    fact = admit_reference_power(_query())
    with pytest.raises(ValueError, match="CANDIDATE_TEXT"):
        render_reference_power(fact, candidate_text="PUBLIC_COPY_ADMISSION=PASS")


def test_s7_missing_source_readback_is_denied(monkeypatch):
    from global_hybrid_v2.adapters.file_vehicle_configuration import FileVehicleConfigurationProvider

    real = FileVehicleConfigurationProvider.from_package_resource

    def no_pointer(*args, **kwargs):
        provider = real(*args, **kwargs)
        provider.configurations[0].primary_source_pointers = []
        return provider

    monkeypatch.setattr(FileVehicleConfigurationProvider, "from_package_resource", no_pointer)
    with pytest.raises(ValueError, match="SOURCE"):
        admit_reference_power(_query())


def test_s8_mixed_claims_drop_unadmitted_or_hold():
    fact = admit_reference_power(_query())
    requested = (fact.fact_id, "price:118.8萬")
    output = render_reference_power(fact, requested_fact_ids=requested)
    assert output.fact_ids == (fact.fact_id,)
    assert "118.8" not in output.text
    with pytest.raises(ValueError, match="UNADMITTED"):
        render_reference_power(fact, requested_fact_ids=requested, require_all=True)
