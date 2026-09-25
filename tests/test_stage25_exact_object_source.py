"""Stage 2.5 receipt tests; R1 uses a live bounded HTTP read, others synthetic."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from global_hybrid_v2.governance.exact_object_source import (
    ExactObjectRequest,
    HttpResponse,
    fetch_exact_object,
    readback_current_exact_object,
    readback_exact_object,
)
from global_hybrid_v2.governance.reference_claim_render import (
    admit_exact_object_observation,
    render_exact_object_observation,
)

OBJECT = "4806397"
URL = f"https://auto.8891.com.tw/usedauto-userInfos-{OBJECT}.html"
CANONICAL = f"https://auto.8891.com.tw/usedauto-infos-{OBJECT}.html"


def _request(object_id=OBJECT):
    return ExactObjectRequest(platform="8891", object_id=object_id,
                              canonical_object_ref=f"https://auto.8891.com.tw/usedauto-infos-{object_id}.html",
                              task_id="stage25-task", request_id="stage25-request",
                              request_time=datetime.now(UTC))


def _html(object_id=OBJECT):
    return (f'<html><head><link rel="canonical" href="https://auto.8891.com.tw/usedauto-infos-{object_id}.html">'
            f'<meta property="og:url" content="https://auto.8891.com.tw/usedauto-infos-{object_id}.html">'
            '<title>listing capture</title></head><body>detail</body></html>').encode()


def _transport(body=None, *, final_url=URL, status=200, content_type="text/html"):
    def fetch(url):
        return HttpResponse(status=status, final_url=final_url, body=_html() if body is None else body,
                            content_type=content_type, etag=None)
    return fetch


def test_r1_live_current_exact_fetch_and_readback(tmp_path):
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path)
    assert receipt.fetch_status == "PASS"
    assert receipt.identity_match is True
    assert receipt.requested_object_id == receipt.observed_object_id == OBJECT
    assert receipt.final_url == URL
    assert receipt.content_hash and receipt.capture_time
    assert readback_exact_object(receipt).ok


def test_r2_wrong_object_denied(tmp_path):
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path,
                                 transport=_transport(_html("4806398")))
    assert receipt.fetch_status == "OBJECT_MISMATCH"
    assert receipt.identity_match is False


def test_r3_fetch_failed_does_not_promote_old_capture(tmp_path):
    old = fetch_exact_object(_request(), capture_dir=tmp_path, transport=_transport())
    def failure(_url):
        raise OSError("synthetic fetch failed")
    current = fetch_exact_object(_request(), capture_dir=tmp_path, transport=failure)
    assert current.fetch_status == "FETCH_FAILED"
    assert current.freshness_state == "FETCH_FAILED"
    assert current.raw_capture_ref is None
    assert readback_exact_object(old).ok
    assert not readback_current_exact_object(old).ok
    with pytest.raises(ValueError, match="CURRENT_RECEIPT"):
        admit_exact_object_observation(current)


def test_r4_stale_historical_capture_cannot_be_current(tmp_path):
    then = datetime.now(UTC) - timedelta(days=1)
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path,
                                 transport=_transport(), clock=lambda: then)
    assert receipt.freshness_state == "STALE_CAPTURE"
    assert readback_exact_object(receipt).ok
    with pytest.raises(ValueError, match="CURRENT_RECEIPT"):
        admit_exact_object_observation(receipt)


def test_r5_redirected_generic_page_denied(tmp_path):
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path,
                                 transport=_transport(b"<html>category Tiguan</html>",
                                                      final_url="https://auto.8891.com.tw/usedauto.html"))
    assert receipt.fetch_status == "OBJECT_MISMATCH"


def test_r6_search_result_substitution_denied(tmp_path):
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path,
                                 transport=_transport(b"8891 4806397 price", content_type="text/plain"))
    assert receipt.fetch_status != "PASS"


def test_r7_tampered_raw_capture_fails_readback(tmp_path):
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path, transport=_transport())
    Path(receipt.raw_capture_ref).write_bytes(b"tampered")
    assert not readback_exact_object(receipt).ok


def test_r8_refresh_preserves_old_lineage(tmp_path):
    first = fetch_exact_object(_request(), capture_dir=tmp_path, transport=_transport())
    second = fetch_exact_object(_request(), capture_dir=tmp_path,
                                transport=_transport(_html() + b"<!-- new capture -->"))
    assert first.content_hash != second.content_hash
    assert first.raw_capture_ref != second.raw_capture_ref
    assert readback_exact_object(first).ok and readback_exact_object(second).ok
    assert not readback_current_exact_object(first).ok
    assert readback_current_exact_object(second).ok


def test_r9_receipt_only_supports_exact_object_observation(tmp_path):
    receipt = fetch_exact_object(_request(), capture_dir=tmp_path, transport=_transport())
    fact = admit_exact_object_observation(receipt)
    assert fact.subject_scope == "EXACT_OBJECT"
    rendered = render_exact_object_observation(fact, requested_object_id=OBJECT)
    assert rendered.fact_ids == (fact.fact_id,)
    assert "公司" not in rendered.text
    with pytest.raises(ValueError, match="SUBJECT_SCOPE"):
        render_exact_object_observation(fact, requested_object_id=OBJECT,
                                        requested_subject_scope="COMPANY_ROW:13")


def test_r10_stage2_existing_tests_remain_separate():
    # R10's substantive assertion is the Stage 2 O1-O10 regression suite,
    # included in the final command. This marker prevents conflating receipts
    # with company or vehicle identity.
    assert _request().platform == "8891"
