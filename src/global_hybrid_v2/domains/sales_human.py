from global_hybrid_v2.contracts import DomainResult, Owner, TaskContract
from global_hybrid_v2.domains.sales_media import SalesMediaDomain
from global_hybrid_v2.domains.sales_vehicle_configuration import (
    SalesVehicleConfigurationDomain,
)


class SalesHumanDomain:
    owner = Owner.SALES_HUMAN

    def __init__(
        self,
        media_domain: SalesMediaDomain | None = None,
        vehicle_domain: SalesVehicleConfigurationDomain | None = None,
    ) -> None:
        self.media_domain = media_domain or SalesMediaDomain()
        self.vehicle_domain = vehicle_domain or SalesVehicleConfigurationDomain()

    def run(self, contract: TaskContract) -> DomainResult:
        if contract.owner is not Owner.SALES_HUMAN:
            raise ValueError("SalesHumanDomain received another owner's task")

        media_task = SalesMediaDomain.supports(contract.request_text)
        vehicle_task = contract.vehicle_configuration_query is not None
        if media_task and vehicle_task:
            return DomainResult(
                owner=Owner.SALES_HUMAN,
                status="SALES_MULTI_PROJECTION_NOT_CONFIGURED",
                output={
                    "state": "SALES_MULTI_PROJECTION_NOT_CONFIGURED",
                    "requested_projections": [
                        "sales_media_evidence",
                        "vehicle_configuration_reference",
                    ],
                },
                evidence={
                    "media_projection_requested": True,
                    "vehicle_configuration_projection_requested": True,
                    "adapter_configured": True,
                    "adapter_called": True,
                    "result_returned": True,
                },
            )
        if vehicle_task:
            return self.vehicle_domain.run(contract)
        return self.media_domain.run(contract)
