# Community SAT Tail-Risk Replication Contract v1

- Frozen date: 2026-07-12
- Stage: symbolic second-substrate replication
- Parent result: [Graph-color structural closeout](../results/multiagent_structural_confirmatory/CLOSEOUT.md)
- Substrate audit: [Community SAT audit](multiagent_sat_substrate_audit_v1.md)
- Headline eligibility: **false**
- GPU/LLM use: none

## Scientific question

Does the graph-coloring pattern replicate on an independently constructed community-SAT substrate?

The target pattern is not a positive free lunch. It is:

1. factorization often reduces work when both arms solve;
2. rare factorized failures dominate failure-penalized expected work;
3. cross-community coupling increases failure/work;
4. cross-agent recovery is necessary;
5. same-order central factorization shares the same robustness boundary.

## Frozen generator

- Variables: 48
- Communities: 4 contiguous blocks ×12 variables
- Clause count: exactly 192
- Clause size: exactly 3 distinct variables
- Planted assignment: deterministic pseudorandom bits per candidate
- Literal construction: exactly one literal true under the planted assignment in every clause
- Duplicate clauses: forbidden after canonical signed-literal sorting
- Low coupling: exactly `round(0.10 × 192)=19` cross-community clauses
- High coupling: exactly `round(0.40 × 192)=77` cross-community clauses
- Global variable order: deterministic pseudorandom permutation per candidate
- Value order: 0, then 1

The planted assignment is unavailable to every search arm.

## Structural search and strata

Search uses fixed-order pure backtracking without unit propagation. A partial assignment is invalid only when it fully falsifies a clause.

For a variable/value failure, blockers are the currently assigned variables in falsified clauses for which the current variable is the latest variable under the frozen order. Conflict sets are propagated to the selected earlier target.

Unlimited structural reference cap: 100,000 branch attempts.

With `R=8`, define:

- `under`: max global rollback distance ≤8;
- `over_local_fit`: max global rollback distance >8 and max target-owner local rollback distance ≤8.

Candidate selection uses only:

- planted/full-clause validity;
- unlimited reference solve;
- exact coupling and clause count;
- the frozen recovery-distance stratum.

No bounded evaluated-arm outcome may affect selection.

## Frozen seeds and splits

### Development

- Base seed: 210000
- Maximum candidates per coupling: 20,000
- Target: 16 instances/cell
- First structurally accepted candidates in increasing candidate index
- Smoke: first four accepted instances/cell after pool completeness

### Independent replication

- Base seed: 310000
- Maximum candidates per coupling: 40,000
- Target: 50 instances/cell
- Zero instance/seed/clause-hash overlap with development
- No smoke on independent instances

If development or independent pool completeness fails, v1 returns `SAT_POOL_NO_GO`; generator parameters are not altered in place.

## Frozen resources

- Agents: `M=4`
- Per-agent recovery window: `R=8`
- Equal-total-memory window: `MR=32`
- Bounded activation/branch cap: 20,000
- Pending request cap: 16
- Failure-penalized work: `max(observed_work, 20000)` for unsolved episodes

Work definitions match graph coloring:

$$
W_{global}=branch\_attempts+retractions+cross\_block\_messages,
$$

$$
W_{factorized}=branch\_attempts+retractions+requests+acknowledgements.
$$

## Frozen arms

1. `independent_local_cbj_sat`;
2. `factorized_central_cbj_sat`;
3. `independent_local_random_valid_sat`;
4. `independent_local_no_cross_sat`;
5. `global_trail_cbj_sat`;
6. `centralized_sharded_MR_sat`;
7. `monolith_MR_sat`;
8. `monolith_R_sat`.

All arms use the same variable order, value order, clause visibility, and full current assignment. The distinction is rollback state/ownership, not information.

## Mandatory protocol and validity gates

- every solved assignment covers all 48 variables with values in `{0,1}`;
- every clause is satisfied;
- no planted assignment fallback;
- owner-only local mutation;
- zero cross-agent direct mutation;
- acyclic earlier-priority rollback requests;
- versioned stale-idempotent request handling;
- request/execution/NACK/ack conservation;
- no executed rollback outside `R`;
- local recoverable occupancy ≤8;
- pending channel ≤16;
- deterministic replay;
- central/global arms never exceed their declared window.

Any violation yields `SAT_PROTOCOL_FAIL`.

## Development gates

1. all four structural cells contain 16 instances;
2. protocol smoke passes on four instances/cell;
3. official planted and solver assignment checks pass;
4. deterministic replay passes;
5. no generator outcome selection occurs.

A development PASS authorizes only hash-locking and independent execution.

## Independent readout

### F1 — Frequent-case factorization

In `over_low`, among jointly solved proposed/monolith pairs:

- proposed/monolith raw-work ratio ≤0.80; and
- proposed work is lower on at least 35/50 paired instances.

### T1 — Tail-risk reversal

Compute:

$$
q^*=\frac{W_m-W_s}{20000-W_s},
$$

where $W_s$ is mean proposed work among proposed-success episodes and $W_m$ is mean monolith-MR work.

Tail-risk replication requires:

- proposed failure rate $q>q^*$;
- at least two monolith-only solves in `over_low`;
- proposed/monolith failure-penalized work ratio ≥1.0.

### T2 — Same-order robustness boundary

`factorized_central_cbj_sat` and `independent_local_cbj_sat` must have solve rates within 0.05, and at least half of proposed over-low failures must also fail under central factorization.

### C1 — Coupling boundary

For proposed factorization:

- over-high/over-low failure-penalized work ratio ≥1.20 or over-high solve at least 0.10 lower;
- both all-episode and solved-only work are reported.

### N1 — Coordination necessity

In at least one over-capacity cell:

- proposed solve exceeds no-cross by at least 0.20; or
- `NO_CROSS_RECOVERY` occurs on at least 25% of no-cross rows.

### R1 — Route identifiability

Deepest and random-valid differ by at least 0.10 solve or 20% failure-penalized work at solve non-inferiority within 0.10. Direction is not assumed.

## Verdicts

- `SAT_TAIL_RISK_REPLICATION`: protocol + F1 + T1 + T2 + C1 + N1 pass.
- `SAT_STRONG_FACTORIZATION_POSITIVE`: protocol passes; proposed is solve-noninferior to equal-memory controls and paired-bootstrap upper 95% work ratio ≤0.80; T1 does not pass.
- `SAT_NO_FREQUENT_FACTOR_GAIN`: protocol passes but F1 fails.
- `SAT_MIXED_NO_REPLICATION`: protocol passes, F1 passes, but neither tail-risk nor strong-positive family passes.
- `SAT_POOL_NO_GO`: structural pool incomplete.
- `SAT_PROTOCOL_FAIL`: any validity/protocol/hash gate fails.

R1 is secondary and cannot rescue a failed primary verdict.

## Statistical reporting

- exact paired solve tables and McNemar tests;
- paired bootstrap ratio-of-means intervals, 100,000 replicates;
- paired win/tie/loss counts;
- stratified bootstrap for coupling;
- failure taxonomy and penalty sensitivity marked exploratory;
- development and independent results kept separate.

## Claim boundary

Even `SAT_TAIL_RISK_REPLICATION` supports only a symbolic cross-substrate boundary result. It establishes no new distributed-search algorithm, no LLM-agent gain, and no wall-clock speedup.
