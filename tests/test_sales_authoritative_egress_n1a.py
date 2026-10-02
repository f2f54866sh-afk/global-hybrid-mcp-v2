from __future__ import annotations

import ast
import inspect
from datetime import UTC, datetime, timedelta

import pytest

from global_hybrid_v2.governance.sales_final_commit import (
    REQUIRED_PRODUCT_CHECKS,
    AuthoritativeSalesTaskSnapshotV1,
    FinalOutputCommitGateV1,
    ProductCheckResultV1,
    check_set_digest,
    sha256_json,
    sha256_text,
)
from global_hybrid_v2.sales_controlled_service import ControlledSalesServiceV1

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
POLICY = "SALES_VISUAL_EXECUTION_PROFILE_20261002_V99_FINAL_CONSUMER_AUDIT_RESULT_IDENTITY_BINDING_GUARD"
PRODUCER = "controlled-sales-app-v1"
RUNTIME = "n1a-local-candidate"
BAD_COPY = "這台的重點很直接：MST 進氣＋BILSTEIN B8 已經在車上。"
GOOD_COPY = "如果你正在找已裝 MST Performance 進氣與 BILSTEIN B8 的 Tiguan R，這台符合這個條件。"


class Generator:
    def __init__(self, text=GOOD_COPY):
        self.text = text

    def generate(self, snapshot):
        return self.text


class Evaluator:
    def __init__(self, overrides=None, bind_candidate=True, bind_snapshot=True, blank_ref=None):
        self.overrides = overrides or {}
        self.bind_candidate = bind_candidate
        self.bind_snapshot = bind_snapshot
        self.blank_ref = blank_ref

    def evaluate(self, snapshot, candidate):
        candidate_digest = sha256_text(candidate)
        rows = []
        for check_id in REQUIRED_PRODUCT_CHECKS:
            rows.append(
                ProductCheckResultV1(
                    check_id=check_id,
                    disposition=self.overrides.get(check_id, "PASS"),
                    result_ref=(" " if self.blank_ref == check_id else f"result:{check_id}"),
                    snapshot_digest=(snapshot.snapshot_digest if self.bind_snapshot else "a" * 64),
                    candidate_digest=(candidate_digest if self.bind_candidate else "b" * 64),
                )
            )
        return rows


class MissingEvaluator(Evaluator):
    def evaluate(self, snapshot, candidate):
        return super().evaluate(snapshot, candidate)[:-1]


class Workbench:
    def __init__(self, state):
        self.state = state

    def terminal_disposition(self, snapshot):
        return self.state


def gate(now=lambda: NOW):
    return FinalOutputCommitGateV1(
        producer_id=PRODUCER,
        policy_ref=POLICY,
        runtime_commit=RUNTIME,
        now=now,
    )


def service(*, generator=None, evaluator=None, workbench=None):
    return ControlledSalesServiceV1(
        candidate_generator=generator or Generator(),
        product_evaluator=evaluator or Evaluator(),
        commit_gate=gate(),
        producer_id=PRODUCER,
        policy_ref=POLICY,
        global_authority_revision="GLOBAL-current",
        sales_authority_revision="SALES-current",
        library_authority_revision="LIBRARY-current",
        real_car_authority_revision="REAL_CAR-current",
        workbench_terminal_port=workbench,
        now=lambda: NOW,
        id_factory=lambda: "task-1",
    )


def run(svc, **kwargs):
    return svc.handle(
        current_user_request="幫我做 AXT-8911 這台 Tiguan R 的 8891 廣告副標題跟特色說明。",
        conversation_or_session_id="session-1",
        task_class="8891_COPY",
        target_surface="8891",
        vehicle_instance_id="WVGZZZ5NZMW539101",
        evidence_refs=["workbench:AXT-8911"],
        **kwargs,
    )


