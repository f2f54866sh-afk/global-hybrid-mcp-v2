import pytest
from global_hybrid_v2.adapters.drive_xlsx_workbench import (
    DriveXlsxWorkbenchPort,
    WorkbenchConflict,
    WorkbenchPostwriteMismatch,
)


class FakeDrive:
    def __init__(self, payload=b"old", version="1"):
        self.payload = payload
        self.version = version
        self.mutate_before_replace = False
        self.corrupt_postwrite = False
        self.replace_calls = 0

    def metadata(self, file_id):
        return {"id": file_id, "version": self.version}

    def download(self, file_id):
        return self.payload

    def replace(self, file_id, payload, mime_type):
        self.replace_calls += 1
        if self.mutate_before_replace:
            self.payload = b"foreign"
            self.version = str(int(self.version) + 1)
            return {"id": file_id}
        self.payload = b"corrupt" if self.corrupt_postwrite else payload
        self.version = str(int(self.version) + 1)
        return {"id": file_id}


class FakeClaims:
    def __init__(self):
        self.active = {}
        self.completed = {}
        self.forced = None

    def claim(self, payload):
        if self.forced is not None:
            return self.forced
        key = (payload["file_id"], payload["preimage_version"])
        existing = self.active.get(key)
        if existing and existing["intent_sha256"] != payload["intent_sha256"]:
            return {"state": "HOLD_CONFLICT", "blocker": "WORKBENCH_PREIMAGE_ALREADY_CLAIMED"}
        if existing:
            return {"state": "IDEMPOTENT_SUCCESS", **self.completed.get(payload["claim_id"], {})}
        self.active[key] = payload
        return {"state": "CLAIMED"}

    def complete(self, payload):
        self.completed[payload["claim_id"]] = payload
        return {"state": "COMPLETED"}

    def fail(self, payload):
        return {"state": "FAILED"}


def port(drive=None, claims=None):
    return DriveXlsxWorkbenchPort(file_id="drive-file-1", drive=drive or FakeDrive(), claims=claims or FakeClaims())


def test_positive_write_and_readback():
    result = port().write(task_id="t1", intent_sha256="a"*64, new_bytes=b"new")
    assert result.state == "WRITE_AND_READBACK_PASS"
    assert result.postwrite_version == "2"


def test_no_delta_has_no_write():
    d = FakeDrive(payload=b"same")
    result = port(drive=d).write(task_id="t1", intent_sha256="a"*64, new_bytes=b"same")
    assert result.state == "NO_DELTA"
    assert d.replace_calls == 0


def test_competing_claim_holds():
    c = FakeClaims()
    c.claim({"claim_id":"x","file_id":"drive-file-1","preimage_version":"1","preimage_sha256":"x","intent_sha256":"b"*64,"task_id":"other"})
    with pytest.raises(WorkbenchConflict, match="ALREADY_CLAIMED"):
        port(claims=c).write(task_id="t1", intent_sha256="a"*64, new_bytes=b"new")


def test_stale_preimage_after_claim_holds_without_replace():
    class StaleDrive(FakeDrive):
        reads = 0
        def metadata(self, file_id):
            self.reads += 1
            if self.reads == 2:
                self.version = "2"
                self.payload = b"foreign"
            return super().metadata(file_id)
    d = StaleDrive()
    with pytest.raises(WorkbenchConflict, match="STALE_PREIMAGE"):
        port(drive=d).write(task_id="t1", intent_sha256="a"*64, new_bytes=b"new")
    assert d.replace_calls == 0


def test_postwrite_hash_mismatch_holds():
    d = FakeDrive()
    d.corrupt_postwrite = True
    with pytest.raises(WorkbenchPostwriteMismatch, match="POSTWRITE_MISMATCH"):
        port(drive=d).write(task_id="t1", intent_sha256="a"*64, new_bytes=b"new")
