"""Server-owned media provenance gate. Similarity never grants vehicle truth."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from PIL import Image, ImageOps, UnidentifiedImageError


class MediaAdmissionError(ValueError):
    pass


class ProvenanceClass(StrEnum):
    ORIGINAL_EVIDENCE = "ORIGINAL_EVIDENCE"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    DERIVATIVE_RESIZE = "DERIVATIVE_RESIZE"
    DERIVATIVE_CROP = "DERIVATIVE_CROP"
    DERIVATIVE_TRANSCODE = "DERIVATIVE_TRANSCODE"
    AI_EDITED = "AI_EDITED"
    AI_GENERATED = "AI_GENERATED"
    COMPOSITED = "COMPOSITED"
    PROVENANCE_UNVERIFIED = "PROVENANCE_UNVERIFIED"
    SIMILARITY_UNRESOLVED = "SIMILARITY_UNRESOLVED"


class TruthEligibility(StrEnum):
    ELIGIBLE = "TRUTH_ELIGIBLE"
    FORBIDDEN = "TRUTH_FORBIDDEN"
    UNRESOLVED = "TRUTH_UNRESOLVED"


class ProducingActivity(StrEnum):
    ORIGINAL_CAPTURE = "ORIGINAL_CAPTURE"
    RESIZE = "RESIZE"
    CROP = "CROP"
    TRANSCODE = "TRANSCODE"
    AI_EDIT = "AI_EDIT"
    AI_GENERATE = "AI_GENERATE"
    COMPOSITE = "COMPOSITE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MediaAsset:
    media_asset_id: str
    raw_sha256: str
    normalized_pixel_hash: str
    perceptual_fingerprint: str
    width: int
    height: int
    mime: str
    provenance_class: ProvenanceClass
    parent_asset_id: str | None
    producing_activity: ProducingActivity
    truth_eligibility: TruthEligibility
    first_seen_at: str
    source_lineage: str
    task_lineage: str
    independent_evidence_id: str | None


class MediaAssetRepository(Protocol):
    def by_raw_hash(self, raw_sha256: str) -> MediaAsset | None: ...
    def by_id(self, media_asset_id: str) -> MediaAsset | None: ...
    def candidates(self, source_lineage: str) -> tuple[MediaAsset, ...]: ...
    def raw_for_analysis(self, media_asset_id: str) -> bytes | None: ...
    def insert_immutable(self, asset: MediaAsset, raw: bytes) -> MediaAsset: ...


class VerifiedMediaFieldExtractor(Protocol):
    def extract_verified(self, *, raw: bytes, asset: MediaAsset) -> dict[str, str]: ...


class TrustedMediaActivityIssuer:
    """The source/activity declaration must be issued outside model and caller payloads."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 32:
            raise ValueError("media activity key too short")
        self._key = key

    def issue(
        self, *, raw_sha256: str, activity: ProducingActivity,
        source_lineage: str, task_lineage: str, parent_asset_id: str | None = None,
    ) -> str:
        payload = _attestation_payload(raw_sha256, activity, source_lineage, task_lineage, parent_asset_id)
        return hmac.new(self._key, payload, hashlib.sha256).hexdigest()

    def verify(
        self, signature: str, *, raw_sha256: str, activity: ProducingActivity,
        source_lineage: str, task_lineage: str, parent_asset_id: str | None,
    ) -> None:
        expected = self.issue(
            raw_sha256=raw_sha256, activity=activity, source_lineage=source_lineage,
            task_lineage=task_lineage, parent_asset_id=parent_asset_id,
        )
        if not hmac.compare_digest(signature, expected):
            raise MediaAdmissionError("MEDIA_ACTIVITY_ATTESTATION_INVALID")


def _attestation_payload(
    raw_sha256: str, activity: ProducingActivity, source_lineage: str,
    task_lineage: str, parent_asset_id: str | None,
) -> bytes:
    return json.dumps(
        [raw_sha256, activity.value, source_lineage, task_lineage, parent_asset_id],
        separators=(",", ":"),
    ).encode()


@dataclass(frozen=True)
class MediaAdmission:
    asset: MediaAsset
    exact_duplicate: bool
    new_independent_evidence: bool
    workbench_history_allowed: bool


@dataclass(frozen=True)
class MediaFieldDelta:
    media_asset_id: str
    independent_evidence_id: str
    verified_fields: dict[str, str]


