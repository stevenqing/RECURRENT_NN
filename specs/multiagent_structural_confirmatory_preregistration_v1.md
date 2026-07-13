# Multi-Agent Structural Factorization Confirmatory Preregistration v1

- Frozen date: 2026-07-11
- Stage: independent symbolic confirmation before any new Qwen/GPU study
- Development result: [Structural free-lunch gate](../results/multiagent_structural_free_lunch/RESULTS.md)
- Headline eligibility: **false**

## 1. Scientific contribution under test

The confirmatory target is not “more agents provide more aggregate memory.” It is the narrower structural claim:

> Under equal total recovery memory, owner-local factorized search with dependency-scoped rollback can preserve solve rate while reducing aggregate rollback work in the global-over-capacity/local-fit, low-coupling regime; the gain is consumed by separator coupling.

The classical ingredients—distributed CSP, graph partitioning, asynchronous backtracking, and conflict-directed backjumping—are not claimed novel. A contribution is eligible only as a **resource-controlled phase law and mechanism isolation**, subject to the later literature audit and a second substrate.

## 2. Frozen successful mechanism

The proposed arm directly imports `_run_independent()` from `experiments/multiagent_independent_local.py`.

- Frozen implementation SHA-256: `946782f3abff7026a98593fb3f3374ff020159f21303ccc442157ac6354244ba`
- Development contract SHA-256: `c51fa8fdd2ccdab7489870a80f12e8ac19824db9543337cb6ae122c55b1ccc3e`
- Development manifest SHA-256: `151e8b2ed9976827bc0e6b1c7559c0cdeb29654527128ae20be311f23dd725ea`

The confirmatory runner must refuse to execute if the successful implementation hash changes.

A parameterized shadow engine may be used for controls only. Before a new manifest is generated, its `queued_deepest` mode must match the frozen proposed arm rowwise on all 64 development instances for:

- solve and status;
- activations and parallel rounds;
- branch attempts, recoveries, and retractions;
- requests, executions, acknowledgements, and NACKs;
- communication and boundary messages;
- aggregate work;
- all ownership, priority, window, channel, and lifecycle fields.

Failure of exact equivalence blocks confirmation.

## 3. Independent manifest

The confirmatory pool is generated without reading any proposed/control-arm outcome.

- Generator: existing fixed-density structural generator and unlimited-reference strata only
- New base seed: `106000`
- Cells: `under_low`, `under_high`, `over_low`, `over_high`
- Instances: `50` per cell, `200` total
- Agents: `M=4`
- Per-agent recovery window: `R=8`
- Equal-total recovery window: `MR=32`
- Vertices: `48`
- Colors: `4`
- Edges: exactly `96`
- Low/high generator coupling: `b=2` / `b=8`
- Under/over target reference depth: `4` / `12`
- Candidate batch size: `96`
- Maximum batches per cell: `30`
- Reference node cap: `20,000`

Selection may use only:

1. reference solution validity;
2. exact target conflict depth;
3. fixed 96-edge normalization;
4. `global_recovery_distance <= R` for under cells;
5. `global_recovery_distance > R` and `local_recovery_distance <= R` for over-local-fit cells;
6. first accepted rows in deterministic generator order.

No smoke run may use a confirmatory instance. All implementation smoke and equivalence checks use the old 64-instance development manifest.

## 4. Frozen arms

1. `independent_local_cbj_v1_exact`: direct call to the hash-locked successful mechanism;
2. `factorized_central_cbj`: identical local orders, priorities, conflict propagation, windows, and owner-local rollback, but the target-owner callback executes immediately and returns an immediate acknowledgement;
3. `independent_local_random_valid`: identical queued owner-local protocol, with a deterministic uniform draw among currently valid earlier conflict targets;
4. `independent_local_no_cross`: identical protocol, but cross-agent recovery is disabled and fails closed;
5. `global_trail_cbj`: existing global-trail team control;
6. `centralized_sharded_MR`: existing equal-total-memory sharded global-trail control;
7. `monolith_MR`: existing equal-total-memory monolith;
8. `monolith_R`: per-agent-memory context arm.

`factorized_central_cbj` counts a request and acknowledgement exactly as the independent arm, even though delivery is immediate. This isolates scheduling/decentralization tax rather than granting free communication.

## 5. Frozen resources

- Activation cap: `20,000` per episode
- Pending request cap: `16`
- Random-valid route seed: `20260711`
- Work for existing controls:

$$
W_{existing}=steps+retractions+cross\_block\_messages.
$$

- Work for factorized arms:

$$
W_{factorized}=branch\_attempts+retractions+requests+acknowledgements.
$$

- Failure-penalized work:

$$
W^*=\begin{cases}
W,&\text{solved},\\
\max(W,20{,}000),&\text{unsolved}.
\end{cases}
$$

