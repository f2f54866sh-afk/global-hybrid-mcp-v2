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
            media_contract = contract.model_copy(
                update={
                    "domain_contracts": [
                        packet
                        for packet in contract.domain_contracts
                        if packet.payload.get("projection") == "sales_media_evidence"
                    ]
                }
            )
            vehicle_contract = contract.model_copy(
                update={
                    "domain_contracts": [
                        packet
                        for packet in contract.domain_contracts
                        if packet.payload.get("projection") == "vehicle_configuration_reference"
                    ]
                }
            )
            media_result = self.media_domain.run(media_contract)
            vehicle_result = self.vehicle_domain.run(vehicle_contract)
            return DomainResult(
                owner=Owner.SALES_HUMAN,
                status="SALES_EVIDENCE_BUNDLE_READY",
                output={
                    "state": "READY",
                    "media": media_result.output,
                    "vehicle_configuration": vehicle_result.output,
                    "projection_packets": [
                        {
                            "contract_id": packet.contract_id,
                            "task_trace_id": packet.task_trace_id,
                            "producer": packet.provider_owner.value,
                            "currentness": packet.currentness.value,
                            "provenance": packet.provenance,
                            "evidence_role": packet.payload.get("evidence_role"),
                            "authority_state": packet.status.value,
                        }
                        for packet in contract.domain_contracts
                    ],
                },
                evidence={
                    **media_result.evidence,
                    "media_projection_requested": True,
                    "vehicle_configuration_projection_requested": True,
                    "adapter_configured": True,
                    "adapter_called": True,
                    "result_returned": True,
                    "media_status": media_result.status,
                    "vehicle_status": vehicle_result.status,
                    "instance_trim_state": "UNRESOLVED",
                    "factory_provenance_state": "UNRESOLVED",
                },
            )
        if vehicle_task:
            return self.vehicle_domain.run(contract)
        return self.media_domain.run(contract)
