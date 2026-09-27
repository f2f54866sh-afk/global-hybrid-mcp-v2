from __future__ import annotations

import hashlib
import io
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from global_hybrid_v2.adapters.controlled_responses import (
    ControlledSalesIngress,
    ForcedHostDispatchAdapter,
    ServerTurnContext,
)
from global_hybrid_v2.ingress_admission import (
    IngressTaskClass,
    IngressTurnTokenCodec,
    InMemoryNonceClaimStore,
)
from global_hybrid_v2.media_admission import (
    MediaAdmissionError,
    MediaAdmissionGate,
    MediaAsset,
    ProducingActivity,
    ProvenanceClass,
    TrustedMediaActivityIssuer,
    TruthEligibility,
    extract_truth_fields,
    independent_evidence_count,
    require_truth_eligible,
)
from global_hybrid_v2.trusted_workbench_intent import TrustBoundaryError, TrustedHostTaskCompiler
from tests.test_rd021_trusted_host_binding import HostResolver, compiler


class MemoryRegistry:
    def __init__(self):
        self.assets: dict[str, MediaAsset] = {}
        self.raw: dict[str, bytes] = {}

    def by_raw_hash(self, raw_sha256):
        return self.assets.get(f"media:{raw_sha256}")

    def by_id(self, media_asset_id):
        return self.assets.get(media_asset_id)

    def candidates(self, source_lineage):
        return tuple(a for a in self.assets.values() if a.source_lineage == source_lineage)

    def raw_for_analysis(self, media_asset_id):
        return self.raw.get(media_asset_id)

    def insert_immutable(self, asset, raw):
        if asset.media_asset_id in self.assets:
            return self.assets[asset.media_asset_id]
        if asset.parent_asset_id:
            assert asset.parent_asset_id in self.assets
        self.assets[asset.media_asset_id] = asset
        self.raw[asset.media_asset_id] = raw
        return asset


@pytest.fixture
def kit():
    store = MemoryRegistry()
    issuer = TrustedMediaActivityIssuer(b"m" * 32)
    return store, issuer, MediaAdmissionGate(store, issuer)