Aggregate work and ideal parallel rounds are always reported separately. Parallel rounds are not wall-clock speedup.

## 6. Mandatory protocol gates

Every factorized-arm row must pass:

1. owner-only assignment and removal;
2. zero direct cross-agent mutation;
3. acyclic earlier-priority requests;
4. version-matched or explicitly stale-idempotent requests;
5. request → target-owner execution/NACK → acknowledgement conservation;
6. zero executed rollback outside `R=8`;
7. recoverable occupancy no larger than `R` per agent;
8. pending channel no larger than 16;
9. no global trail in factorized arms;
10. no oracle/model fallback;
11. official full-edge solution verification;
12. deterministic replay on the old development manifest.

Any violation yields `CONFIRMATORY_PROTOCOL_FAIL` regardless of outcomes.

## 7. Four primary confirmatory gates

All effect estimates are paired where arms share an instance. Bootstrap resampling uses 100,000 paired replicates and fixed seeds recorded in the analysis artifact.

### C1 — Equal-total-memory solve non-inferiority

In `over_low`, compare `independent_local_cbj_v1_exact` with both `monolith_MR` and `centralized_sharded_MR`.

Required for each control:

- observed paired solve-rate difference ≥ `-0.10`; and
- the conservative one-sided 95% Clopper–Pearson upper bound on the control-only discordance rate ≤ `0.10`.

This is an intersection-union gate; both controls must pass.

### C2 — Aggregate-work advantage

In `over_low`, using failure-penalized work:

- ratio of means versus `monolith_MR` ≤ `0.80`;
- ratio of means versus `centralized_sharded_MR` ≤ `0.80`;
- paired bootstrap 95% upper confidence bound for each ratio ≤ `0.80`.

Both equal-memory controls must pass.

### C3 — Same-order factorization and bounded decentralization tax

Two conjunctive checks in `over_low`:

1. `factorized_central_cbj` is solve-noninferior to `monolith_MR` by the C1 rule and has penalized-work ratio ≤ `0.80` with bootstrap upper bound ≤ `0.80`;
2. `independent_local_cbj_v1_exact` is no more than `0.10` below `factorized_central_cbj` in solve and has penalized-work ratio ≤ `1.15`.

This separates the factorization/ordering benefit from request scheduling overhead.

### C4 — Coupling boundary

For `independent_local_cbj_v1_exact`:

- mean failure-penalized work in `over_high` divided by `over_low` is at least `1.20`; and
- high coupling does not improve solve rate over low coupling.

Because cells use independent instances, uncertainty is estimated by a stratified two-sample bootstrap. Cap-censored and solved-only work are both reported; the frozen decision uses penalized all-episode work.

## 8. Secondary mechanism gates

These do not rescue a failed primary family.

### S1 — Route identifiability

In at least one over-capacity cell, deepest-CBJ and random-valid differ by at least:

- `0.10` solve rate; or
- `20%` penalized work at solve non-inferiority within `0.10`.

The direction is not assumed.

### S2 — Coordination necessity

In at least one over-capacity cell, deepest-CBJ exceeds no-cross solve by at least `0.20`, or no-cross produces `NO_CROSS_RECOVERY` on at least 25% of episodes.

### S3 — Unrelated-work preservation

Among proposed-arm episodes with at least one rollback, at least 25% preserve one or more current assignments that a global timestamp-suffix rollback would have removed.

## 9. Statistical reporting

Report:

- paired solve differences and exact McNemar tables;
- conservative control-only discordance bounds for non-inferiority;
- paired ratio-of-means bootstrap intervals for work;
- paired win/tie/loss counts and one-sided sign tests;
- stratified bootstrap interval for the coupling ratio;
- Holm correction over four directional supporting tests, while C1–C4 remain the frozen decision criteria;
- all failure statuses and cap censoring.

At `n=50`, zero control-only losses give a one-sided 95% discordance upper bound below 0.10. The sample size is also more than three times the 16-pair development pool and is fixed before any new outcome is read.

## 10. Verdicts

- `SYMBOLIC_STRUCTURAL_CONFIRMATION_PASS`: protocol, C1–C4, and S1–S3 pass.
- `FACTORIZATION_CONFIRMED_ROUTING_UNRESOLVED`: protocol and C1–C4 pass, but one or more secondary mechanism gates fail.
- `STRUCTURAL_CONFIRMATION_FAIL`: any C1–C4 gate fails.
- `CONFIRMATORY_PROTOCOL_FAIL`: any hash/equivalence/input/protocol gate fails.

Even `SYMBOLIC_STRUCTURAL_CONFIRMATION_PASS` establishes no general novelty or LLM claim. It authorizes a second substrate and sparse-Qwen routing study only after a literature audit.
