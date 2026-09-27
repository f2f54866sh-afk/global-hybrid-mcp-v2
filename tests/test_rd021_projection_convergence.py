from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from global_hybrid_v2.canonical_projection import (
    ProjectionOutboxWorker,
    XlsxProjectionVerifier,
)
from global_hybrid_v2.transactional_vehicle_store import (
    CanonicalConflict,
    CreativeAdmission,
)
from global_hybrid_v2.workbench_mutation import AI_SHEET, _cell, _cell_value, _header, _row, _Workbook
from tests import test_rd021_transactional_canonical_store as canonical_tests
from tests._rd021_projection_fixture import AtomicProjectionFixture
from tests.test_rd021_completion_fence import q


def _states(path):
    with sqlite3.connect(path) as connection:
        return dict(connection.execute("SELECT event_id, state FROM projection_outbox"))


def _revisions(path):
    with sqlite3.connect(path) as connection:
        return dict(connection.execute(
            "SELECT event_id, satisfied_by_revision FROM projection_outbox"
        ))


def _cells(payload):
    book = _Workbook.parse(payload)
    ai = book.root(AI_SHEET)
    header = _header(ai, book.shared)
    row = _row(ai, 13)
    return {name: (_cell_value(cell, book.shared) if (cell := _cell(row, col)) is not None else "")
            for name, col in header.items()}


def _creative(revision=0, admission_id="creative:m1", media_id="media:ai-generated"):
    return CreativeAdmission(
        admission_id, "8891:S4806251", revision, media_id, "root:creative",
        "AI_GENERATED", "FORBIDDEN", ("FB", "8891"), "request:creative", "task:creative",
    )


@pytest.fixture
def candidate(tmp_path):
    return canonical_tests.candidate.__wrapped__(tmp_path)


def test_failed_revision_one_retries_against_latest_two_and_terminalizes_both(candidate):
    store, path, raw, _ = candidate
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    store.commit_verified(canonical_tests.mutation())
    sink.fail_writes = True
    assert worker.run("m1") == "PROJECTION_FAILED"
    store.commit_verified(canonical_tests.mutation(mutation_id="m2", revision=1, value="sport plus"))
    sink.fail_writes = False
    assert worker.run("m1") == "SUPERSEDED_BY_LATER_REVISION"
    assert _states(path) == {
        "m1": "SUPERSEDED_BY_LATER_REVISION", "m2": "PROJECTED",
    }
    assert _revisions(path) == {"m1": 2, "m2": 2}
    assert _cells(sink.payload)["CANONICAL_REVISION"] == "2"
    assert _cells(sink.payload)["實際配備狀態"] == "sport plus"


def test_later_event_can_satisfy_earlier_pending_without_old_write(candidate):
    store, path, raw, _ = candidate
    store.commit_verified(canonical_tests.mutation())
    store.commit_verified(canonical_tests.mutation(mutation_id="m2", revision=1, value="sport plus"))
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    assert worker.run("m2") == "PROJECTED"
    writes = sink.write_calls
    assert worker.run("m1") == "SUPERSEDED_BY_LATER_REVISION"
    assert sink.write_calls == writes
    assert _states(path)["m1"] == "SUPERSEDED_BY_LATER_REVISION"
    assert _cells(sink.payload)["CANONICAL_REVISION"] == "2"


def test_concurrent_projection_workers_never_decrease_revision(candidate):
    store, path, raw, _ = candidate
    store.commit_verified(canonical_tests.mutation())
    store.commit_verified(canonical_tests.mutation(mutation_id="m2", revision=1, value="sport plus"))
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(worker.run, ("m1", "m2")))
    assert set(results) == {"SUPERSEDED_BY_LATER_REVISION", "PROJECTED"}
    assert _cells(sink.payload)["CANONICAL_REVISION"] == "2"
    assert sink.write_calls == 1
    assert _states(path)["m1"] == "SUPERSEDED_BY_LATER_REVISION"


