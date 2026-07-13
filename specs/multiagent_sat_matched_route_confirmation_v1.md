# Matched-Window Community-SAT Confirmation v1

- Frozen date: 2026-07-12
- Timing: after exposed-pool `SAT_MATCHED_ROUTE_DEV_GO_CONFIRMATION`, before generation of the new manifest and before any new-arm outcome
- Study role: independent confirmation of capacity-valid routing as a tail-risk control
- Evidence tier: symbolic mechanism confirmation; no LLM or algorithm-novelty claim
- Development report: [Matched-window route development](../results/multiagent_sat_matched_route_development/DEVELOPMENT.md)

## 1. Research question

Does filtering rollback candidates to the target owner's current bounded-memory window before applying deepest conflict priority:

1. outperform a matched random-valid route;
2. remove the NACK/window-rejection cascade of the frozen deepest policy; and
3. restore solve reliability and failure-penalized expected-work advantage against an equal-total-memory monolith?

## 2. Mechanism

`independent_local_deepest_window_valid_sat` calls the exact frozen `queued_random_valid` engine and changes only the within-filter ranking:

- candidate set: assignments currently valid in the target owner's $R=8$ window;
- random-valid: uniformly sampled with the frozen per-instance RNG;
- matched deepest: maximum fixed-order position in the same candidate set.

The implementation is a sequential shadow wrapper around the hash-locked solver. Concurrent calls are forbidden.

## 3. New untouched manifest

- substrate: planted fixed-density community 3-SAT;
- 48 variables in four communities;
- exactly 192 clauses of size 3;
- high coupling: exactly 77 cross-community clauses;
- capacity stratum: `over_local_fit`, global reference distance $>8$ and local target-owner distance $\leq8$;
- split: `matched_route_confirmation`;
- base seed: 510000;
- ascending candidate indices;
- maximum 20,000 candidates;
- first 200 structurally eligible instances;
- no bounded-arm outcomes during selection;
- planted assignments removed;
- zero instance-ID and clause-hash overlap with all three prior SAT pools: development, independent replication, and route confirmation.

## 4. Frozen resources

- agents $M=4$;
- local register $R=8$;
- total recovery memory $MR=32$;
- activation/failure cap 20,000;
- request channel cap 16;
- route seed 20260712;
- fixed variable order and values 0 then 1;
- no unit propagation;
- no oracle/model fallback;
- official full-clause verification.

## 5. Arms

1. `independent_local_deepest_window_valid_sat` — proposed matched-window policy;
2. `independent_local_random_valid_sat` — same candidate filter, random rank;
3. `independent_local_cbj_sat` — frozen deepest-before-window-rejection policy;
4. `independent_local_no_cross_sat` — coordination ablation;
5. `monolith_MR_sat` — equal-total-memory control.

The proposed/random contrast isolates ranking. Proposed/frozen-deepest isolates capacity-valid filtering. Proposed/monolith tests the actual expected-resource objective.

## 6. Frozen statistics

- paired solve contrasts;
- one-sided exact McNemar tests in the declared direction;
- one-sided 95% Clopper–Pearson upper bound on monolith-only discordance;
- paired failure-penalized ratio-of-means bootstrap with 100,000 replicates;
- failure cost 20,000;
- alpha 0.05;
- no secondary statistic may rescue a failed gate.

## 7. Frozen gates

### C0 — execution integrity

- 200 instances and 1,000 rows;
- all lock hashes, cardinality, deterministic-shadow, protocol, memory-window, request-conservation, and official-verification checks pass.

### C1 — ranking solve effect

Proposed minus random-valid solve $\geq0.10$ and one-sided exact McNemar $p\leq0.05$.

### C2 — ranking expected-work effect

Proposed/random failure-penalized work ratio $\leq0.90$ with paired-bootstrap upper 95% bound $<1.00$.

### C3 — operational safety

Proposed mean NACKs $\leq1.0$, mean window rejections $\leq1.0$, zero out-of-window rollback executions, and matched declared resources.

### C4 — equal-memory solve non-inferiority

For proposed versus `monolith_MR_sat`:

- observed solve difference $\geq-0.05$; and
- one-sided 95% Clopper–Pearson upper bound on monolith-only discordance $\leq0.05$.

### C5 — equal-memory expected-work advantage

Proposed/monolith failure-penalized work ratio $\leq0.80$ with paired-bootstrap upper 95% bound $<1.00$.

### C6 — repair mechanism

Proposed/frozen-deepest failure-penalized work ratio $\leq0.50$ with paired-bootstrap upper 95% bound $<0.75$.

## 8. Verdict family

- all C0–C6 pass: `SAT_MATCHED_ROUTE_STRONG_CONFIRMATION`;
- C0–C3 and C6 pass but C4 or C5 fails: `SAT_MATCHED_ROUTE_CONFIRMATION_ONLY`;
- C0 passes but a route/repair gate fails: `SAT_MATCHED_ROUTE_CONFIRMATION_NO_GO`;
- C0 fails: `SAT_MATCHED_ROUTE_PROTOCOL_FAIL`.

## 9. Contribution boundary

A strong confirmation would support:

> In bounded owner-local search, conflict priority must be applied only after recovery-capacity validity filtering; otherwise NACK cascades create catastrophic tails. Capacity-valid routing can recover equal-memory reliability and expected-work gains in the frozen community-SAT regime.

It would not establish:

- algorithm novelty relative to CSP/DisCSP/backtracking literature;
- an LLM or Qwen contribution;
- a general law beyond this SAT regime;
- measured wall-clock or hardware efficiency.

Qwen remains unauthorized by this contract. A positive result first changes the symbolic paper contribution and triggers a separate decision about whether an LLM experiment adds scientific value.
