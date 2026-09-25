"""Stage 2 exact-object capture and constrained rendering acceptance."""
import json
from pathlib import Path

import pytest

from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.governance.reference_claim_render import (
    admit_exact_object_title,
    admit_reference_power,
    render_exact_object_title,
    render_reference_and_object,
)

CAPTURE = Path(__file__).resolve().parents[1] / "validation/stage2/8891-4806397-capture.json"
CAPTURE_HASH = "9fa891ba0fb328f743c86a2de20c760a78df0752d58ca52f3b91d702a81fbea7"


def _admit(path=CAPTURE, **kwargs):
    return admit_exact_object_title(path, requested_object_id="4806397",
                                    expected_capture_hash=CAPTURE_HASH, **kwargs)


def _synthetic_capture(tmp_path, **changes):
    value = json.loads(CAPTURE.read_text(encoding="utf-8"))
    value.update(changes)
    path = tmp_path / "synthetic-capture.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def test_o1_real_exact_object_capture_positive():
    fact = _admit()
    output = render_exact_object_title(fact, requested_object_id="4806397")
    assert fact.object_platform == "8891"
    assert fact.object_id == "4806397"
    assert fact.subject_scope == "EXACT_OBJECT"
    assert fact.source_field == "listing_title"
    assert fact.object_capture_hash == CAPTURE_HASH
    assert fact.admission_state == "BOUNDED"
    assert output.fact_ids == (fact.fact_id,)
    assert "Volkswagen Tiguan 2021款 R 藍色" in output.text
    assert "118.8萬" not in output.text


def test_o2_wrong_object_id_rejected():
    with pytest.raises(ValueError, match="OBJECT_ID"):
        admit_exact_object_title(CAPTURE, requested_object_id="4806398",
                                 expected_capture_hash=CAPTURE_HASH)


def test_o3_generic_page_substitution_rejected(tmp_path):
    path = _synthetic_capture(tmp_path, extracted_text="Volkswagen Tiguan R 型號介紹")
    with pytest.raises(ValueError, match="OBJECT_ID"):
        admit_exact_object_title(path, requested_object_id="4806397",
                                 expected_capture_hash=CAPTURE_HASH)


def test_o4_search_snippet_substitution_rejected(tmp_path):
    path = _synthetic_capture(tmp_path, extractor_scope="search_snippet")
    with pytest.raises(ValueError, match="CAPTURE_SCOPE"):
        admit_exact_object_title(path, requested_object_id="4806397",
                                 expected_capture_hash=CAPTURE_HASH)


def test_o5_company_row_escalation_rejected():
    fact = _admit()
    with pytest.raises(ValueError, match="SUBJECT_SCOPE"):
        render_exact_object_title(fact, requested_object_id="4806397",
                                  requested_subject_scope="COMPANY_ROW:13")


def test_o6_listing_title_not_oem_trim_truth():
    fact = _admit()
    with pytest.raises(ValueError, match="CLAIM_SCOPE"):
        render_exact_object_title(fact, requested_object_id="4806397",
                                  requested_claim_scope="OEM_VERIFIED_TRIM")


def test_o7_cross_object_fact_injection_rejected():
    fact = _admit()
    with pytest.raises(ValueError, match="UNADMITTED"):
        render_exact_object_title(fact, requested_object_id="4806397",
                                  requested_fact_ids=(fact.fact_id, "8891:4806398:mileage"),
                                  require_all=True)


def test_o8_capture_mismatch_and_time_mismatch_rejected():
    with pytest.raises(ValueError, match="CAPTURE_HASH"):
        admit_exact_object_title(CAPTURE, requested_object_id="4806397",
                                 expected_capture_hash="0" * 64)
    with pytest.raises(ValueError, match="CAPTURE_TIME"):
        _admit(expected_capture_time="2020-01-01T00:00:00Z")


def test_o9_self_asserted_pass_rejected():
    fact = _admit()
    with pytest.raises(ValueError, match="CANDIDATE_TEXT"):
        render_exact_object_title(fact, requested_object_id="4806397",
                                  candidate_text="PUBLIC_COPY_ADMISSION=PASS")


def test_o10_reference_and_object_keep_distinct_scopes():
    query = VehicleConfigurationQuery(
        market="TW", model_year=2017, make="BMW", model="318i",
        generation="F30 LCI", trim="318i",
    )
    reference = admit_reference_power(query)
    object_fact = _admit()
    output = render_reference_and_object(reference, object_fact, requested_object_id="4806397")
    assert output.fact_ids == (reference.fact_id, object_fact.fact_id)
    assert "台灣 2017 BMW 318i 原廠參考規格：136 hp。" in output.text
    assert "8891 物件 S4806397" in output.text
    assert "BMW" not in output.text.split("8891 物件 S4806397", 1)[1]
