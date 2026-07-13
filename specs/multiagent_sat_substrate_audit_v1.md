# Community SAT Substrate Audit v1

- Date: 2026-07-12
- Purpose: second-substrate replication of the graph-coloring tail-risk/coupling result
- GPU/LLM use: none

## Reusable repository components

1. [SAT generators](../tasks/sat/generators.py)
   - canonical CNF representation: clauses are lists of signed 1-based variable IDs;
   - `SATInstance` stores clauses and oracle traces;
   - planted/community structure is not supported.
2. [DPLL oracle](../tasks/oracle/dpll_oracle.py)
   - complete recursive solve for small CSPs;
   - records branch, propagation, contradiction, backtrack, and solved events;
   - uses MRV, value order 0 then 1, and chronological rollback.
3. [Symbolic CSP utilities](../llm_operator/symbolic_filter.py)
   - SAT clause-to-constraint conversion;
   - partial-assignment consistency, valid values, status, and propagation fixpoint.
4. [Trace conversion](../tasks/oracle/trace_generator.py)
   - converts oracle traces to training examples;
   - not suitable for conflict-directed target extraction because traces omit conflict clauses.

## Missing capabilities

- no community-structured planted CNF generator;
- no exact coupling control at fixed clause count;
- no fixed global variable order in the oracle API;
- no conflict sets/nogoods/backjump targets;
- no owner-local independent loops;
- no equal-total-memory monolith/sharded controls for SAT;
- no compact internal official verifier returning full-assignment clause validity.

## Implementation decision

Do not modify `DPLLOracle`; existing experiments depend on its MRV semantics.

Add a separate community-SAT substrate with:

1. planted satisfiable 3-CNF;
2. exactly four variable communities;
3. exact total clause count and exact cross-community clause count;
4. fixed deterministic global variable order plus per-community restrictions;
5. pure fixed-order search without hidden unit-propagation state;
6. explicit conflict extraction from currently falsified clauses;
7. global-trail and owner-local CBJ under identical variable/value order;
8. official full-clause verification;
9. the same work, recovery-window, request/ack, and failure-penalty accounting as graph coloring.

Pure fixed-order search is deliberate: it makes dependencies, rollback targets, and memory windows auditable and prevents MRV or propagation from changing the compared policy across arms.

## Community and coupling definition

- Variables: 48, IDs 1–48
- Communities: four contiguous blocks of 12 variables
- Clause size: exactly 3 distinct variables
- Total clauses: exactly 192
- Low coupling: 10% cross-community clauses, rounded once and fixed
- High coupling: 40% cross-community clauses, rounded once and fixed
- Intra clause: all three variables owned by one community
- Cross clause: variables span at least two communities
- Every clause has exactly one literal true under the planted assignment, increasing constraint sharpness while guaranteeing satisfiability

The planted assignment is used only for generation and final validity auditing. Search arms never receive it.

## Capacity strata

For each candidate, run only unlimited fixed-order structural references:

- global-trail CBJ to measure maximum global rollback distance;
- the same global trail with per-community local-register views to measure maximum target-owner rollback distance.

With `R=8`:

- `under`: global recovery distance ≤8;
- `over_local_fit`: global recovery distance >8 and local recovery distance ≤8.

Selection reads no evaluated bounded-arm outcome.

## Recommended arm family

1. `independent_local_cbj_v1_sat`;
2. `factorized_central_cbj_sat`;
3. `independent_local_random_valid_sat`;
4. `independent_local_no_cross_sat`;
5. `global_trail_cbj_sat`;
6. `centralized_sharded_MR_sat`;
7. `monolith_MR_sat`;
8. `monolith_R_sat`.

## Main methodological risk

A planted 3-SAT pool may be too easy or may not populate both recovery strata. Pool-completeness and structural-reference gates are therefore evaluated on a development seed before any independent pool is frozen. If the fixed generator cannot populate all four cells, the v1 contract fails rather than tuning on evaluated-arm outcomes.
