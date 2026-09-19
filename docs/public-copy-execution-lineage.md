# Public Copy terminal execution lineage

This bounded repair uses the existing `TraceBus`, SQLite `runtime_event_journal`,
`ReadOnlyWitness`, Dispatcher and response egress. It does not change Sales
Canonical, the Sales + Visual V84 profile/kernel, or any product acceptance policy.

## Integration boundary

The host identifies a public commercial Copy request with
`TaskRequest.public_commercial_copy=True`, supplies the nonempty, distinct
`public_copy_requirement_ids`, exact generation/frame IDs, and an immutable typed
`PublicCopyOracleInput`. Ordinary requests keep their existing path. This is an
explicit host contract, not a natural-language classifier.

The packet contains its schema and packet identity, exact task scope and frame,
the canonical expected terminal candidate and digest, typed hard requirements,
classified literal/calibration records, selected Primary
reason-to-care, typed supporting proofs and evidence references, optional product
qualification, authority revisions, source bindings, producer identity, provenance
and a bounded validity window. It is not derived from prompt parsing,
`ContextItem.payload`, domain output, or model self-report.

`PublicCopyOracleGate` follows the Host projection pattern. Its production default
uses an unavailable verifier and therefore fails closed. A configured Host verifier
must establish producer/currentness authenticity. The gate also checks the time
window, exact task/generation/frame binding, requirement manifest, current authority
revisions, and that every consumed evidence ref resolves to an admitted current
context item or current authority revision. The real Host producer/verifier is not
implemented or connected in this repository.

Configure `create_application(public_copy_checks=...)` (or Dispatcher) with an
application-owned `PublicCopyChecks` implementation that executes the existing
checks. No production implementation is installed here. Missing configuration,
missing durable binding, malformed receipts and execution exceptions fail closed.
Domain-result evidence and prompt self-reports cannot configure this port or
supply its execution receipts. Test ports and Sales results are recording fakes.

Each call receives a stage, immutable canonical JSON for the exact terminal
candidate (`output` plus `final_response_object`), the immutable acceptance witness
JSON for subsequent calls, the requirement IDs, and canonical oracle-input JSON plus
its admitted digest. It returns `CopyCheckResult`:

- `decision`: `PASS` or `FAIL`.
- `exact_candidate_digest`: SHA-256 of canonical candidate JSON (UTF-8, sorted
  keys, compact separators, Unicode preserved, nonfinite numbers rejected).
- `witness_digest`: subsequent checks must independently return the digest of
  the supplied witness JSON. Production and Detached receive the identical JSON.
- `details`: JSON execution proof. Acceptance requires
  `public_copy_acceptance_witness`, `non_binding_literal_leak_check` and
  `supporting_proof_serialization`, each `PASS`; a nonempty `supporting_proof`
  object; and `hard_requirement_coverage` mapping every requested ID to
  `{decision: PASS, exact_candidate_digest: ...}`. Invariance and audit require
  `disposition_invariance: PASS` and `copy_egress_audit: PASS`, respectively.

The runtime computes the witness digest over the acceptance receipt's exact
candidate digest and details. It serializes the proof before emitting the receipt;
it does not infer semantic product correctness from the copy text. The configured
product checks remain responsible for their actual evaluations.

## Durable consumption

Oracle admission, the candidate, five required stages, and final `response_egress`
are appended via TraceBus to the existing journal. The existing journal envelope supplies runtime
task ID, dispatch task ID and trace ID. Each check and egress reference the actual
journal event IDs of all its predecessor inputs. Both oracle receipts carry the
same acceptance witness digest. The candidate receipt also references its task
contract and records the requirement manifest.

At egress and closure, Witness queries the SQLite journal, bounded by the terminal
event ID. It requires a single ordered chain in the same dispatch/runtime task and
trace, all decisions PASS, identical oracle-input/task/generation/frame binding,
exact candidate and witness digest equality, complete
candidate-bound coverage and the required proof checks. Missing, duplicate,
out-of-order, mismatched or post-terminal evidence fails. All eight check results
are persisted as `WITNESS_ASSESSMENT` in that same journal; failures also use the
existing `WITNESS_FINDING` mechanism. Dispatcher suppresses Copy output on failure
before committing the result. No second store or tracing authority is introduced.

After reopening SQLite, `ReadOnlyWitness.assess_public_copy(...)` independently
recomputes the eight checks using the conversation, runtime task, dispatch task,
trace and terminal event IDs; it does not trust the persisted assessment's PASS.
Public Copy does not use the ordinary committed-output replay shortcut: a new
execution requires a fresh runtime task and returns
`PUBLIC_COPY_REPLAY_REQUIRES_NEW_DISPATCH` otherwise. Read-only journal inspection
of the completed execution remains available after reopen.

## Qualification

`tests/test_public_copy_lineage.py` and `tests/test_public_copy_oracle_edge.py` cover
typed admission, positive dispatch/checkpoint/reopen;
every missing required stage; candidate and witness mismatch; invariance and audit
failure; self-asserted and post-hoc proof; ordinary-task isolation; invalid receipt,
proof and evaluator errors; and replay isolation. All use synthetic Copy and
recording checks, without real Sales/product/image or publishing side effects.

This qualifies traced-runtime implementation only. It does **not** prove that a
ChatGPT Sales + Visual Project is connected to this runtime, or that a production
product oracle adapter is configured or semantically qualified.
