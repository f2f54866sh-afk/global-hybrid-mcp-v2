from __future__ import annotations

import hashlib
import io
import json

import pytest
from PIL import Image

from global_hybrid_v2.adapters.openai_bound_image import (
    OpenAIAdapterError,
    OpenAIBoundImageExecutionPort,
    OpenAIImagesTransportResult,
    ResolvedImageAsset,
    VerificationResult,
)
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


def _png(color: tuple[int, int, int, int]) -> bytes:
    stream = io.BytesIO()
    Image.new("RGBA", (2, 2), color).save(stream, format="PNG")
    return stream.getvalue()


SCENE = _png((10, 20, 30, 255))
MASTER = _png((40, 50, 60, 255))
SELLER = _png((70, 80, 90, 255))
BODY = _png((100, 110, 120, 255))
MASK = _png((255, 255, 255, 255))
OUTPUT = _png((10, 20, 30, 255))


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Assets:
    def __init__(self):
        self.values = {
            "scene": ResolvedImageAsset(
                asset_id="scene", content=SCENE, media_type="image/png",
                authoritative_roles={IdentitySourceRole.SCENE_BASE},
            ),
            "master": ResolvedImageAsset(
                asset_id="master", content=MASTER, media_type="image/png",
                authoritative_roles={IdentitySourceRole.ORIGINAL_REAL_MASTER},
            ),
            "seller": ResolvedImageAsset(
                asset_id="seller", content=SELLER, media_type="image/png",
                authoritative_roles={IdentitySourceRole.SELLER},
            ),
            "body": ResolvedImageAsset(
                asset_id="body", content=BODY, media_type="image/png",
                authoritative_roles={IdentitySourceRole.BODY},
            ),
            "mask": ResolvedImageAsset(
                asset_id="mask", content=MASK, media_type="image/png"
            ),
        }

    def resolve(self, asset_id):
        return self.values[asset_id]


