from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from global_hybrid_v2.adapters.openai_bound_image import ResolvedImageAsset
from global_hybrid_v2.image_surface import (
    AuthorizedEditEnvelope,
    IdentitySourceRole,
    IdentityStage,
    ImageExecutionInput,
    ImageExecutionRequest,
    ImageOperationMode,
    LocalityEvidenceState,
    NormalizedPoint,
    RenderManifest,
    SpatialBindingReceipt,
    SpatialClipState,
)
from global_hybrid_v2.runtime.state import RuntimeStateError, SQLiteRuntimeStateStore
from global_hybrid_v2.scene_product_verifier import (
    MetricResult,
    PinnedModelArtifact,
    ProductCheckResult,
    RegistrationResult,
    SceneDecision,
    SceneProductVerifierV1,
)


def _png(pixels, size=(4, 4)):
    image = Image.new("RGBA", size, (10, 20, 30, 255))
    for point, color in pixels.items():
        image.putpixel(point, color)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


SCENE = _png({})
MASK = _png({(1, 1): (0, 0, 0, 0)})


def _sha(value):
    return hashlib.sha256(value).hexdigest()


class Assets:
    def __init__(self):
        self.values = {
            "scene": ResolvedImageAsset(
                asset_id="scene",
                content=SCENE,
                media_type="image/png",
                authoritative_roles={IdentitySourceRole.SCENE_BASE},
            ),
            "mask": ResolvedImageAsset(asset_id="mask", content=MASK, media_type="image/png"),
        }

    def resolve(self, asset_id):
        return self.values[asset_id]


def _threshold_digest(metric_id, threshold, version="cal-v1"):
    body = {"metric_id": metric_id, "threshold": threshold, "threshold_version": version}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class Metric:
    def __init__(self, artifact, metric_id, decision=SceneDecision.PASS, score=0.01):
        self.artifact = artifact
        self.metric_id = metric_id
        self.decision = decision
        self.score = score

    def compare(self, **_kwargs):
        threshold = 0.1
        return MetricResult(
            metric_id=self.metric_id,
            score=self.score,
            threshold=threshold,
            threshold_version="cal-v1",
            threshold_digest=_threshold_digest(self.metric_id, threshold),
            decision=self.decision,
            region_scores={"scene": self.score, "vehicle": self.score, "customer": self.score},
        )


class Checks:
    def __init__(self, failed=None):
        self.failed = failed

    def check(self, **_kwargs):
        return [
            ProductCheckResult(
                check_id=name,
                decision=SceneDecision.FAIL if name == self.failed else SceneDecision.PASS,
            )
            for name in sorted(SceneProductVerifierV1.REQUIRED_PRODUCT_CHECKS)
        ]


class FailedRegistration:
    def register(self, *, parent, candidate):
        return RegistrationResult(
            decision=SceneDecision.INDETERMINATE,
            algorithm_id="fixture-registration",
            algorithm_version="1",
            transform=[1, 0, 0, 0, 1, 0],
            confidence=0,
            registered_output=candidate,
        )


def _artifact(tmp_path, name):
    path = tmp_path / f"{name}.bin"
    path.write_bytes(name.encode())
    return PinnedModelArtifact(
        backend_id=name,
        model_id=name,
        model_version="1",
        artifact_path=str(path),
        artifact_sha256=_sha(name.encode()),
        runtime_id="fixture-runtime",
        runtime_version="1",
        preprocessing_version="1",
    )


def _request(attempt="attempt-1"):
    polygon = [
        NormalizedPoint(x=0.1, y=0.1),
        NormalizedPoint(x=0.9, y=0.1),
        NormalizedPoint(x=0.9, y=0.9),
    ]
    envelope = AuthorizedEditEnvelope(
        source_asset_id="scene",
        source_sha256=_sha(SCENE),
        region_id="seller",
        mask_asset_id="mask",
        mask_sha256=_sha(MASK),
        target_semantics="SELLER_ONLY",
        spatial_binding=SpatialBindingReceipt(
            target_role="SELLER",
            geometry_source="fixture",
            source_frame_id="frame",
            source_polygon=polygon,
            geometry_confidence=1,
            geometry_confidence_sufficient=True,
            transform_chain_digest="transform",
            projected_polygon=polygon,
            current_artifact_frame_id="frame",
            clip_state=SpatialClipState.INSIDE_EXPECTED_BOUNDS,
            binding_valid=True,
            locator_receipt_id="locator",
            locator_evidence_state=LocalityEvidenceState.VERIFIED,
        ),
        write_polygon=polygon,
    )
    return ImageExecutionRequest(
        workflow_id="workflow-1",
        slot_id="slot-1",
        stage=IdentityStage.SOURCE_1X1,
        attempt_id=attempt,
        operation_mode=ImageOperationMode.TARGETED_EDIT,
        task_binding="task-1",
        person_binding="person-1",
        packet_digest="a" * 64,
        capability_snapshot_id="snapshot-1",
        inputs=[
            ImageExecutionInput(
                asset_id="scene", sha256=_sha(SCENE), role=IdentitySourceRole.SCENE_BASE
            )
        ],
        manifest=RenderManifest(visual_subject="seller", current_visual_delta="replace seller"),
        locality_envelope=envelope,
    )


