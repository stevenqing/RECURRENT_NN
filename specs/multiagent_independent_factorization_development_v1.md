# Independent Factorization Mechanism — Development Contract v1

- Frozen date: 2026-07-11
- Stage: symbolic mechanism development; not confirmatory
- Parent memo: [Where Is the Multi-Agent Free Lunch?](multiagent_free_lunch_research_memo_v1.md)
- Source pool: the already-observed 64-instance core 2×2 preflight manifest
- Headline eligibility: **No**

## 1. Research contribution contract

The following ingredients are established classical ideas and are **not** standalone contributions:

- graph partitioning;
- distributed CSP search;
- asynchronous backtracking;
- conflict-directed backjumping;
- calling an LLM as a generic heuristic.

A research contribution becomes eligible only if the experiment isolates the following joint mechanism:

> Under equal total recovery memory, independent bounded local search avoids rollback of dependency-unrelated work; when cross-partition recovery events are sparse and route-sensitive, a frozen LLM can later be tested only at those events rather than at every branch.

The symbolic development stage tests the first half and whether the second half is identifiable. It does not test an LLM.

## 2. Competing explanations that must be removed

1. **More-memory explanation:** compare against `monolith_MR`, not only `monolith_R`.
2. **Sharding-only explanation:** compare against the current `centralized_sharded_MR` global-trail solver.
3. **Changed-order explanation:** add a centralized controller using exactly the same factorized local loops and deepest route.
4. **Communication-is-unnecessary explanation:** add an independent arm with cross-agent recovery disabled.
5. **Any-valid-route explanation:** add uniform random valid routing.
6. **Parallel-hardware explanation:** report aggregate work separately from critical-path rounds.

## 3. Frozen data and resources

- Manifest: `results/multiagent_core_2x2_preflight/instance_manifest.json`
- Cells: `under_low`, `under_high`, `over_low`, `over_high`
- Instances: 16 per cell, 64 total
- Agents: $M=4$
- Per-agent window: $R=8$
- Equal-total window: $MR=32$
- Aggregate-work cap: 5000
- No GPU and no LLM calls

This pool has already been observed. Every statistic from this stage is development evidence only. A successful mechanism must later be frozen and rerun on a newly generated independent manifest.

## 4. Frozen arms

| Arm | Search state | Recovery execution | Purpose |
|---|---|---|---|
| `monolith_R` | one global trail, window $R$ | centralized | single-window capacity control |
| `monolith_MR` | one global trail, window $MR$ | centralized | equal-total-memory control |
| `global_trail_team_cbj` | sharded windows, one global trail | global suffix rollback | current team bridge |
| `centralized_sharded_MR` | sharded windows, one global trail | global suffix rollback | sharding-only control |
| `factorized_central_deepest` | independent local trails | immediate centrally applied local rollback | changed-order/factorization control |
| `independent_local_deepest` | independent local trails | queued request handled by target agent | proposed symbolic architecture |
| `independent_local_random_valid` | independent local trails | queued uniform-valid request | route-identifiability control |
| `independent_local_no_cross` | independent local trails | no cross-agent recovery | coordination-necessity ablation |

`global_trail_team_cbj` and `centralized_sharded_MR` are expected to remain rowwise outcome-equivalent. `factorized_central_deepest` and `independent_local_deepest` use the same local ordering and target rule; their difference estimates the asynchronous message-handling tax.

## 5. Independent-local semantics

Each agent owns:

- a local vertex order equal to the global order restricted to its partition;
- its own trail and next-choice state;
- one recoverable suffix window of size $R$;
- a queue of incoming rollback requests.

The environment may hold a full assignment and audit trace for scoring, but an agent can inspect only:

- its own assignments;
- current boundary commitments from neighboring agents;
- explicit recovery messages.

A cross-agent dead end does not directly mutate another agent. The source queues a request and waits; the target processes the request on its own activation. Only the target's local suffix is retracted. Unrelated agents retain their assignments.