class Transport:
    def __init__(self, *, output=OUTPUT, error=None, reported_digest=None):
        self.calls = []
        self.output = output
        self.error = error
        self.reported_digest = reported_digest

    def execute(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return OpenAIImagesTransportResult(
            output_bytes=self.output,
            reported_output_sha256=self.reported_digest,
            provider_operation_id="operation-1",
            provider_response_id="request-1",
        )


class Verifier:
    def __init__(self, passed=True):
        self.passed = passed

    def verify(self, **_kwargs):
        return VerificationResult(passed=self.passed, evidence={"qualified": True})


def _polygon():
    return [
        NormalizedPoint(x=0.1, y=0.1),
        NormalizedPoint(x=0.9, y=0.1),
        NormalizedPoint(x=0.9, y=0.9),
    ]


def _envelope(parent="scene"):
    return AuthorizedEditEnvelope(
        source_asset_id=parent,
        source_sha256=_sha(SCENE),
        region_id="seller-region",
        mask_asset_id="mask",
        mask_sha256=_sha(MASK),
        target_semantics="SELLER_ONLY",
        spatial_binding=SpatialBindingReceipt(
            target_role="SELLER",
            geometry_source="server-locator",
            source_frame_id="frame-1",
            source_polygon=_polygon(),
            geometry_confidence=1,
            geometry_confidence_sufficient=True,
            transform_chain_digest="transform-1",
            projected_polygon=_polygon(),
            current_artifact_frame_id="frame-1",
            clip_state=SpatialClipState.INSIDE_EXPECTED_BOUNDS,
            binding_valid=True,
            locator_receipt_id="locator-1",
            locator_evidence_state=LocalityEvidenceState.VERIFIED,
        ),
        write_polygon=_polygon(),
    )


def _input(asset_id, content, role):
    return ImageExecutionInput(asset_id=asset_id, sha256=_sha(content), role=role)


def _request(*, inputs=None, snapshot=None, envelope=None, workflow="workflow-1"):
    return ImageExecutionRequest(
        workflow_id=workflow,
        slot_id="slot-1",
        stage=IdentityStage.SOURCE_1X1,
        operation_mode=ImageOperationMode.TARGETED_EDIT,
        task_binding="task-1",
        person_binding="person-1",
        packet_digest="a" * 64,
        capability_snapshot_id=snapshot or OpenAIBoundImageExecutionPort.SNAPSHOT_ID,
        inputs=inputs
        or [
            _input("seller", SELLER, IdentitySourceRole.SELLER),
            _input("body", BODY, IdentitySourceRole.BODY),
            _input("scene", SCENE, IdentitySourceRole.SCENE_BASE),
            _input("master", MASTER, IdentitySourceRole.ORIGINAL_REAL_MASTER),
        ],
        manifest=RenderManifest(
            visual_subject="same seller in the supplied scene",
            current_visual_delta="replace seller",
        ),
        locality_envelope=envelope or _envelope(),
    )


def _port(tmp_path, *, transport=None, identity=True, scene=True, assets=None):
    ledger = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    port = OpenAIBoundImageExecutionPort(
        assets=assets or Assets(),
        transport=transport or Transport(),
        ledger=ledger,
        identity_verifier=Verifier(identity),
        scene_product_verifier=Verifier(scene),
        model="gpt-image-1",
    )
    return port, ledger


def test_capabilities_are_port_owned_and_do_not_claim_generate(tmp_path):
    port, _ = _port(tmp_path)
    snapshot = port.capability_snapshot()
    assert not snapshot.generate
    assert snapshot.edit and snapshot.targeted_edit
    assert snapshot.multiple_reference_input and snapshot.mask_input
    assert snapshot.source_binding_receipt and snapshot.output_digest_available
    assert not snapshot.provider_typed_role_enforcement
    assert not snapshot.provider_digest_binding
    assert not snapshot.exact_mask_enforcement
    capabilities = port.describe_capabilities()
    assert capabilities.supported_operation_modes == {
        ImageOperationMode.EDIT,
        ImageOperationMode.TARGETED_EDIT,
    }
    assert capabilities.mask_input
    assert capabilities.source_binding_receipt
    assert capabilities.outside_region_verification


def test_targeted_edit_serializes_exact_order_receipt_and_lineage(tmp_path):
    transport = Transport()
    port, ledger = _port(tmp_path, transport=transport)
    outcome = port.invoke_bound(request=_request(), node_token="attempt-1")
    sent = transport.calls[0]
    assert sent.endpoint == "/images/edits"
    assert [item.role for item in sent.images] == [
        IdentitySourceRole.SCENE_BASE,
        IdentitySourceRole.ORIGINAL_REAL_MASTER,
        IdentitySourceRole.SELLER,
        IdentitySourceRole.BODY,
    ]
    assert sent.mask_asset_id == "mask"
    assert sent.mask_sha256 == _sha(MASK)
    assert outcome.artifact_sha256 == _sha(OUTPUT)
    assert outcome.artifact_id == f"sha256:{_sha(OUTPUT)}"
    record = ledger.read_openai_image_execution(
        ledger._connect().execute(
            "SELECT receipt_id FROM openai_bound_image_execution"
        ).fetchone()[0]
    )
    assert record["state"] == "ACCEPTED"
    assert record["receipt"]["endpoint"] == "/images/edits"
    assert record["receipt"]["ordered_inputs"][0]["role"] == "SCENE_BASE"
    assert record["lineage"]["parent_scene_asset_id"] == "scene"
    assert record["lineage"]["provider_response_id"] == "request-1"


@pytest.mark.parametrize(
    ("inputs", "blocker"),
    [
        (
            [
                _input("master", MASTER, IdentitySourceRole.ORIGINAL_REAL_MASTER),
                _input("seller", SELLER, IdentitySourceRole.SELLER),
            ],
            "EXACT_SCENE_BASE_REQUIRED",
        ),
        (
            [
                _input("scene", SCENE, IdentitySourceRole.SCENE_BASE),
                _input("master", MASTER, IdentitySourceRole.ORIGINAL_REAL_MASTER),
            ],
            "EXACT_SELLER_REQUIRED",
        ),
        (
            [
                _input("scene", SCENE, IdentitySourceRole.SCENE_BASE),
                _input("master", MASTER, IdentitySourceRole.SELLER),
                _input("seller", SELLER, IdentitySourceRole.ORIGINAL_REAL_MASTER),
            ],
            "SOURCE_ROLE_AUTHORITY_MISMATCH",
        ),
    ],
)
def test_role_injection_or_missing_required_role_fails_closed(tmp_path, inputs, blocker):
    port, _ = _port(tmp_path)
    with pytest.raises(OpenAIAdapterError, match=blocker):
        port.invoke_bound(request=_request(inputs=inputs), node_token="attempt-1")


def test_caller_digest_injection_is_recomputed_from_server_asset(tmp_path):
    request = _request()
    forged = request.inputs[0].model_copy(update={"sha256": "f" * 64})
    port, _ = _port(tmp_path)
    with pytest.raises(OpenAIAdapterError, match="SOURCE_DIGEST_MISMATCH"):
        port.invoke_bound(
            request=request.model_copy(update={"inputs": [forged, *request.inputs[1:]]}),
            node_token="attempt-1",
        )


def test_generated_master_stale_asset_and_wrong_mask_parent_fail_closed(tmp_path):
    assets = Assets()
    assets.values["master"] = assets.values["master"].model_copy(update={"generated": True})
    port, _ = _port(tmp_path / "a", assets=assets)
    with pytest.raises(OpenAIAdapterError, match="GENERATED_IMAGE_CANNOT_BE_MASTER"):
        port.invoke_bound(request=_request(), node_token="attempt-1")

    assets = Assets()
    assets.values["scene"] = assets.values["scene"].model_copy(update={"current": False})
    port, _ = _port(tmp_path / "b", assets=assets)
    with pytest.raises(OpenAIAdapterError, match="STALE_SOURCE_ASSET"):
        port.invoke_bound(request=_request(), node_token="attempt-1")

    port, _ = _port(tmp_path / "c")
    with pytest.raises(OpenAIAdapterError, match="MASK_PARENT_BINDING_MISMATCH"):
        port.invoke_bound(request=_request(envelope=_envelope("other")), node_token="attempt-1")


def test_capability_snapshot_and_unsupported_mode_fail_before_transport(tmp_path):
    transport = Transport()
    port, _ = _port(tmp_path, transport=transport)
    with pytest.raises(OpenAIAdapterError, match="CAPABILITY_SNAPSHOT_MISMATCH"):
        port.invoke_bound(request=_request(snapshot="stale"), node_token="attempt-1")
    generate = _request().model_copy(update={"operation_mode": ImageOperationMode.GENERATE})
    with pytest.raises(OpenAIAdapterError, match="OPENAI_IMAGE_OPERATION_UNSUPPORTED"):
        port.invoke_bound(request=generate, node_token="attempt-2")
    assert transport.calls == []


def test_provider_unknown_and_output_missing_are_durable(tmp_path):
    port, ledger = _port(tmp_path / "unknown", transport=Transport(error=TimeoutError()))
    with pytest.raises(TimeoutError):
        port.invoke_bound(request=_request(), node_token="attempt-1")
    with ledger._connect() as connection:
        row = connection.execute(
            "SELECT receipt_id, state FROM openai_bound_image_execution"
        ).fetchone()
    assert row[1] == "PROVIDER_OUTCOME_UNKNOWN"
    assert SQLiteRuntimeStateStore(tmp_path / "unknown" / "runtime.db").read_openai_image_execution(
        row[0]
    )["state"] == "PROVIDER_OUTCOME_UNKNOWN"

    port, ledger = _port(tmp_path / "missing", transport=Transport(output=b""))
    with pytest.raises(OpenAIAdapterError, match="OPENAI_IMAGE_OUTPUT_MISSING"):
        port.invoke_bound(request=_request(), node_token="attempt-1")
    with ledger._connect() as connection:
        assert connection.execute(
            "SELECT state FROM openai_bound_image_execution"
        ).fetchone()[0] == "OUTPUT_MISSING"


def test_output_digest_mismatch_is_rejected(tmp_path):
    port, _ = _port(tmp_path, transport=Transport(reported_digest="f" * 64))
    with pytest.raises(OpenAIAdapterError, match="OUTPUT_DIGEST_MISMATCH"):
        port.invoke_bound(request=_request(), node_token="attempt-1")


def test_verifier_failures_never_accept(tmp_path):
    port, ledger = _port(tmp_path / "identity", identity=False)
    outcome = port.invoke_bound(request=_request(), node_token="attempt-1")
    assert not outcome.identity_preserved
    with ledger._connect() as connection:
        assert connection.execute(
            "SELECT state FROM openai_bound_image_execution"
        ).fetchone()[0] == "REJECTED"

    port, ledger = _port(tmp_path / "scene", scene=False)
    outcome = port.invoke_bound(request=_request(), node_token="attempt-1")
    assert not outcome.preservation_pass
    with ledger._connect() as connection:
        assert connection.execute(
            "SELECT state FROM openai_bound_image_execution"
        ).fetchone()[0] == "REJECTED"


def test_outside_envelope_mutation_is_rejected(tmp_path):
    changed = _png((255, 0, 0, 255))
    transparent_mask = _png((0, 0, 0, 255))
    assets = Assets()
    assets.values["mask"] = ResolvedImageAsset(
        asset_id="mask", content=transparent_mask, media_type="image/png"
    )
    request = _request().model_copy(update={"locality_envelope": _envelope().model_copy(
        update={"mask_sha256": _sha(transparent_mask)}
    )})
    port, ledger = _port(tmp_path, assets=assets, transport=Transport(output=changed))
    outcome = port.invoke_bound(request=request, node_token="attempt-1")
    assert not outcome.preservation_pass
    assert outcome.outside_envelope_changed_pixels == 4
    with ledger._connect() as connection:
        assert connection.execute(
            "SELECT state FROM openai_bound_image_execution"
        ).fetchone()[0] == "REJECTED"


def test_duplicate_attempt_and_retry_after_accepted_fail_after_reopen(tmp_path):
    port, ledger = _port(tmp_path)
    port.invoke_bound(request=_request(), node_token="attempt-1")
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    port.ledger = reopened
    with pytest.raises(RuntimeStateError, match="IMAGE_SLOT_ALREADY_ACCEPTED"):
        port.invoke_bound(request=_request(), node_token="attempt-2")


def test_reopen_rejects_tampered_immutable_lineage(tmp_path):
    port, ledger = _port(tmp_path)
    port.invoke_bound(request=_request(), node_token="attempt-1")
    with ledger._connect() as connection:
        receipt_id, raw = connection.execute(
            "SELECT receipt_id, lineage FROM openai_bound_image_execution"
        ).fetchone()
        lineage = json.loads(raw)
        lineage["output_artifact_id"] = "forged"
        connection.execute(
            "UPDATE openai_bound_image_execution SET lineage=? WHERE receipt_id=?",
            (json.dumps(lineage), receipt_id),
        )
    reopened = SQLiteRuntimeStateStore(tmp_path / "runtime.db")
    with pytest.raises(RuntimeStateError, match="LINEAGE_DIGEST_MISMATCH"):
        reopened.read_openai_image_execution(receipt_id)


def test_order_is_server_deterministic_regardless_of_request_order(tmp_path):
    request = _request()
    transport = Transport()
    port, _ = _port(tmp_path, transport=transport)
    port.invoke_bound(
        request=request.model_copy(update={"inputs": list(reversed(request.inputs))}),
        node_token="attempt-1",
    )
    assert [item.asset_id for item in transport.calls[0].images] == [
        "scene",
        "master",
        "seller",
        "body",
    ]
