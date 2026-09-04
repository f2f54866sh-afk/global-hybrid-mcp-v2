import pytest

from global_hybrid_v2.contracts import EffectType, Owner
from global_hybrid_v2.governance.effects import EffectAuthorizationError, EffectGate


def test_visual_cannot_write_external_state():
    with pytest.raises(EffectAuthorizationError):
        EffectGate().authorize(Owner.VISUAL, [EffectType.EXTERNAL_WRITE])


def test_execution_can_request_image_generation():
    EffectGate().authorize(Owner.EXECUTION, [EffectType.IMAGE_GENERATE])


@pytest.mark.parametrize(
    "effect", [EffectType.EXTERNAL_WRITE, EffectType.FILE_WRITE, EffectType.IMAGE_GENERATE]
)
def test_live_execution_disabled_blocks_mutations(effect):
    with pytest.raises(EffectAuthorizationError, match="LIVE_EXECUTION_DISABLED"):
        EffectGate(live_execution=False).authorize(Owner.EXECUTION, [effect])


@pytest.mark.parametrize(
    "effect", [EffectType.READ_ONLY, EffectType.EXTERNAL_READ, EffectType.MODEL_INFERENCE]
)
def test_live_execution_disabled_allows_non_mutations(effect):
    owner = Owner.LIBRARY_FACT if effect is EffectType.EXTERNAL_READ else Owner.SALES_HUMAN
    EffectGate(live_execution=False).authorize(owner, [effect])
