from global_hybrid_v2.contracts import Intent, Owner
from global_hybrid_v2.governance.router import OwnerRouter


def test_owner_routing_is_deterministic():
    router = OwnerRouter()
    assert router.route(Intent.GOVERNANCE) is Owner.GLOBAL
    assert router.route(Intent.SALES_HUMAN) is Owner.SALES_HUMAN
    assert router.route(Intent.LIBRARY_FACT) is Owner.LIBRARY_FACT
    assert router.route(Intent.VISUAL) is Owner.VISUAL
    assert router.route(Intent.EXECUTION) is Owner.EXECUTION
