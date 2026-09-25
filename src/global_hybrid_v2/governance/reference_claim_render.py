"""Stage 1 reference-only admission and constrained text rendering.

This module never accepts a user/model-provided vehicle assertion for rendering.
It reads the packaged Library snapshot through its existing provider, admits one
bounded reference fact, then renders only a fixed versioned template.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from pathlib import Path
from uuid import uuid4

from global_hybrid_v2.adapters.file_vehicle_configuration import FileVehicleConfigurationProvider
from global_hybrid_v2.contracts import VehicleConfigurationQuery
from global_hybrid_v2.domains.vehicle_configuration import VehicleConfigurationLookupState
from global_hybrid_v2.governance.exact_object_source import (
    ExactObjectSourceReceiptV1,
    readback_current_exact_object,
)

_RESOURCE = "data/vehicle_configuration_current.json"
_TEMPLATE = "reference_power_v1"
_SAFE_LABEL = re.compile(r"^[\w][\w .-]{0,48}$", re.UNICODE)
_issued: dict[str, ReferenceFact] = {}
_object_issued: dict[str, ExactObjectFact] = {}
_PINNED_OBJECT = "4806397"
_PINNED_CAPTURE_HASH = "9fa891ba0fb328f743c86a2de20c760a78df0752d58ca52f3b91d702a81fbea7"
_OBJECT_TITLE_TEMPLATE = "exact_object_title_v1"


@dataclass(frozen=True)
class ReferenceFact:
    schema_version: int
    fact_id: str
    subject_scope: str
    assertion: str
    source_class: str
    source_ref: str
    source_version: str
    readback_ref: str
    provenance: tuple[str, ...]
    claim_scope: str
    freshness_class: str
    admission_state: str
    admission_reason: str
    market: str
    model_year: int
    make: str
    model: str
    power_hp: int
    _issue_token: str


@dataclass(frozen=True)
class RenderedReference:
    template_id: str
    text: str
    fact_ids: tuple[str, ...]
    source_readback_ref: str


@dataclass(frozen=True)
class ExactObjectFact:
    schema_version: int
    fact_id: str
    assertion: str
    source_class: str
    source_ref: str
    source_version: str
    readback_ref: str
    provenance: tuple[str, ...]
    claim_scope: str
    freshness_class: str
    admission_state: str
    admission_reason: str
    subject_scope: str
    object_platform: str
    object_id: str
    object_canonical_ref: str
    object_capture_ref: str
    object_capture_hash: str
    capture_time: str
    source_field: str
    source_location: str
    _issue_token: str


def _readback() -> tuple[dict, str]:
    raw = resources.files("global_hybrid_v2").joinpath(_RESOURCE).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _safe_label(value: str) -> bool:
    return bool(_SAFE_LABEL.fullmatch(value))


def admit_reference_power(query: VehicleConfigurationQuery) -> ReferenceFact:
    """Admit only a uniquely matched, provenance-backed packaged reference power fact."""
    provider = FileVehicleConfigurationProvider.from_package_resource()
    source, readback = _readback()
    result = provider.lookup(query)
    if (
        result.state is not VehicleConfigurationLookupState.HIT
        or len(result.configurations) != 1
        or source.get("snapshot_id") != provider.snapshot_id
        or source.get("source_revision") != provider.source_revision
    ):
        raise ValueError("REFERENCE_SOURCE_NOT_ADMISSIBLE")
    config = result.configurations[0]
    if not any(item == config.model_dump(mode="json") for item in source.get("configurations", [])):
        raise ValueError("REFERENCE_SOURCE_READBACK_MISMATCH")
    refs = config.primary_source_pointers
    if not refs or len(refs) != 1 or not refs[0].strip() or not result.provenance:
        raise ValueError("REFERENCE_SOURCE_PROVENANCE_MISSING")
    power = config.powertrain.get("power_hp")
    if isinstance(power, bool) or not isinstance(power, int) or not 1 <= power <= 3000:
        raise ValueError("REFERENCE_POWER_NOT_TYPED")
    if config.conflict_state != "NO_CONFLICT":
        raise ValueError("REFERENCE_SOURCE_CONFLICT")
    if config.market != "TW" or not all(_safe_label(value) for value in (config.make, config.model)):
        raise ValueError("REFERENCE_SUBJECT_UNSAFE")
    if config.model_year != query.model_year:
        raise ValueError("REFERENCE_SUBJECT_MISMATCH")
    subject = f"{config.market}:{config.model_year}:{config.make}:{config.model}:REFERENCE"
    fact_id = f"reference:{config.configuration_id}:{config.model_year}:power_hp"
    token = uuid4().hex
    fact = ReferenceFact(
        schema_version=1,
        fact_id=fact_id,
        subject_scope=subject,
        assertion=f"{power} hp",
        source_class="REFERENCE",
        source_ref=refs[0],
        source_version=provider.snapshot_id,
        readback_ref=readback,
        provenance=tuple(result.provenance),
        claim_scope="FACTORY_MODEL_REFERENCE_ONLY",
        freshness_class=f"REFERENCE_LAST_VERIFIED:{config.last_verified}",
        admission_state="BOUNDED",
        admission_reason="SINGLE_MATCHED_LIBRARY_REFERENCE_WITH_SOURCE_READBACK",
        market=config.market,
        model_year=config.model_year,
        make=config.make,
        model=config.model,
        power_hp=power,
        _issue_token=token,
    )
    _issued[token] = fact
    return fact


def render_reference_power(
    fact: ReferenceFact,
    *,
    template_id: str = _TEMPLATE,
    requested_subject_scope: str | None = None,
    requested_fact_ids: tuple[str, ...] | None = None,
    require_all: bool = False,
    candidate_text: str | None = None,
) -> RenderedReference:
    """Render one approved reference fact; no free-text factual slot exists."""
    if candidate_text is not None:
        raise ValueError("CANDIDATE_TEXT_NOT_ACCEPTED")
    if template_id != _TEMPLATE:
        raise ValueError("TEMPLATE_NOT_ADMITTED")
    if _issued.get(fact._issue_token) != fact or fact.admission_state != "BOUNDED":
        raise ValueError("FACT_NOT_ADMITTED")
    if requested_subject_scope is not None and requested_subject_scope != fact.subject_scope:
        raise ValueError("SUBJECT_SCOPE_ESCALATION")
    _, current_readback = _readback()
    if current_readback != fact.readback_ref:
        raise ValueError("SOURCE_READBACK_STALE")
    requested = requested_fact_ids if requested_fact_ids is not None else (fact.fact_id,)
    if require_all and any(item != fact.fact_id for item in requested):
        raise ValueError("UNADMITTED_FACT_REQUESTED")
    if fact.fact_id not in requested:
        raise ValueError("NO_ADMITTED_FACT_REQUESTED")
    text = f"台灣 {fact.model_year} {fact.make} {fact.model} 原廠參考規格：{fact.power_hp} hp。"
    return RenderedReference(
        template_id=_TEMPLATE,
        text=text,
        fact_ids=(fact.fact_id,),
        source_readback_ref=fact.readback_ref,
    )


def _trusted_capture_path() -> Path:
    return Path(__file__).resolve().parents[3] / "validation/stage2/8891-4806397-capture.json"


def _capture_readback(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def admit_exact_object_title(
    capture_path: str | Path,
    *,
    requested_object_id: str,
    expected_capture_hash: str,
    expected_capture_time: str | None = None,
) -> ExactObjectFact:
    """Admit only the pinned, readable exact-object title captured from 8891.

    The caller's expected hash is an additional check, never the trust anchor.
    This local candidate has exactly one pinned capture; it is not a live adapter.
    """
    path = Path(capture_path).resolve()
    capture, actual_hash = _capture_readback(path)
    if capture.get("extractor_scope") != "rendered_markdown_text" or capture.get("read_status") != "READABLE":
        raise ValueError("CAPTURE_SCOPE_NOT_READABLE_DETAIL_PAGE")
    body = capture.get("extracted_text")
    if not isinstance(body, str) or not re.search(r"編號：S\d+", body):
        raise ValueError("OBJECT_ID_NOT_IN_DETAIL_BODY")
    if requested_object_id != _PINNED_OBJECT:
        raise ValueError("OBJECT_ID_NOT_PINNED")
    if path != _trusted_capture_path().resolve():
        raise ValueError("CAPTURE_PATH_NOT_TRUSTED")
    if actual_hash != _PINNED_CAPTURE_HASH or expected_capture_hash != actual_hash:
        raise ValueError("CAPTURE_HASH_MISMATCH")
    if capture.get("source_owner") != "8891" or capture.get("object_id_observed") != requested_object_id:
        raise ValueError("OBJECT_ID_MISMATCH")
    if len(re.findall(rf"編號：S{re.escape(requested_object_id)}(?!\d)", body)) != 1:
        raise ValueError("OBJECT_ID_MISMATCH")
    retrieved_url = capture.get("retrieved_url")
    canonical_url = capture.get("canonical_url")
    if (
        not isinstance(retrieved_url, str) or not isinstance(canonical_url, str)
        or
        retrieved_url != f"https://auto.8891.com.tw/usedauto-userInfos-{requested_object_id}.html"
        or canonical_url != f"https://auto.8891.com.tw/usedauto-infos-{requested_object_id}.html"
    ):
        raise ValueError("OBJECT_ID_URL_MISMATCH")
    capture_time = capture.get("capture_time_utc")
    if not isinstance(capture_time, str) or expected_capture_time not in (None, capture_time):
        raise ValueError("CAPTURE_TIME_MISMATCH")
    try:
        datetime.fromisoformat(capture_time.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("CAPTURE_TIME_INVALID") from exc
    titles = re.findall(r"(?m)^# ([^\r\n]+)$", body)
    if len(titles) != 1 or len(titles[0]) > 100:
        raise ValueError("OBJECT_TITLE_UNRESOLVED")
    title = titles[0]
    token = uuid4().hex
    fact = ExactObjectFact(
        schema_version=1,
        fact_id=f"8891:{requested_object_id}:listing_title:{actual_hash[:12]}",
        assertion=title,
        source_class="EXACT_OBJECT",
        source_ref=retrieved_url,
        source_version=capture_time,
        readback_ref=actual_hash,
        provenance=("8891 detail-page rendered text", "TinyFish fetch-content", actual_hash),
        claim_scope="PLATFORM_LISTING_TITLE_ONLY",
        freshness_class="CAPTURED_AT_NOT_LIVE_CURRENT_OFFER",
        admission_state="BOUNDED",
        admission_reason="EXACT_OBJECT_ID_AND_PINNED_CAPTURE_READBACK_MATCH",
        subject_scope="EXACT_OBJECT",
        object_platform="8891",
        object_id=requested_object_id,
        object_canonical_ref=canonical_url,
        object_capture_ref=str(path),
        object_capture_hash=actual_hash,
        capture_time=capture_time,
        source_field="listing_title",
        source_location="rendered detail body: # heading",
        _issue_token=token,
    )
    _object_issued[token] = fact
    return fact


def render_exact_object_title(
    fact: ExactObjectFact,
    *,
    requested_object_id: str,
    template_id: str = _OBJECT_TITLE_TEMPLATE,
    requested_subject_scope: str | None = None,
    requested_claim_scope: str | None = None,
    requested_fact_ids: tuple[str, ...] | None = None,
    require_all: bool = False,
    candidate_text: str | None = None,
) -> RenderedReference:
    if candidate_text is not None:
        raise ValueError("CANDIDATE_TEXT_NOT_ACCEPTED")
    if template_id != _OBJECT_TITLE_TEMPLATE:
        raise ValueError("TEMPLATE_NOT_ADMITTED")
    if _object_issued.get(fact._issue_token) != fact or fact.admission_state != "BOUNDED":
        raise ValueError("FACT_NOT_ADMITTED")
    if requested_object_id != fact.object_id or requested_subject_scope not in (None, "EXACT_OBJECT"):
        raise ValueError("SUBJECT_SCOPE_ESCALATION")
    if requested_claim_scope not in (None, "PLATFORM_LISTING_TITLE_ONLY"):
        raise ValueError("CLAIM_SCOPE_ESCALATION")
    if _capture_readback(Path(fact.object_capture_ref))[1] != fact.object_capture_hash:
        raise ValueError("CAPTURE_HASH_STALE")
    requested = requested_fact_ids if requested_fact_ids is not None else (fact.fact_id,)
    if require_all and any(item != fact.fact_id for item in requested):
        raise ValueError("UNADMITTED_FACT_REQUESTED")
    if fact.fact_id not in requested:
        raise ValueError("NO_ADMITTED_FACT_REQUESTED")
    captured_date = fact.capture_time[:10]
    text = f"8891 物件 S{fact.object_id} 於 {captured_date} 擷取的頁面標題：{fact.assertion}。"
    return RenderedReference(
        template_id=_OBJECT_TITLE_TEMPLATE,
        text=text,
        fact_ids=(fact.fact_id,),
        source_readback_ref=fact.object_capture_hash,
    )


def render_reference_and_object(
    reference: ReferenceFact,
    object_fact: ExactObjectFact,
    *,
    requested_object_id: str,
) -> RenderedReference:
    """Compose two independently scoped rendered lines; never join their subjects."""
    first = render_reference_power(reference)
    second = render_exact_object_title(object_fact, requested_object_id=requested_object_id)
    return RenderedReference(
        template_id="independent_reference_and_exact_object_v1",
        text=f"{first.text}\n{second.text}",
        fact_ids=first.fact_ids + second.fact_ids,
        source_readback_ref=f"{first.source_readback_ref}:{second.source_readback_ref}",
    )


def admit_exact_object_observation(receipt: ExactObjectSourceReceiptV1) -> ExactObjectFact:
    """Consume a fresh same-task exact-object source receipt, not its page as vehicle truth."""
    if not readback_current_exact_object(receipt).ok:
        raise ValueError("CURRENT_RECEIPT_REQUIRED")
    if (
        receipt.content_hash is None or receipt.capture_time is None
        or receipt.raw_capture_ref is None or receipt.final_url is None
    ):
        raise ValueError("CURRENT_RECEIPT_INCOMPLETE")
    token = uuid4().hex
    fact = ExactObjectFact(
        schema_version=1,
        fact_id=f"{receipt.platform}:{receipt.requested_object_id}:capture:{receipt.content_hash[:12]}",
        assertion=f"S{receipt.requested_object_id} detail page captured",
        source_class="EXACT_OBJECT",
        source_ref=receipt.final_url,
        source_version=receipt.source_version_or_etag or receipt.capture_time,
        readback_ref=receipt.content_hash,
        provenance=(receipt.receipt_ref, receipt.raw_capture_ref),
        claim_scope="PLATFORM_OBJECT_CAPTURE_ONLY",
        freshness_class="CURRENT_CAPTURE",
        admission_state="BOUNDED",
        admission_reason="CURRENT_EXACT_OBJECT_RECEIPT_READBACK_PASS",
        subject_scope="EXACT_OBJECT",
        object_platform=receipt.platform,
        object_id=receipt.requested_object_id,
        object_canonical_ref=receipt.requested_canonical_url,
        object_capture_ref=receipt.raw_capture_ref,
        object_capture_hash=receipt.content_hash,
        capture_time=receipt.capture_time,
        source_field="exact_object_page_observed",
        source_location="raw HTML canonical + og:url",
        _issue_token=token,
    )
    _object_issued[token] = fact
    return fact


def render_exact_object_observation(
    fact: ExactObjectFact,
    *,
    requested_object_id: str,
    requested_subject_scope: str | None = None,
) -> RenderedReference:
    if _object_issued.get(fact._issue_token) != fact or fact.claim_scope != "PLATFORM_OBJECT_CAPTURE_ONLY":
        raise ValueError("FACT_NOT_ADMITTED")
    if requested_object_id != fact.object_id or requested_subject_scope not in (None, "EXACT_OBJECT"):
        raise ValueError("SUBJECT_SCOPE_ESCALATION")
    receipt = ExactObjectSourceReceiptV1(**json.loads(Path(fact.provenance[0]).read_text(encoding="utf-8")))
    if not readback_current_exact_object(receipt).ok or receipt.content_hash != fact.object_capture_hash:
        raise ValueError("CURRENT_RECEIPT_REQUIRED")
    text = f"於 {fact.capture_time[:10]} 讀取到 8891 物件 S{fact.object_id} 的詳細頁。"
    return RenderedReference(
        template_id="exact_object_capture_observation_v1",
        text=text,
        fact_ids=(fact.fact_id,),
        source_readback_ref=fact.object_capture_hash,
    )
