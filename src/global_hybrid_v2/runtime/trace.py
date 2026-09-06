from __future__ import annotations

import json
import sys
from copy import deepcopy
from typing import Any
from uuid import uuid4

from global_hybrid_v2.contracts import Owner, TraceEvent
from global_hybrid_v2.observer.witness import ReadOnlyWitness
from global_hybrid_v2.runtime.state import SQLiteRuntimeStateStore


class TraceBus:
    def __init__(self, witness: ReadOnlyWitness | None = None):
        # Kept as a process/bus identifier for compatibility. Governed work uses
        # a distinct trace id per task through start_task()/emit().
        self.trace_id = str(uuid4())
        self.witness = witness
        self.findings = []
        self._quarantined_evidence: dict[str, dict[str, Any]] = {}
        self._task_trace_ids: dict[str, str] = {}
        self._task_spans: dict[tuple[str, str], str] = {}
        self._journal: SQLiteRuntimeStateStore | None = None
        self._runtime_binding: tuple[str, str] | None = None
        self._action_id: str | None = None
        self._checkpoint_id: str | None = None

    def bind_runtime(
        self, journal: SQLiteRuntimeStateStore, conversation_or_thread_id: str, runtime_task_id: str
    ) -> None:
        self._journal = journal
        self._runtime_binding = (conversation_or_thread_id, runtime_task_id)

    def bind_runtime_context(self, *, action_id: str | None = None, checkpoint_id: str | None = None) -> None:
        self._action_id = action_id
        self._checkpoint_id = checkpoint_id

    def unbind_runtime(self) -> None:
        self._journal = None
        self._runtime_binding = None
        self._action_id = None
        self._checkpoint_id = None

    def attach_witness(self, witness: ReadOnlyWitness) -> None:
        if self.witness is None:
            self.witness = witness

    def start_task(self, task_id: str) -> str:
        trace_id = str(uuid4())
        self._task_trace_ids[task_id] = trace_id
        self._span_id(task_id, "GLOBAL")
        return trace_id

    def store_quarantined_evidence(
        self,
        task_id: str,
        evidence: dict[str, Any],
    ) -> None:
        if evidence:
            self._quarantined_evidence[task_id] = deepcopy(evidence)

    def quarantined_evidence_for_task(self, task_id: str) -> dict[str, Any]:
        return deepcopy(self._quarantined_evidence.get(task_id, {}))

    def findings_for_task(self, task_id: str) -> list[Any]:
        """Read-only view of Witness findings bound to one task."""
        return [finding for finding in self.findings if finding.task_id == task_id]

    def _span_id(self, task_id: str, span_owner: str) -> str:
        key = (task_id, span_owner)
        return self._task_spans.setdefault(key, str(uuid4()))

    @staticmethod
    def _print(event: TraceEvent) -> None:
        print(
            json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
            file=sys.stdout,
            flush=True,
        )

    def emit(
        self,
        *,
        task_id: str,
        stage: str,
        decision: str,
        owner: Owner | None = None,
        span_owner: str | None = None,
        metadata: dict | None = None,
    ) -> TraceEvent:
        task_trace_id = self._task_trace_ids.get(task_id)
        if task_trace_id is None:
            task_trace_id = self.start_task(task_id)
        effective_span_owner = span_owner or (owner.value if owner is not None else "GLOBAL")
        span_id = self._span_id(task_id, effective_span_owner)
        parent_span_id = None if effective_span_owner == "GLOBAL" else self._span_id(task_id, "GLOBAL")
        event = TraceEvent(
            trace_id=task_trace_id,
            task_id=task_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_owner=effective_span_owner,
            stage=stage,
            owner=owner,
            decision=decision,
            metadata=metadata or {},
            action_id=(metadata or {}).get("action_id") or self._action_id,
            checkpoint_id=self._checkpoint_id,
            conversation_or_thread_id=self._runtime_binding[0] if self._runtime_binding else None,
            runtime_task_id=self._runtime_binding[1] if self._runtime_binding else None,
        )
        if self._journal and self._runtime_binding:
            event_id = self._journal.append_event(
                {
                    "conversation_or_thread_id": self._runtime_binding[0],
                    "runtime_task_id": self._runtime_binding[1],
                    "dispatch_task_id": task_id,
                    "trace_id": task_trace_id,
                    "stage": stage,
                    "event_type": "TRACE",
                    "action_id": event.action_id,
                    "payload": event.model_dump(mode="json"),
                }
            )
            event = event.model_copy(update={"event_id": event_id})
        self._print(event)
        if self.witness:
            finding = self.witness.observe(event.model_copy(deep=True))
            if finding:
                finding = finding.model_copy(
                    update={
                        "observed_event_id": event.event_id,
                        "action_id": event.action_id,
                        "checkpoint_id": event.checkpoint_id,
                    }
                )
                self.findings.append(finding)
                if self._journal and self._runtime_binding:
                    self._journal.append_event(
                        {
                            "conversation_or_thread_id": self._runtime_binding[0],
                            "runtime_task_id": self._runtime_binding[1],
                            "dispatch_task_id": task_id,
                            "trace_id": task_trace_id,
                            "stage": "witness_finding",
                            "event_type": "WITNESS_FINDING",
                            "action_id": finding.action_id,
                            "payload": finding.model_dump(mode="json"),
                        }
                    )
            consumption_checks = self.witness.consumption_assessment_for_task(task_id)
            witness_event = TraceEvent(
                trace_id=task_trace_id,
                task_id=task_id,
                span_id=self._span_id(task_id, "WITNESS"),
                parent_span_id=self._span_id(task_id, "GLOBAL"),
                span_owner="WITNESS",
                stage="witness_observation",
                decision="FINDING" if finding else "OBSERVED",
                metadata={
                    "state": "WITNESS_FINDING" if finding else "WITNESS_OBSERVED",
                    "input_ref": stage,
                    "output_ref": finding.code if finding else None,
                    "result": "FINDING" if finding else "OBSERVED",
                    "failure_class": finding.code if finding else None,
                    "observed_stage": stage,
                    "finding_code": finding.code if finding else None,
                    "consumption_checks": consumption_checks,
                    "current_mapping_version": event.metadata.get("current_mapping_version"),
                    "resolved_referent_id": event.metadata.get("resolved_referent_id"),
                    "identity_source_id": event.metadata.get("identity_source_id"),
                    "identity_source_version": event.metadata.get("identity_source_version"),
                    "identity_currentness_token": event.metadata.get("identity_currentness_token"),
                },
            )
            self._print(witness_event)
        return event