@pytest.mark.parametrize(
    ("name", "svc", "kwargs", "expected"),
    [
        ("VALID_ALL_PASS", service(), {}, "PASS"),
        (
            "META_FAIL_WITHHELD",
            service(
                generator=Generator(BAD_COPY),
                evaluator=Evaluator({"PRODUCTION_PRODUCT": "FAIL"}),
            ),
            {},
            "FAIL",
        ),
        (
            "FEATURE_SOUP_FAIL_WITHHELD",
            service(evaluator=Evaluator({"DETACHED_PRODUCT": "FAIL"})),
            {},
            "FAIL",
        ),
        ("MISSING_CHECK_HOLD", service(evaluator=MissingEvaluator()), {}, "HOLD"),
        ("RESULT_REFS_MISSING_HOLD", service(evaluator=Evaluator(blank_ref="COPY_EGRESS")), {}, "HOLD"),
        ("CANDIDATE_MISMATCH_HOLD", service(evaluator=Evaluator(bind_candidate=False)), {}, "HOLD"),
        (
            "WORKBENCH_VERSION_MISMATCH_HOLD",
            service(workbench=Workbench("HOLD")),
            {"persistence_required": True},
            "HOLD",
        ),
        (
            "NO_DELTA_CAN_COMMIT",
            service(workbench=Workbench("NO_DELTA")),
            {"persistence_required": True},
            "PASS",
        ),
        (
            "WRITE_READBACK_CAN_COMMIT",
            service(workbench=Workbench("WRITE_AND_READBACK_PASS")),
            {"persistence_required": True},
            "PASS",
        ),
        ("PERSISTENCE_FAIL_WITHHOLDS", service(), {"persistence_required": True}, "HOLD"),
        ("DETACHED_FAIL_WITHHELD", service(evaluator=Evaluator({"DETACHED_PRODUCT": "FAIL"})), {}, "FAIL"),
        (
            "CONTEXT_ISOLATION_HOLD_WITHHELD",
            service(evaluator=Evaluator({"CONTEXT_ISOLATION": "HOLD"})),
            {},
            "HOLD",
        ),
        (
            "INVARIANCE_FAIL_WITHHELD",
            service(evaluator=Evaluator({"DISPOSITION_INVARIANCE": "FAIL"})),
            {},
            "FAIL",
        ),
        (
            "SERIALIZATION_FAIL_WITHHELD",
            service(evaluator=Evaluator({"PUBLIC_SERIALIZATION": "FAIL"})),
            {},
            "FAIL",
        ),
    ],
)
def test_semantic_matrix(name, svc, kwargs, expected):
    outcome = run(svc, **kwargs)
    assert outcome.receipt.final_output_commit == expected, name
    if expected == "PASS":
        assert outcome.public_output is not None
        assert outcome.receipt.public_output_digest == sha256_text(outcome.public_output)
    else:
        assert outcome.public_output is None
        assert outcome.receipt.public_output_digest is None


def _snapshot(**updates):
    base = AuthoritativeSalesTaskSnapshotV1(
        task_id="task-1",
        conversation_or_session_id="session-1",
        current_user_request="request",
        current_user_request_sha256=sha256_text("request"),
        task_class="8891_COPY",
        target_surface="8891",
        direct_user_hard_requirements=[],
        hard_requirements_digest=sha256_json([]),
        sales_execution_policy_ref=POLICY,
        global_authority_revision="GLOBAL-current",
        sales_authority_revision="SALES-current",
        library_authority_revision="LIBRARY-current",
        real_car_authority_revision="REAL_CAR-current",
        evidence_refs=[],
        evidence_set_digest=sha256_json([]),
        generation=1,
        issued_at=NOW,
        valid_until=NOW + timedelta(minutes=5),
        producer_id=PRODUCER,
        snapshot_digest="0" * 64,
    )
    base = base.model_copy(update={"snapshot_digest": sha256_json(base.digest_payload())})
    if updates:
        base = base.model_copy(update=updates)
    return base


def _decision(snapshot, candidate=GOOD_COPY, evaluator=None):
    ev = evaluator or Evaluator()
    return gate().decide(snapshot=snapshot, candidate=candidate, results=ev.evaluate(snapshot, candidate))


def test_snapshot_digest_forged_fails_closed():
    snapshot = _snapshot(snapshot_digest="f" * 64)
    decision = _decision(snapshot)
    outcome = gate().commit(
        snapshot=snapshot,
        candidate=GOOD_COPY,
        decision=decision,
        persistence_required=False,
    )
    assert outcome.public_output is None
    assert outcome.receipt.withhold_blocker == "SNAPSHOT_DIGEST_MISMATCH"


def test_snapshot_stale_holds():
    snapshot = _snapshot(valid_until=NOW - timedelta(seconds=1))
    decision = _decision(snapshot)
    outcome = gate().commit(
        snapshot=snapshot,
        candidate=GOOD_COPY,
        decision=decision,
        persistence_required=False,
    )
    assert outcome.public_output is None
    assert outcome.receipt.withhold_blocker in {
        "SNAPSHOT_DIGEST_MISMATCH",
        "SNAPSHOT_STALE",
    }


