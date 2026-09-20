from __future__ import annotations

from global_hybrid_v2.contracts import (
    DomainContractStatus,
    DomainResult,
    OutputClassification,
    Owner,
    TaskContract,
)


class SalesVehicleConfigurationDomain:
    owner = Owner.SALES_HUMAN
    projection_name = "vehicle_configuration_reference"
    lookup_states = {
        "HIT",
        "PARTIAL",
        "MISS",
        "STALE",
        "CONFLICT",
        "PROVIDER_UNAVAILABLE",
    }

    def run(self, contract: TaskContract) -> DomainResult:
        if contract.owner is not Owner.SALES_HUMAN:
            raise ValueError("vehicle configuration consumer requires SALES_HUMAN owner")
        if contract.vehicle_configuration_query is None:
            raise ValueError("vehicle configuration consumer requires typed query")

        packets = [
            packet
            for packet in contract.domain_contracts
            if packet.provider_owner is Owner.LIBRARY_FACT
            and packet.consumer_owner is Owner.SALES_HUMAN
            and packet.payload.get("projection") == self.projection_name
        ]
        if len(packets) != 1:
            raise ValueError("vehicle configuration consumer requires exactly one Library packet")
        packet = packets[0]
        if packet.status is not DomainContractStatus.PASS:
            raise ValueError("vehicle configuration Library packet must pass admission")
        if packet.payload.get("evidence_role") != "LIBRARY_REFERENCE_NOT_INSTANCE_PROOF":
            raise ValueError("vehicle configuration packet evidence role is invalid")
        if packet.task_trace_id != contract.task_trace_id:
            raise ValueError(
                "vehicle configuration Library packet task binding mismatch"
            )
        expected_query = contract.vehicle_configuration_query.model_dump(mode="json")
        if packet.payload.get("query") != expected_query:
            raise ValueError(
                "vehicle configuration Library packet query binding mismatch"
            )

        lookup_state = packet.payload["lookup_state"]
        if lookup_state not in self.lookup_states:
            raise ValueError("unsupported vehicle configuration lookup state")
        query = packet.payload["query"]
        reference_configurations = packet.payload["configurations"]
        trim_matrix = (
            reference_configurations
            if query.get("trim") is None and query.get("include_trim_matrix") is True
            else []
        )
        observed_equipment_matches = [
            self._match_observed_equipment(key, reference_configurations)
            for key in query.get("observed_equipment_keys", [])
        ]
        state = "READY" if lookup_state == "HIT" and reference_configurations else "GAP"
        output = {
            "state": state,
            "lookup_state": lookup_state,
            "reference_configurations": reference_configurations,
            "trim_matrix": trim_matrix,
            "observed_equipment_matches": observed_equipment_matches,
            "instance_trim_state": "UNRESOLVED",
            "factory_provenance_state": "UNRESOLVED",
            "hard_evidence_refs": query.get("hard_evidence_refs", []),
            "uncertainties": packet.payload["uncertainties"],
            "library_packet_id": packet.contract_id,
        }
        return DomainResult(
            owner=self.owner,
            status=(
                "SALES_VEHICLE_CONFIGURATION_READY"
                if state == "READY"
                else "SALES_VEHICLE_CONFIGURATION_GAP"
            ),
            output=output,
            evidence={
                "adapter_configured": True,
                "adapter_called": True,
                "context_delivered": True,
                "result_returned": True,
                "library_request_id": packet.payload["library_request_id"],
                "library_packet_id": packet.contract_id,
                "consumer": Owner.SALES_HUMAN.value,
                "projection": packet.payload["projection"],
                "contract_version": packet.schema_version,
                "source_authority_revision": packet.source_authority_revision,
                "provenance": packet.provenance,
                "currentness": packet.currentness.value,
                "lookup_state": lookup_state,
                "actual_consumed_context": sorted(packet.used_fields),
                "reference_is_instance_proof": False,
                "factory_provenance_resolved": False,
            },
            output_classifications={OutputClassification.DIAGNOSIS_ONLY},
        )

    @staticmethod
    def _match_observed_equipment(
        equipment_key: str,
        configurations: list[dict],
    ) -> dict:
        configuration_ids: list[str] = []
        classifications: list[str] = []
        for configuration in configurations:
            matching = [
                equipment
                for equipment in configuration.get("equipment", [])
                if equipment.get("equipment_key") == equipment_key
            ]
            if not matching:
                continue
            configuration_id = configuration.get("configuration_id")
            if configuration_id not in configuration_ids:
                configuration_ids.append(configuration_id)
            for equipment in matching:
                classification = equipment.get("classification")
                if classification not in classifications:
                    classifications.append(classification)
        return {
            "equipment_key": equipment_key,
            "matched_configuration_ids": configuration_ids,
            "reference_classifications": classifications,
            "evidence_role": "SUPPORTING_REFERENCE_MATCH_ONLY",
        }
