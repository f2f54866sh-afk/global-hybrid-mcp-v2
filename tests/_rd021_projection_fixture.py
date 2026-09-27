"""Isolated atomic projection sink fixture; never a Drive production adapter."""
from __future__ import annotations

import hashlib
import io
import threading
import xml.etree.ElementTree as ET
import zipfile

from global_hybrid_v2.canonical_projection import (
    DeterministicXlsxProjectionBuilder,
    ProjectionEvent,
    ProjectionObservation,
)
from global_hybrid_v2.transactional_vehicle_store import CanonicalConflict, VehicleProjectionState
from global_hybrid_v2.workbench_mutation import _cell, _set_cell
from tests.test_rd021_completion_fence import q


def _edit_sheet(payload: bytes, edit) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload)) as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            raw = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(raw)
                edit(root)
                raw = ET.tostring(root)
            target.writestr(info, raw)
    return output.getvalue()


class AtomicProjectionFixture:
    def __init__(self, source: bytes):
        builder = DeterministicXlsxProjectionBuilder()

        def add_field_header(root):
            header = root.find(q("sheetData")).findall(q("row"))[0]
            _set_cell(_cell(header, 7, create=True), "實際配備狀態")

        self.payload = builder.add_revision_schema(_edit_sheet(source, add_field_header))
        self.version = 1
        self.fail_writes = False
        self.write_calls = 0
        self._lock = threading.Lock()
        self.builder = builder

    def metadata(self, file_id: str) -> dict:
        with self._lock:
            return {"version": str(self.version)}

    def download(self, file_id: str) -> bytes:
        with self._lock:
            return self.payload

    def replace_if_preimage(self, observed: ProjectionObservation,
                            desired: ProjectionEvent, state: VehicleProjectionState) -> None:
        with self._lock:
            self.write_calls += 1
            if self.fail_writes:
                raise OSError("isolated projection unavailable")
            if (observed.file_version != str(self.version)
                or observed.file_sha256 != hashlib.sha256(self.payload).hexdigest()):
                raise CanonicalConflict("HOLD_PROJECTION_PREIMAGE_CHANGED")
            output = self.builder.build(self.payload, desired, state)
            if output != self.payload:
                self.payload = output
                self.version += 1

    def external_edit(self, edit) -> None:
        with self._lock:
            self.payload = _edit_sheet(self.payload, edit)
            self.version += 1