def test_creative_link_materializes_without_truth_or_original_media_change(candidate):
    store, path, raw, _ = candidate
    before = store.read_vehicle("8891:S4806251")
    store.admit_creative(_creative())
    state = store.read_projection_state("8891:S4806251")
    assert state.canonical_revision == 1
    assert state.verified_state == before.verified_state == {}
    assert state.original_media_refs == ("original:1",)
    assert len(state.creative_media_refs) == 1
    ref = state.creative_media_refs[0]
    assert ref.media_asset_id == "media:ai-generated"
    assert ref.channels == ("8891", "FB")
    assert store.independent_evidence_count("8891:S4806251") == 0
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    assert worker.run("creative:m1") == "PROJECTED"
    cells = _cells(sink.payload)
    assert json.loads(cells["銷售素材Refs"]) == [ref.creative_ref_id]
    assert cells["原始媒體Refs"] == "original:1"
    assert cells["CANONICAL_REVISION"] == "1"
    assert store.admit_creative(_creative()).postwrite_version == "1"
    assert store.admit_creative(replace(_creative(), admission_id="creative:m2")).state.value == "NO_DELTA"
    assert _states(path) == {"creative:m1": "PROJECTED"}
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM vehicle_media_link").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM vehicle_field_evidence").fetchone()[0] == 0


def test_creative_retry_after_later_truth_mutation_coalesces(candidate):
    store, path, raw, _ = candidate
    store.admit_creative(_creative())
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    sink.fail_writes = True
    assert worker.run("creative:m1") == "PROJECTION_FAILED"
    store.commit_verified(canonical_tests.mutation(mutation_id="truth:m2", revision=1))
    sink.fail_writes = False
    assert worker.run("creative:m1") == "SUPERSEDED_BY_LATER_REVISION"
    assert _states(path)["truth:m2"] == "PROJECTED"
    cells = _cells(sink.payload)
    assert json.loads(cells["銷售素材Refs"]) == [
        store.read_projection_state("8891:S4806251").creative_media_refs[0].creative_ref_id
    ]
    assert cells["原始媒體Refs"] == "original:1"
    assert cells["實際配備狀態"] == "sport"
    assert store.independent_evidence_count("8891:S4806251") == 1


def test_external_target_row_mutation_holds_without_last_write_wins(candidate):
    store, path, raw, _ = candidate
    store.commit_verified(canonical_tests.mutation())
    sink = AtomicProjectionFixture(raw)
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    assert worker.run("m1") == "PROJECTED"
    store.commit_verified(canonical_tests.mutation(mutation_id="m2", revision=1, value="sport plus"))

    def tamper(root):
        target = next(row for row in root.find(q("sheetData")).findall(q("row"))
                      if row.get("r") == "13")
        cell = next(cell for cell in target.findall(q("c")) if cell.get("r") == "E13")
        cell.find(f"{q('is')}/{q('t')}").text = "external:modified"

    sink.external_edit(tamper)
    writes = sink.write_calls
    assert worker.run("m2") == "HOLD_CONFLICT"
    assert sink.write_calls == writes
    assert _states(path)["m2"] == "HOLD_CONFLICT"
    assert store.read_vehicle("8891:S4806251").revision == 2


def test_external_preimage_change_during_cas_holds(candidate):
    store, path, raw, _ = candidate
    store.commit_verified(canonical_tests.mutation())
    sink = AtomicProjectionFixture(raw)
    original = sink.replace_if_preimage

    def raced(observed, desired, state):
        sink.version += 1
        original(observed, desired, state)

    sink.replace_if_preimage = raced
    worker = ProjectionOutboxWorker(store, sink, XlsxProjectionVerifier(sink))
    assert worker.run("m1") == "HOLD_CONFLICT"
    assert _states(path)["m1"] == "HOLD_CONFLICT"
    assert _cells(sink.payload)["CANONICAL_REVISION"] == ""


def test_import_with_unresolved_creative_baseline_holds(candidate):
    _, _, raw, _ = candidate
    from global_hybrid_v2.canonical_cutover import compile_import
    from global_hybrid_v2.company_commercial_completion import CANONICAL_WORKBENCH_FILE_ID
    from global_hybrid_v2.workbench_mutation import _cell, _set_cell
    from tests.test_rd021_creative_schema_migration import edit_sheet

    def add_creative(root):
        row = next(item for item in root.find(q("sheetData")).findall(q("row"))
                   if item.get("r") == "13")
        _set_cell(_cell(row, 6, create=True), '["creative:unresolved"]')

    with pytest.raises(CanonicalConflict, match="MIGRATION_CREATIVE_LINKAGE_REQUIRED"):
        compile_import(edit_sheet(raw, add_creative), file_id=CANONICAL_WORKBENCH_FILE_ID)
