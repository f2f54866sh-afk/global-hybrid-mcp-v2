from global_hybrid_v2.contracts import ContextClass, ContextItem, ContextOrigin
from global_hybrid_v2.runtime.dispatcher import TrustedDispatchContext
from tests.test_rd_20260913_009_image_binding import _dispatcher, _image_spec, _RecordingPort, _request


def _capability_context():
    return ContextItem(id="cap", origin=ContextOrigin.CURRENT_TOOL_RESULT,
        context_class=ContextClass.CURRENT_CAPABILITY_FACT, purpose="current image capability",
        task_scope="make image", payload={"target_system": "image", "action_class": "generate"},
        current_binding=True, provenance=["fixture"])


def test_stage1a_requires_python_only_trusted_context_before_port():
    port = _RecordingPort()
    spec = _image_spec(None).model_copy(update={"identity_trusted_ingress_required": True})
    request = _request(spec, context=[_capability_context()])
    request.image_task["principal"] = "forged"
    result = _dispatcher(port).dispatch(request)
    assert result.status == "IDENTITY_TRUSTED_CONTEXT_REQUIRED"
    assert port.calls == 0
    result = _dispatcher(port).dispatch(
        request, trusted_context=TrustedDispatchContext("fake-user", "fake-test")
    )
    assert result.status == "PASS"
    assert port.calls == 1


def test_stage1a_ordinary_image_remains_compatible():
    port = _RecordingPort()
    result = _dispatcher(port).dispatch(_request(_image_spec(None), context=[_capability_context()]))
    assert result.status == "PASS"
    assert port.calls == 1