## 6. Resource accounting

Report all of:

- `decision_work`: branch/dead-end evaluations;
- `coordination_work`: queued recovery requests processed;
- `aggregate_work = decision_work + coordination_work`;
- `critical_path_rounds`: synchronous round-robin supersteps;
- `retractions`;
- `preserved_unrelated_assignments`: assignments that a global suffix rollback would have removed but local rollback retained;
- recovery requests, acknowledgements, boundary commit/retract messages, and communication tokens;
- peak recoverable entries per agent and in total.

Unsolved runs receive the frozen aggregate-work cap for penalized-work comparisons.

## 7. Development gates

### D0 — Correctness and reproducibility

All solved rows pass full graph validation; invariant violations, out-of-window targets, oracle fallback, and duplicate assignments are zero. Repeated runs are byte-deterministic after excluding output paths.

### D1 — Mechanism engagement

At least 25% of episodes containing a recovery preserve one or more unrelated assignments, and independent traces are not outcome/cost-identical to the global-trail control.

### D2 — Equal-resource solve retention

In `over_low`:

$$
S_{independent\_deepest} \ge S_{monolith\_MR}-0.10.
$$

The same arm may not lose more than 0.10 solve rate to `factorized_central_deepest` overall.

### D3 — Aggregate-work factorization

On paired `over_low` instances using cap-penalized work:

$$
\frac{\overline W_{independent\_deepest}}
{\overline W_{monolith\_MR}}\le0.85.
$$

This 15% threshold is the minimum effect that permits a structural-factorization claim to advance. Critical-path improvement alone does not pass D3.

### D4 — Bounded decentralization tax

On jointly solved rows:

$$
\frac{\overline W_{independent\_deepest}}
{\overline W_{factorized\_central\_deepest}}\le1.10,
$$

or the independent arm must improve solve rate enough to compensate. Otherwise asynchronous coordination overhead dominates the local factorization.

### D5 — Route identifiability

Deepest and random-valid routing must differ by at least one of:

- 0.10 solve rate in an over-capacity cell; or
- 15% paired aggregate work on jointly solved over-capacity rows.

The direction is not assumed. If route policies are indistinguishable, there is no substrate-level basis for an LLM routing contribution.

### D6 — Coordination necessity

Disabling cross-agent recovery must reduce solve by at least 0.20 in one over-capacity cell or produce a clearly separated recovery-failure mode.

### D7 — Event sparsity

For `independent_local_deepest`:

$$
\frac{\text{cross-agent route requests}}
{\text{decision work}}\le0.20
$$

in both over-capacity cells. Otherwise “event-triggered” does not provide a sparse-call regime.

## 8. Decision rule

- **Factorization GO:** D0–D4 all pass.
- **Sparse-routing GO:** D0, D2, D5–D7 all pass.
- **Full research GO:** both gates pass.
- If D3 fails, retain only horizontal capacity scaling.
- If D5 fails, remove the LLM-routing novelty claim.
- If D6 fails, the substrate does not require multi-agent coordination.
- If D7 fails, do not claim sparse specialization.

Thresholds are development routing criteria, not p-values.

## 9. Confirmatory stage reserved only after GO

A GO permits implementation freeze and a new, independent 50-instance-per-cell manifest. The confirmatory stage must preregister no more than four primary contrasts and use paired solve/work analyses with multiplicity correction. It must not reuse this development pool.

## 10. Safe and forbidden language

Safe before confirmation:

- “The independent-loop mechanism passed/failed a development gate on an already-observed symbolic pool.”
- “The result motivates/does not motivate an independent confirmatory manifest.”

Forbidden:

- “Multi-agent systems beat equal-resource monoliths.”
- “Qwen routing is beneficial.”
- “The architecture is novel” without a separate literature audit.
- “Parallel speedup” from simulated rounds alone.
