from __future__ import annotations

import json
import sys
from uuid import uuid4

from global_hybrid_v2.contracts import Owner, TraceEvent
from global_hybrid_v2.observer.witness import ReadOnlyWitness


class TraceBus:
    def __init__(self, witness: ReadOnlyWitness | None = None):
        self.trace_id = str(uuid4())
        self.witness = witness
        self.findings = []

    def emit(
        self,
        *,
        task_id: str,
        stage: str,
        decision: str,
        owner: Owner | None = None,
        metadata: dict | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            trace_id=self.trace_id,
            task_id=task_id,
            stage=stage,
            owner=owner,
            decision=decision,
            metadata=metadata or {},
        )
        print(json.dumps(event.model_dump(mode="json"), ensure_ascii=False), file=sys.stdout, flush=True)
        if self.witness:
            finding = self.witness.observe(event.model_copy(deep=True))
            if finding:
                self.findings.append(finding)
        return event