def _image(raw: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MediaAdmissionError("MEDIA_IMAGE_UNREADABLE") from exc


def canonical_image_mime(raw: bytes) -> str:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            mime = Image.MIME.get(image.format)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise MediaAdmissionError("MEDIA_IMAGE_UNREADABLE") from exc
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise MediaAdmissionError("MEDIA_MIME_UNSUPPORTED")
    return mime


def _fingerprints(image: Image.Image) -> tuple[str, str]:
    pixels = image.tobytes()
    normalized = hashlib.sha256(
        image.width.to_bytes(4, "big") + image.height.to_bytes(4, "big") + pixels
    ).hexdigest()
    grid = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    values = grid.tobytes()
    bits = sum(
        (1 << (row * 8 + col))
        for row in range(8) for col in range(8)
        if values[row * 9 + col] > values[row * 9 + col + 1]
    )
    return normalized, f"{bits:016x}"


def validate_asset_readback(asset: MediaAsset, raw: bytes) -> None:
    if asset.media_asset_id != "media:" + asset.raw_sha256 or (
        hashlib.sha256(raw).hexdigest() != asset.raw_sha256
    ):
        raise MediaAdmissionError("MEDIA_RAW_READBACK_INVALID")
    image = _image(raw)
    normalized, fingerprint = _fingerprints(image)
    if (asset.width, asset.height, asset.mime) != (
        image.width, image.height, canonical_image_mime(raw),
    ) or (asset.normalized_pixel_hash, asset.perceptual_fingerprint) != (
        normalized, fingerprint,
    ):
        raise MediaAdmissionError("MEDIA_METADATA_READBACK_INVALID")


def _visual_relation(image: Image.Image, other: Image.Image) -> ProvenanceClass | None:
    # A strict pixel check confirms resampling/transcoding. Hash proximity alone never merges.
    ratio_delta = abs(image.width / image.height - other.width / other.height)
    if ratio_delta < 0.003:
        small = image.resize((64, 64), Image.Resampling.LANCZOS)
        baseline = other.resize((64, 64), Image.Resampling.LANCZOS)
        left, right = small.tobytes(), baseline.tobytes()
        mean_error = sum(abs(a - b) for a, b in zip(left, right, strict=True)) / len(left)
        if mean_error <= 3.0:
            return (
                ProvenanceClass.DERIVATIVE_RESIZE
                if image.size != other.size else ProvenanceClass.DERIVATIVE_TRANSCODE
            )
    # Crop confirmation is exact pixel containment only; resampled crops remain unresolved.
    if (image.width <= other.width and image.height <= other.height and image.size != other.size
        and image.width * image.height <= 1_000_000 and other.width * other.height <= 4_000_000):
        if other.crop((0, 0, image.width, image.height)).tobytes() == image.tobytes():
            return ProvenanceClass.DERIVATIVE_CROP
        # Scan exact rows to support arbitrary crop offsets without perceptual false merges.
        first_row = image.crop((0, 0, image.width, 1)).tobytes()
        for y in range(other.height - image.height + 1):
            for x in range(other.width - image.width + 1):
                if other.crop((x, y, x + image.width, y + 1)).tobytes() == first_row:
                    if other.crop((x, y, x + image.width, y + image.height)).tobytes() == image.tobytes():
                        return ProvenanceClass.DERIVATIVE_CROP
    return None


class MediaAdmissionGate:
    def __init__(self, repository: MediaAssetRepository, issuer: TrustedMediaActivityIssuer) -> None:
        self.repository = repository
        self.issuer = issuer

    def ingest(
        self, *, raw: bytes, mime: str, activity: ProducingActivity,
        source_lineage: str, task_lineage: str, attestation: str,
        parent_asset_id: str | None = None,
    ) -> MediaAdmission:
        raw_hash = hashlib.sha256(raw).hexdigest()
        self.issuer.verify(
            attestation, raw_sha256=raw_hash, activity=activity,
            source_lineage=source_lineage, task_lineage=task_lineage,
            parent_asset_id=parent_asset_id,
        )
        existing = self.repository.by_raw_hash(raw_hash)
        if existing is not None:
            if existing.source_lineage != source_lineage:
                raise MediaAdmissionError("MEDIA_SOURCE_LINEAGE_CONFLICT")
            return MediaAdmission(existing, True, False, False)
        image = _image(raw)
        if mime != canonical_image_mime(raw) or not source_lineage or not task_lineage:
            raise MediaAdmissionError("MEDIA_SCOPE_OR_MIME_INVALID")
        normalized, fingerprint = _fingerprints(image)
        asset_id = f"media:{raw_hash}"
        if parent_asset_id == asset_id:
            raise MediaAdmissionError("MEDIA_LINEAGE_CYCLE")
        parent = self.repository.by_id(parent_asset_id) if parent_asset_id else None
        if parent_asset_id and parent is None:
            raise MediaAdmissionError("MEDIA_PARENT_MISSING")
        if parent and parent.source_lineage != source_lineage:
            raise MediaAdmissionError("MEDIA_PARENT_SCOPE_MISMATCH")
        visual_parent: MediaAsset | None = None
        visual_relation: ProvenanceClass | None = None
        similar_unresolved = False
        for candidate in self.repository.candidates(source_lineage):
            candidate_raw = self.repository.raw_for_analysis(candidate.media_asset_id)
            if candidate_raw is None:
                continue
            relation = _visual_relation(image, _image(candidate_raw))
            if relation is not None:
                visual_parent, visual_relation = candidate, relation
                break
            distance = (int(fingerprint, 16) ^ int(candidate.perceptual_fingerprint, 16)).bit_count()
            similar_unresolved |= distance <= 6
        creative = {
            ProducingActivity.AI_EDIT: ProvenanceClass.AI_EDITED,
            ProducingActivity.AI_GENERATE: ProvenanceClass.AI_GENERATED,
            ProducingActivity.COMPOSITE: ProvenanceClass.COMPOSITED,
        }
        if activity in creative:
            provenance = creative[activity]
            eligibility = TruthEligibility.FORBIDDEN
        elif parent and parent.truth_eligibility is TruthEligibility.FORBIDDEN:
            provenance = {
                ProducingActivity.CROP: ProvenanceClass.DERIVATIVE_CROP,
                ProducingActivity.RESIZE: ProvenanceClass.DERIVATIVE_RESIZE,
                ProducingActivity.TRANSCODE: ProvenanceClass.DERIVATIVE_TRANSCODE,
            }.get(activity, ProvenanceClass.PROVENANCE_UNVERIFIED)
            eligibility = TruthEligibility.FORBIDDEN
        elif parent or visual_parent:
            if parent and visual_parent and parent.media_asset_id != visual_parent.media_asset_id:
                raise MediaAdmissionError("MEDIA_PARENT_CONFLICT")
            parent = parent or visual_parent
            provenance = visual_relation or ProvenanceClass.SIMILARITY_UNRESOLVED
            confirmed = visual_relation and parent.truth_eligibility is TruthEligibility.ELIGIBLE
            eligibility = TruthEligibility.ELIGIBLE if confirmed else TruthEligibility.UNRESOLVED
        elif similar_unresolved:
            provenance, eligibility = ProvenanceClass.SIMILARITY_UNRESOLVED, TruthEligibility.UNRESOLVED
        elif activity is ProducingActivity.ORIGINAL_CAPTURE:
            provenance, eligibility = ProvenanceClass.ORIGINAL_EVIDENCE, TruthEligibility.ELIGIBLE
        else:
            provenance, eligibility = ProvenanceClass.PROVENANCE_UNVERIFIED, TruthEligibility.UNRESOLVED
        if parent and parent.truth_eligibility is TruthEligibility.FORBIDDEN:
            eligibility = TruthEligibility.FORBIDDEN
        root = parent.independent_evidence_id if parent else (
            asset_id if eligibility is TruthEligibility.ELIGIBLE else None
        )
        asset = MediaAsset(
            media_asset_id=asset_id, raw_sha256=raw_hash,
            normalized_pixel_hash=normalized, perceptual_fingerprint=fingerprint,
            width=image.width, height=image.height, mime=mime,
            provenance_class=provenance, parent_asset_id=parent.media_asset_id if parent else None,
            producing_activity=activity, truth_eligibility=eligibility,
            first_seen_at=datetime.now(UTC).isoformat(), source_lineage=source_lineage,
            task_lineage=task_lineage, independent_evidence_id=root,
        )
        inserted = self.repository.insert_immutable(asset, raw)
        newly_recorded = inserted == asset
        return MediaAdmission(
            inserted, not newly_recorded, newly_recorded and root == asset_id,
            newly_recorded and root == asset_id,
        )


def require_truth_eligible(assets: tuple[MediaAsset, ...]) -> tuple[MediaAsset, ...]:
    if any(asset.truth_eligibility is not TruthEligibility.ELIGIBLE for asset in assets):
        raise MediaAdmissionError("MEDIA_NOT_TRUTH_ELIGIBLE")
    return assets


def independent_evidence_count(assets: tuple[MediaAsset, ...]) -> int:
    eligible = require_truth_eligible(assets)
    if any(asset.independent_evidence_id is None for asset in eligible):
        raise MediaAdmissionError("MEDIA_EVIDENCE_LINEAGE_MISSING")
    return len({asset.independent_evidence_id for asset in eligible})


def extract_truth_fields(
    repository: MediaAssetRepository, extractor: VerifiedMediaFieldExtractor,
    asset: MediaAsset,
) -> MediaFieldDelta:
    require_truth_eligible((asset,))
    raw = repository.raw_for_analysis(asset.media_asset_id)
    if raw is None or hashlib.sha256(raw).hexdigest() != asset.raw_sha256:
        raise MediaAdmissionError("MEDIA_RAW_READBACK_INVALID")
    if asset.independent_evidence_id is None:
        raise MediaAdmissionError("MEDIA_EVIDENCE_LINEAGE_MISSING")
    fields = extractor.extract_verified(raw=raw, asset=asset)
    return MediaFieldDelta(asset.media_asset_id, asset.independent_evidence_id, fields)