def _verifier(tmp_path, *, checks=None, lpips=SceneDecision.PASS, dino=SceneDecision.PASS, registration=None):
    store = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    verifier = SceneProductVerifierV1(
        assets=Assets(),
        ledger=store,
        lpips=Metric(_artifact(tmp_path, "lpips"), "LPIPS", lpips),
        dinov2=Metric(_artifact(tmp_path, "dinov2"), "DINOv2", dino),
        product_checks=Checks(checks),
        registration=registration,
    )
    return verifier, store


def test_preserved_scene_and_allowed_inside_envelope_change_pass_and_reopen(tmp_path):
    verifier, store = _verifier(tmp_path)
    output = _png({(1, 1): (200, 100, 50, 255)})
    result = verifier.verify(request=_request(), output=output, attempt_id="attempt-1")
    assert result.passed
    receipt = result.evidence["receipt"]
    assert receipt["decision"] == "PASS"
    assert receipt["parent_scene_sha256"] == _sha(SCENE)
    assert receipt["candidate_output_sha256"] == _sha(output)
    assert receipt["lpips_artifact"]["artifact_sha256"] == _sha(b"lpips")
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    assert reopened.read_scene_product_verification(receipt["receipt_id"]) == receipt
    with pytest.raises(RuntimeStateError, match="ALREADY_RECORDED"):
        verifier.verify(request=_request(), output=output, attempt_id="attempt-1")


@pytest.mark.parametrize(
    "output",
    [
        _png({(0, 0): (255, 0, 0, 255)}),
        _png({(0, 0): (30, 40, 50, 255), (2, 2): (30, 40, 50, 255)}),
    ],
)
def test_outside_or_global_color_drift_fails_hard_boundary(tmp_path, output):
    verifier, _ = _verifier(tmp_path)
    result = verifier.verify(request=_request(), output=output, attempt_id="attempt-1")
    assert not result.passed
    assert result.evidence["decision"] == "FAIL"
    assert result.evidence["receipt"]["outside_pixel_metrics"]["decision"] == "FAIL"


def test_geometry_or_registration_failure_holds(tmp_path):
    verifier, _ = _verifier(tmp_path, registration=FailedRegistration())
    result = verifier.verify(request=_request(), output=SCENE, attempt_id="attempt-1")
    assert not result.passed
    assert result.evidence["decision"] == "INDETERMINATE"


@pytest.mark.parametrize(
    "check",
    [
        "vehicle_region_continuity",
        "vehicle_component_substitution",
        "customer_region_preservation",
        "object_count_presence",
        "protected_region_correspondence",
    ],
)
def test_product_drift_checks_fail(check, tmp_path):
    verifier, _ = _verifier(tmp_path, checks=check)
    result = verifier.verify(request=_request(), output=SCENE, attempt_id="attempt-1")
    assert not result.passed
    assert result.evidence["decision"] == "FAIL"


def test_soft_metrics_cannot_override_hard_failure(tmp_path):
    verifier, _ = _verifier(tmp_path)
    result = verifier.verify(
        request=_request(),
        output=_png({(0, 0): (99, 99, 99, 255)}),
        attempt_id="attempt-1",
    )
    assert result.evidence["receipt"]["lpips_result"]["decision"] == "PASS"
    assert result.evidence["receipt"]["dinov2_result"]["decision"] == "PASS"
    assert result.evidence["decision"] == "FAIL"


def test_model_artifact_and_threshold_mismatch_fail_closed(tmp_path):
    artifact = _artifact(tmp_path, "lpips")
    Path(artifact.artifact_path).write_bytes(b"tampered")
    with pytest.raises(Exception, match="ARTIFACT_MISMATCH"):
        SceneProductVerifierV1(
            assets=Assets(),
            ledger=SQLiteRuntimeStateStore(tmp_path / "runtime.db"),
            lpips=Metric(artifact, "LPIPS"),
            dinov2=Metric(_artifact(tmp_path, "dinov2"), "DINOv2"),
            product_checks=Checks(),
        )
    with pytest.raises(ValidationError, match="threshold digest mismatch"):
        MetricResult(
            metric_id="LPIPS",
            score=0,
            threshold=0.1,
            threshold_version="cal-v1",
            threshold_digest="f" * 64,
            decision=SceneDecision.PASS,
        )


def test_stale_parent_and_forged_receipt_fail_closed(tmp_path):
    verifier, store = _verifier(tmp_path)
    bad = _request().model_copy(
        update={
            "inputs": [
                ImageExecutionInput(
                    asset_id="scene",
                    sha256="f" * 64,
                    role=IdentitySourceRole.SCENE_BASE,
                )
            ]
        }
    )
    with pytest.raises(Exception, match="STALE_PARENT"):
        verifier.verify(request=bad, output=SCENE, attempt_id="attempt-1")
    result = verifier.verify(request=_request(), output=SCENE, attempt_id="attempt-1")
    receipt_id = result.evidence["receipt"]["receipt_id"]
    with store._connect() as connection:
        payload = json.loads(connection.execute(
            "SELECT receipt FROM scene_product_verification WHERE receipt_id=?", (receipt_id,)
        ).fetchone()[0])
        payload["decision"] = "FAIL"
        connection.execute(
            "UPDATE scene_product_verification SET receipt=? WHERE receipt_id=?",
            (json.dumps(payload), receipt_id),
        )
    with pytest.raises(RuntimeStateError, match="DIGEST_MISMATCH"):
        SQLiteRuntimeStateStore(tmp_path / "runtime.db").read_scene_product_verification(receipt_id)