def test_policy_mismatch_holds():
    snapshot = _snapshot(sales_execution_policy_ref="wrong-policy")
    snapshot = snapshot.model_copy(update={"snapshot_digest": sha256_json(snapshot.digest_payload())})
    decision = _decision(snapshot)
    outcome = gate().commit(
        snapshot=snapshot,
        candidate=GOOD_COPY,
        decision=decision,
        persistence_required=False,
    )
    assert outcome.public_output is None
    assert outcome.receipt.withhold_blocker == "POLICY_REF_MISMATCH"


def test_legacy_chat_not_authority():
    # The controlled service has no entry point that accepts a caller-authored snapshot or decision.
    params = inspect.signature(ControlledSalesServiceV1.handle).parameters
    assert "snapshot" not in params
    assert "decision" not in params
    with pytest.raises(TypeError):
        run(service(), snapshot=_snapshot())


def test_rejected_candidate_bytes_never_appear_in_public_return():
    outcome = run(service(generator=Generator(BAD_COPY), evaluator=Evaluator({"PRODUCTION_PRODUCT": "FAIL"})))
    assert outcome.public_output is None
    assert BAD_COPY not in outcome.model_dump_json()


def test_commit_receipt_cannot_be_model_supplied():
    assert "receipt" not in inspect.signature(ControlledSalesServiceV1.handle).parameters
    assert "final_output_commit" not in inspect.signature(ControlledSalesServiceV1.handle).parameters


def test_required_check_set_is_fixed_and_digest_bound():
    snapshot = _snapshot()
    decision = _decision(snapshot)
    assert decision.required_check_set_digest == check_set_digest(REQUIRED_PRODUCT_CHECKS)
    assert set(decision.result_refs) == set(REQUIRED_PRODUCT_CHECKS)


def test_n1a_candidate_has_no_network_or_file_write_imports():
    forbidden = {"openai", "requests", "httpx", "urllib", "socket", "pathlib", "os", "subprocess"}
    for module in (
        "global_hybrid_v2.governance.sales_final_commit",
        "global_hybrid_v2.sales_controlled_service",
    ):
        source = inspect.getsource(__import__(module, fromlist=["*"]))
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports |= {
            (node.module or "").split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert forbidden.isdisjoint(imports)


def test_duplicate_required_check_holds():
    snapshot = _snapshot()
    rows = Evaluator().evaluate(snapshot, GOOD_COPY)
    rows.append(rows[0].model_copy())
    decision = gate().decide(snapshot=snapshot, candidate=GOOD_COPY, results=rows)
    assert decision.aggregate_product_disposition == "HOLD"
    assert any(item.endswith(":DUPLICATE") for item in decision.unresolved_check_ids)


def test_forged_aggregate_pass_is_rejected_even_with_valid_recomputed_digest():
    snapshot = _snapshot()
    decision = _decision(snapshot)
    per_check = dict(decision.per_check_dispositions)
    per_check["PRODUCTION_PRODUCT"] = "FAIL"
    forged = decision.model_copy(
        update={
            "per_check_dispositions": per_check,
            "aggregate_product_disposition": "PASS",
            "failed_check_ids": [],
            "decision_digest": "0" * 64,
        }
    )
    forged = forged.model_copy(update={"decision_digest": sha256_json(forged.digest_payload())})
    outcome = gate().commit(
        snapshot=snapshot,
        candidate=GOOD_COPY,
        decision=forged,
        persistence_required=False,
    )
    assert outcome.public_output is None
    assert outcome.receipt.withhold_blocker == "DECISION_AGGREGATE_MISMATCH"


def test_forged_missing_result_ref_set_is_rejected():
    snapshot = _snapshot()
    decision = _decision(snapshot)
    refs = dict(decision.result_refs)
    refs.pop("COPY_EGRESS")
    forged = decision.model_copy(update={"result_refs": refs, "decision_digest": "0" * 64})
    forged = forged.model_copy(update={"decision_digest": sha256_json(forged.digest_payload())})
    outcome = gate().commit(
        snapshot=snapshot,
        candidate=GOOD_COPY,
        decision=forged,
        persistence_required=False,
    )
    assert outcome.public_output is None
    assert outcome.receipt.withhold_blocker == "DECISION_RESULT_REF_SET_MISMATCH"
