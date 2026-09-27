from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workbench_claim_schema_and_worker_control_paths_are_bounded():
    schema = (ROOT / "infra/vehicle_knowledge/schema.sql").read_text()
    worker = (ROOT / "infra/vehicle_knowledge/worker.js").read_text()

    assert "CREATE TABLE workbench_write_claim(" in schema
    assert "UNIQUE(file_id, preimage_version)" in schema

    for path in (
        "/internal/control/workbench-write-claim",
        "/internal/control/workbench-write-complete",
        "/internal/control/workbench-write-fail",
    ):
        assert path in worker

    assert "WORKBENCH_PREIMAGE_ALREADY_CLAIMED" in worker
    assert 'if (!controlAuthorized(request, env)) return json({error: "CONTROL_AUTH_REQUIRED"}, 403);' in worker
