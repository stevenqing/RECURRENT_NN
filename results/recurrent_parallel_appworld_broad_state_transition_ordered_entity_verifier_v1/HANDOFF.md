# Broad State-Transition Ordered-Entity Verifier Handoff

## Status: **`RPD_APPWORLD_BROAD_STATE_TRANSITION_ORDERED_ENTITY_VERIFIER_UNSAFE`**

This step tests a broad ordered/cursor baseline for remaining state-transition entity fields. It is intentionally simple: a candidate is valid if it equals the write-ordinal-th unique same-field entity from same-app pre-write read responses.

## Result

| Decision | Count |
|---|---:|
| `commit_live` | 257 |
| `ambiguous_both_valid` | 0 |
| `abstain_no_valid` | 292 |
| `unsafe_unique_wrong` | 28 |

## Interpretation

The broad ordered-entity rule is too coarse to be a verifier. It recovers many live commits, but 28 unsafe unique-wrong cases violate the zero-unsafe safety gate. This confirms that state-transition proofs need schema-specific effect/cursor predicates, not just an ordinal over same-field entities.

## Safe Schemas Inside The Failed Baseline

Several schemas had zero unsafe under this rule and may be used only through an explicitly frozen filtered ledger, not as a general verifier claim. Unsafe schemas must remain fail-closed until stronger semantics are implemented.

## Key Artifacts

- Contract: `specs/recurrent_parallel_appworld_broad_state_transition_ordered_entity_verifier_v1.json`
- Spec: `specs/recurrent_parallel_appworld_broad_state_transition_ordered_entity_verifier_v1.md`
- Runner: `analysis/appworld_broad_state_transition_ordered_entity_verifier.py`
- Report: `results/recurrent_parallel_appworld_broad_state_transition_ordered_entity_verifier_v1/REPORT.md`
- Results: `results/recurrent_parallel_appworld_broad_state_transition_ordered_entity_verifier_v1/results.json`
- Value-free rows: `results/recurrent_parallel_appworld_broad_state_transition_ordered_entity_verifier_v1/rows.json`

## Next Route

Build a filtered safe ledger that imports only zero-unsafe schemas from this failed baseline while preserving the failed baseline result. Then implement stronger schema-specific verifiers for the unsafe schemas.