def photo(size=(160, 120), shift=0, fmt="PNG", quality=94):
    image = Image.new("RGB", size)
    for y in range(size[1]):
        for x in range(size[0]):
            image.putpixel((x, y), ((x * 2 + shift) % 256, (y * 2 + shift) % 256,
                                      ((x + y) // 2 + shift) % 256))
    out = io.BytesIO()
    image.save(out, format=fmt, quality=quality)
    return out.getvalue()


def derived(raw, *, size=None, crop=None, fmt="PNG", quality=94):
    with Image.open(io.BytesIO(raw)) as image:
        if crop:
            image = image.crop(crop)
        if size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format=fmt, quality=quality)
        return out.getvalue()


def ingest(kit, raw, activity=ProducingActivity.ORIGINAL_CAPTURE, parent=None, lineage="vehicle:a"):
    _, issuer, gate = kit
    digest = hashlib.sha256(raw).hexdigest()
    signature = issuer.issue(
        raw_sha256=digest, activity=activity, source_lineage=lineage,
        task_lineage="turn:1", parent_asset_id=parent,
    )
    return gate.ingest(
        raw=raw, mime="image/jpeg" if raw.startswith(b"\xff\xd8") else "image/png",
        activity=activity, source_lineage=lineage, task_lineage="turn:1",
        parent_asset_id=parent, attestation=signature,
    )


def test_exact_bytes_return_same_id_and_no_second_history(kit):
    raw = photo()
    first = ingest(kit, raw)
    again = ingest(kit, raw)
    assert again.asset.media_asset_id == first.asset.media_asset_id
    assert again.exact_duplicate and not again.new_independent_evidence
    assert not again.workbench_history_allowed
    assert len(kit[0].assets) == 1
    with pytest.raises(MediaAdmissionError, match="MEDIA_SOURCE_LINEAGE_CONFLICT"):
        ingest(kit, raw, lineage="vehicle:other")


@pytest.mark.parametrize("transform,expected", [
    (lambda raw: derived(raw, size=(80, 60)), ProvenanceClass.DERIVATIVE_RESIZE),
    (lambda raw: derived(raw, fmt="JPEG", quality=94), ProvenanceClass.DERIVATIVE_TRANSCODE),
])
def test_confirmed_resize_or_recompression_reuses_evidence_root(kit, transform, expected):
    first = ingest(kit, photo())
    result = ingest(kit, transform(photo()), ProducingActivity.RESIZE)
    assert result.asset.provenance_class is expected
    assert result.asset.parent_asset_id == first.asset.media_asset_id
    assert result.asset.independent_evidence_id == first.asset.media_asset_id
    assert not result.new_independent_evidence
    assert independent_evidence_count((first.asset, result.asset)) == 1


def test_crop_requires_exact_visual_relation_or_stays_unresolved(kit):
    original = photo()
    root = ingest(kit, original)
    crop = derived(original, crop=(10, 8, 100, 80))
    child = ingest(kit, crop, ProducingActivity.CROP, root.asset.media_asset_id)
    assert child.asset.provenance_class is ProvenanceClass.DERIVATIVE_CROP
    assert child.asset.independent_evidence_id == root.asset.media_asset_id
    uncertain = derived(original, crop=(10, 8, 100, 80), size=(70, 50))
    unresolved = ingest(kit, uncertain, ProducingActivity.CROP, root.asset.media_asset_id)
    assert unresolved.asset.truth_eligibility is TruthEligibility.UNRESOLVED
    assert not unresolved.new_independent_evidence


def test_different_photo_same_angle_never_merged_as_derivative(kit):
    original = ingest(kit, photo())
    distinct = ingest(kit, photo(shift=24))
    assert distinct.asset.media_asset_id != original.asset.media_asset_id
    assert distinct.asset.parent_asset_id is None
    assert distinct.asset.provenance_class not in {
        ProvenanceClass.DERIVATIVE_RESIZE, ProvenanceClass.DERIVATIVE_CROP,
        ProvenanceClass.DERIVATIVE_TRANSCODE,
    }


@pytest.mark.parametrize("activity", [ProducingActivity.AI_GENERATE, ProducingActivity.AI_EDIT,
                                       ProducingActivity.COMPOSITE])
def test_creative_and_renamed_reupload_forbidden(kit, activity):
    original = ingest(kit, photo())
    creative = ingest(kit, photo(shift=61), activity, original.asset.media_asset_id)
    assert creative.asset.truth_eligibility is TruthEligibility.FORBIDDEN
    renamed = ingest(kit, photo(shift=61), activity, original.asset.media_asset_id)
    assert renamed.exact_duplicate
    with pytest.raises(MediaAdmissionError, match="MEDIA_NOT_TRUTH_ELIGIBLE"):
        require_truth_eligible((creative.asset,))
    child = ingest(kit, derived(photo(shift=61), size=(80, 60)),
                   ProducingActivity.RESIZE, creative.asset.media_asset_id)
    grandchild = ingest(kit, derived(photo(shift=61), crop=(0, 0, 60, 50)),
                        ProducingActivity.CROP, child.asset.media_asset_id)
    assert child.asset.truth_eligibility is TruthEligibility.FORBIDDEN
    assert grandchild.asset.truth_eligibility is TruthEligibility.FORBIDDEN


def test_higher_resolution_derivative_can_yield_new_verified_field_without_new_evidence(kit):
    high = photo((200, 150))
    low = derived(high, size=(100, 75))
    low_asset = ingest(kit, low)
    high_asset = ingest(kit, high, ProducingActivity.RESIZE)
    assert not high_asset.new_independent_evidence
    assert high_asset.asset.independent_evidence_id == low_asset.asset.media_asset_id

    class Extractor:
        def extract_verified(self, *, raw, asset):
            return {"VIN": "verified-test-vin"} if asset.width >= 200 else {}

    delta = extract_truth_fields(kit[0], Extractor(), high_asset.asset)
    assert delta.verified_fields["VIN"] == "verified-test-vin"
    assert delta.independent_evidence_id == low_asset.asset.media_asset_id


def test_caller_original_without_server_attestation_and_cycle_rejected(kit):
    raw = photo()
    with pytest.raises(MediaAdmissionError, match="ATTESTATION_INVALID"):
        kit[2].ingest(raw=raw, mime="image/png", activity=ProducingActivity.ORIGINAL_CAPTURE,
                      source_lineage="vehicle:a", task_lineage="turn:1", attestation="caller-original")
    with pytest.raises(MediaAdmissionError, match="MEDIA_PARENT_MISSING|MEDIA_LINEAGE_CYCLE"):
        ingest(kit, raw, parent="media:" + hashlib.sha256(raw).hexdigest())


def test_d1_worker_media_contract():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", "tests/fixtures/rd021_media_worker.mjs"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "media-worker-ok" in result.stdout


def test_d1_candidate_schema_and_incremental_migration_match():
    root = Path(__file__).resolve().parents[1]
    migration = (root / "infra/vehicle_knowledge/migrations/0002_media_asset.sql").read_text()
    schema = (root / "infra/vehicle_knowledge/schema.sql").read_text()
    assert migration[migration.index("CREATE TABLE media_asset("):] in schema
    connection = sqlite3.connect(":memory:")
    connection.executescript(migration)
    cols = {row[1] for row in connection.execute("PRAGMA table_info(media_asset)")}
    assert {"media_asset_id", "raw_sha256", "truth_eligibility", "parent_asset_id",
            "raw_capture_base64"}.issubset(cols)


def test_controlled_ingress_admits_exact_bytes_before_model_and_binds_asset(kit):
    raw = photo()
    digest = hashlib.sha256(raw).hexdigest()
    issuer = kit[1]
    codec = IngressTurnTokenCodec(
        key=b"t" * 32, audience="test", server="mcp", replay_store=InMemoryNonceClaimStore(),
    )

    class Classifier:
        def classify(self, *, request_text, evidence_digest):
            assert evidence_digest == digest
            return IngressTaskClass.COMPANY_COMMERCIAL_MATCHING

    ingress = ControlledSalesIngress(
        classifier=Classifier(), token_codec=codec,
        responses_adapter=ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/endpoint"),
        media_gate=kit[2],
    )
    turn = ServerTurnContext("c1", "7")
    signature = issuer.issue(
        raw_sha256=digest, activity=ProducingActivity.ORIGINAL_CAPTURE,
        source_lineage="vehicle:a", task_lineage="conversation:c1:turn:7",
    )
    plan = ingress.plan(
        turn=turn, request_text="update vehicle", intent="sales_human", raw_evidence=raw,
        media_inputs=({"type": "input_image", "image_url": "caller-supplied"},),
        media_activity=ProducingActivity.ORIGINAL_CAPTURE, media_attestation=signature,
        media_source_lineage="vehicle:a",
    )
    tool = plan.responses_request["tools"][0]
    binding = codec.verify_authorization(
        "Bearer " + tool["authorization"], request_text="update vehicle", intent="sales_human",
    )
    assert binding.media_asset_id == "media:" + digest
    assert plan.responses_request["input"][0]["content"][1]["image_url"].startswith(
        "data:image/png;base64,"
    )
    assert "caller-supplied" not in str(plan.responses_request)


def test_creative_allowed_for_visual_task_but_matching_admission_stops_before_model(kit):
    raw = photo(shift=80)
    digest = hashlib.sha256(raw).hexdigest()
    signature = kit[1].issue(
        raw_sha256=digest, activity=ProducingActivity.AI_GENERATE,
        source_lineage="vehicle:a", task_lineage="conversation:c1:turn:7",
    )
    codec = IngressTurnTokenCodec(
        key=b"t" * 32, audience="test", server="mcp", replay_store=InMemoryNonceClaimStore(),
    )

    class Classifier:
        def __init__(self, task_class):
            self.task_class = task_class

        def classify(self, **kwargs):
            return self.task_class

    adapter = ForcedHostDispatchAdapter(mcp_server_url="https://mcp.example/endpoint")
    values = dict(
        turn=ServerTurnContext("c1", "7"), request_text="make an ad", intent="sales_human",
        raw_evidence=raw, media_inputs=({"type": "input_image"},),
        media_activity=ProducingActivity.AI_GENERATE, media_attestation=signature,
        media_source_lineage="vehicle:a",
    )
    ordinary = ControlledSalesIngress(
        classifier=Classifier(IngressTaskClass.ORDINARY), token_codec=codec,
        responses_adapter=adapter, media_gate=kit[2],
    )
    assert ordinary.plan(**values).responses_request["input"][0]["content"][1]["type"] == "input_image"
    matching = ControlledSalesIngress(
        classifier=Classifier(IngressTaskClass.COMPANY_COMMERCIAL_MATCHING), token_codec=codec,
        responses_adapter=adapter, media_gate=kit[2],
    )
    with pytest.raises(MediaAdmissionError, match="MEDIA_NOT_TRUTH_ELIGIBLE"):
        matching.plan(**values)


def test_matching_media_truth_checked_before_evidence_provider(kit):
    raw = photo(shift=60)
    asset = ingest(kit, raw, ProducingActivity.AI_GENERATE).asset
    codec = IngressTurnTokenCodec(
        key=b"t" * 32, audience="test", server="mcp", replay_store=InMemoryNonceClaimStore(),
    )
    token = codec.issue(
        conversation_id="c1", turn_id="7", task_class=IngressTaskClass.COMPANY_COMMERCIAL_MATCHING,
        request_text="update vehicle", intent="sales_human", evidence_digest=asset.raw_sha256,
        media_asset_id=asset.media_asset_id, now=datetime.now(UTC),
    )
    binding = codec.verify_authorization(
        "Bearer " + token, request_text="update vehicle", intent="sales_human",
    )

    class Provider:
        calls = 0

        def resolve(self, **kwargs):
            self.calls += 1
            return None

    provider = Provider()
    host_compiler = TrustedHostTaskCompiler(
        dispatch_compiler=compiler(), host_state_resolver=HostResolver(),
        evidence_provider=provider, media_repository=kit[0],
    )
    from global_hybrid_v2.trusted_workbench_intent import CallerTask

    with pytest.raises(TrustBoundaryError, match="MEDIA_NOT_TRUTH_ELIGIBLE"):
        host_compiler.compile_admitted(
            caller_task=CallerTask(request_text="update vehicle", intent="sales_human"),
            binding=binding,
        )
    assert provider.calls == 0
