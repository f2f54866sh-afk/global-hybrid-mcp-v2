import pytest

from global_hybrid_v2.contracts import EffectType, Owner
from global_hybrid_v2.governance.effects import EffectAuthorizationError, EffectGate


def test_visual_cannot_write_external_state():
    with pytest.raises(EffectAuthorizationError):
        EffectGate().authorize(Owner.VISUAL, [EffectType.EXTERNAL_WRITE])


def test_execution_can_request_image_generation():
    EffectGate().authorize(Owner.EXECUTION, [EffectType.IMAGE_GENERATE])
