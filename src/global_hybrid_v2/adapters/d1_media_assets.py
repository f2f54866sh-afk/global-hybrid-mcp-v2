"""D1 control-plane client for immutable media assets; no vehicle truth store."""
from __future__ import annotations

import base64
import json
from dataclasses import asdict
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from global_hybrid_v2.creative_media import CreativeMediaRef
from global_hybrid_v2.media_admission import (
    MediaAdmissionError,
    MediaAsset,
    ProducingActivity,
    ProvenanceClass,
    ProvenanceConfidence,
    TruthEligibility,
    validate_asset_readback,
)


class D1MediaAssetRepository:
    def __init__(self, *, base_url: str, read_secret: str, write_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("D1 media control endpoint must use https")
        if not read_secret or not write_secret:
            raise ValueError("D1 media control secrets required")
        self.base_url = base_url.rstrip("/")
        self.read_secret = read_secret
        self.write_secret = write_secret

    def _request(self, path: str, *, write: bool = False, body: dict | None = None) -> dict:
        request = Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.write_secret if write else self.read_secret}",
                "Content-Type": "application/json",
            },
            method="POST" if write else "GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
        except Exception as exc:
            raise MediaAdmissionError("D1_MEDIA_REGISTRY_UNAVAILABLE") from exc
        if result.get("state") == "HOLD":
            raise MediaAdmissionError(result.get("blocker", "D1_MEDIA_REGISTRY_HOLD"))
        return result

    def _lookup(self, **query: str) -> tuple[MediaAsset | None, bytes | None]:
        result = self._request("/internal/media-asset/read?" + urlencode(query))
        if result.get("state") == "MISS":
            return None, None
        if result.get("state") != "HIT":
            raise MediaAdmissionError("D1_MEDIA_READBACK_INVALID")
        fields = result["asset"]
        asset = MediaAsset(**{
            **fields,
            "provenance_class": ProvenanceClass(fields["provenance_class"]),
            "producing_activity": ProducingActivity(fields["producing_activity"]),
            "truth_eligibility": TruthEligibility(fields["truth_eligibility"]),
            "provenance_confidence": ProvenanceConfidence(fields["provenance_confidence"]),
        })
        request = Request(
            self.base_url + "/internal/media-object/read?" + urlencode({"object_key": asset.object_key}),
            headers={"Authorization": f"Bearer {self.read_secret}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                raw = response.read()
        except Exception as exc:
            raise MediaAdmissionError("MEDIA_OBJECT_MISSING") from exc
        validate_asset_readback(asset, raw)
        return asset, raw

    def by_raw_hash(self, raw_sha256: str) -> MediaAsset | None:
        return self._lookup(raw_sha256=raw_sha256)[0]

    def by_id(self, media_asset_id: str) -> MediaAsset | None:
        return self._lookup(media_asset_id=media_asset_id)[0]

    def raw_for_analysis(self, media_asset_id: str) -> bytes | None:
        return self._lookup(media_asset_id=media_asset_id)[1]

    def candidates(self, source_lineage: str) -> tuple[MediaAsset, ...]:
        result = self._request("/internal/media-asset/candidates?" + urlencode({
            "source_lineage": source_lineage,
        }))
        if result.get("state") != "HIT" or result.get("truncated"):
            raise MediaAdmissionError("D1_MEDIA_CANDIDATES_INVALID")
        return tuple(self.by_id(asset_id) for asset_id in result["media_asset_ids"])

    def insert_immutable(self, asset: MediaAsset, raw: bytes) -> MediaAsset:
        result = self._request(
            "/internal/control/media-asset", write=True,
            body={**asdict(asset), "raw_base64": base64.b64encode(raw).decode()},
        )
        if result.get("state") not in {"RECORDED", "EXACT_DUPLICATE"}:
            raise MediaAdmissionError("D1_MEDIA_WRITE_INVALID")
        readback, read_raw = self._lookup(media_asset_id=result["media_asset_id"])
        if readback is None or readback.raw_sha256 != asset.raw_sha256 or read_raw is None:
            raise MediaAdmissionError("D1_MEDIA_READBACK_MISMATCH")
        return readback


class D1CreativeMediaRepository:
    def __init__(self, *, base_url: str, read_secret: str, write_secret: str) -> None:
        self.client = D1MediaAssetRepository(
            base_url=base_url, read_secret=read_secret, write_secret=write_secret,
        )

    def insert_immutable(self, ref: CreativeMediaRef) -> CreativeMediaRef:
        result = self.client._request(
            "/internal/control/creative-media-ref", write=True,
            body={
                "creative_ref_id": ref.creative_ref_id,
                "media_asset_id": ref.media_asset_id,
                "vehicle_instance_id": ref.vehicle_instance_id,
                "target_column": ref.target_column,
                "channels": list(ref.channels),
            },
        )
        if result.get("state") not in {"RECORDED", "IDEMPOTENT_SUCCESS"}:
            raise MediaAdmissionError("D1_CREATIVE_WRITE_INVALID")
        readback = self.client._request(
            "/internal/creative-media-ref/read?" + urlencode({"creative_ref_id": ref.creative_ref_id}),
        )
        if readback.get("state") != "HIT":
            raise MediaAdmissionError("D1_CREATIVE_READBACK_MISSING")
        row = readback["ref"]
        if (row["creative_ref_id"], row["media_asset_id"], row["vehicle_instance_id"],
            row["target_column"], tuple(row["channels"])) != (
            ref.creative_ref_id, ref.media_asset_id, ref.vehicle_instance_id,
            ref.target_column, ref.channels,
        ):
            raise MediaAdmissionError("D1_CREATIVE_READBACK_MISMATCH")
        return CreativeMediaRef(
            creative_ref_id=ref.creative_ref_id, media_asset_id=ref.media_asset_id,
            vehicle_instance_id=ref.vehicle_instance_id, target_column=ref.target_column,
            channels=ref.channels, admitted_at=row["admitted_at"],
        )
