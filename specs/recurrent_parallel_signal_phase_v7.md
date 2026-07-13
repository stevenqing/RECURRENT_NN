# SPEC v7-RPD: Recurrent Parallel Reasoning under Noisy Rollback Signals

> **CPU preflight update (2026-07-12):** The 32-instance, 576-row development harness passed G-env, G0, G1, and G2. Exact rollback solved 1.000 at $\eta=0$; two-hit confirmation dominated once false positives were introduced, while `R_exact` collapsed by $\eta=0.20$. The preliminary crossing is only bounded to $(0,0.05]$ and does not shift with diameter because recurrent parallel propagation is not implemented yet. See [preflight closeout](../results/recurrent_signal_phase_v7_preflight/CLOSEOUT.md).

> **RPD P0 update (2026-07-12):** Recurrent parallel propagation is now implemented with strict one-round message delay. Communication depth and message correctness pass; persistent local state does not. The next authorized stage is a fixed-$B=MT$ width/depth sweep, after which signal noise can be injected into recurrent messages to estimate $\eta^*(\delta,T)$. See [RPD P0 closeout](../results/recurrent_parallel_engine_p0/CLOSEOUT.md).

> **Fixed-budget update (2026-07-12):** The authorized $B=MT$ sweep identifies an interior reliable width at the smaller budget and recovery of the maximally wide endpoint when temporal budget doubles. This supplies the spatial–temporal backbone required for a future $\eta^*(\delta,T)$ sweep. Persistent latent state and real wall-clock remain unproven. See [fixed-budget closeout](../results/recurrent_parallel_fixed_budget/CLOSEOUT.md).

> **Compressed-message update (2026-07-12):** A one-fact-per-round bottleneck preserves recurrent solve and makes persistent overall candidate state necessary, but does not identify explicit two-fact message-cache memory. The next stage should now inject the frozen rollback-signal noise process into recurrent correction events and measure $\eta^*(\delta,T)$; do not start learned-state or Qwen work. See [compressed-state closeout](../results/recurrent_parallel_compressed_state/CLOSEOUT.md).

> **Independent graph confirmation (2026-07-12):** A new zero-overlap 200-instance graph pool passes all six recurrent signal gates. At T=32 the confirmed first crossing moves from $\eta^*=0.10$ at $\delta=2$ to 0.05 at $\delta=4$ and 0.02 at $\delta\in\{8,16\}$. Two-hit correction remains robust while one-hit solve collapses with diameter/noise. Verdict: `RPD_SIGNAL_GRAPH_CONFIRMATION_PASS`. SAT replication and a real signal anchor remain mandatory. See [graph closeout](../results/recurrent_parallel_signal_graph_confirmation/CLOSEOUT.md).

> **SAT development boundary (2026-07-12):** Long-diameter 3-SAT reproduces perfect-signal benefit, nonzero-noise crossing, and monotone one-hit hazard, but fails frozen two-hit robustness and finite diameter-boundary gates. At eta=.20 soft2 solve falls to 0.875 for diameter 8 and 0.125 for diameter 16, while diameter 2 has no crossing through .20. Verdict: `RPD_SIGNAL_SAT_DEV_NO_GO`; no SAT confirmation or cross-substrate law is authorized. The refined hypothesis is exposure-scaled confirmation depth $k(\eta,L)$, not universally fixed two-hit. See [SAT closeout](../results/recurrent_parallel_signal_sat_development/CLOSEOUT.md).

> **Adaptive-guard outcome (2026-07-12):** The formula $k(\eta,\delta)=\min\{k:(1-\eta^k)^{16(\delta+1)}\ge.95\}$ was frozen, passed SAT development, and independently confirmed on 200 new SAT instances: solve 1.000 in every cell and charged work gains in the failed diameter-8/16 high-noise cells. However, applying the same formula to the exposed graph pool fails a strict per-cell hazard-dominance gate despite robust solve and diameter-16 value. Thus graph fixed-two-hit and SAT adaptive-k are confirmed as substrate-specific guards; one universal guard policy is not. See [SAT adaptive closeout](../results/recurrent_parallel_adaptive_guard_sat_confirmation/CLOSEOUT.md) and [graph adaptive boundary](../results/recurrent_parallel_adaptive_guard_graph/CLOSEOUT.md).

> **Cost-sensitive cross-substrate confirmation (2026-07-12):** A common analytic objective—verification-query cost plus 5,000 times exposure-dependent failure probability—was calibrated only from eta=0 exposure counts and frozen before two new 200-instance pools. The 9,600-row joint graph/SAT confirmation passes all seven gates after an explicit replay-metadata erratum: the frozen helper omitted the runner-added `substrate` label, while raw rows and all substantive statistics were unchanged. Authoritative verdict: `RPD_COST_SENSITIVE_CROSS_SUBSTRATE_CONFIRMATION_PASS`. See [joint closeout](../results/recurrent_parallel_cost_sensitive_confirmation/CLOSEOUT.md).

## The Asset↔Liability Phase Diagram in Space and Time

- Frozen date: 2026-07-12
- Status: proposed development contract; no outcome observed under this contract
- Parent directions:
  - [Recurrent Parallel Agent Reasoning](multiagent_recurrent_parallel_reasoning_v1.md)
  - user-provided SPEC v7 rollback-signal phase proposal from the current research session
- Current evidence foundation: [capacity-valid tail control](../results/multiagent_capacity_valid_route_tail_control/SUMMARY.md)

## 1. Headline question

The exact reversible mechanism is not intrinsically beneficial. Its value depends on:

1. rollback-signal quality $\eta$;
2. dependency/communication diameter $\delta$;
3. recurrent communication depth $T$;
4. parallel agent width $M$.

The target law is:

> Exact rollback is an asset only when recurrent agents receive sufficiently reliable correction signals before the cost of undoing distributed correct work dominates. Higher dependency diameter requires more recurrent rounds and can lower the tolerable false-positive rate.

## 2. Recurrent parallel system

There are $M$ weight-tied local agents. Round $t$ uses an immutable snapshot:

$$
(h_i^{t+1},r_i^{t+1},y_i^t,m_i^t)
=F_\theta(x_i,h_i^t,r_i^t,\bar m_i^t,D_\eta(s^t)).
$$

All agents update in parallel. Proposals are verified and committed at a round barrier. Messages become visible only in round $t+1$.

Fixed total update budget:

$$
B=MT.
$$

No same-round cross-agent state read is allowed in the eventual RPD confirmation.

## 3. Environment requirements

The substrate must satisfy:

1. `dead_star(partial)` is computed independently from the signal shown to agents;
2. exact ground-truth scoring is separate from detector output;
3. at $\eta=0$, at least $K=3$ true rollback engagements occur per accepted instance in development;
4. difficulty, partition diameter, and signal noise are independently manipulated;
5. fixed graph/clause density within each substrate;
6. exact partition-graph diameter is audited, not inferred from separator count;
7. false positives destroy or delay correct committed work and are fully charged;
8. every solved output passes official verification.

## 4. Long-diameter graph substrate

Development substrate: planted 3-colorable graph with:

- $M=17$ partitions;
- four vertices per partition;
- a fixed local gadget in every partition;
- exactly 16 partition-tree edges for every diameter;
- exactly two cross-variable edges per partition-tree edge;
- fixed total graph edges;
- planted coloring used only for generation/verification, never by a system.

Partition trees have exact diameter:

$$
\delta\in\{2,4,8,16\}.
$$

Construction: a path of length $\delta$ plus all remaining partition nodes attached to the path center. Since every partition graph is a tree on 17 nodes, edge count remains 16 while diameter changes.

Main study must additionally replicate on long-diameter community SAT before a cross-task claim.

## 5. Ground truth and signal

For partial assignment $s$:

$$
dead^*(s)=\mathbb 1[\text{no valid completion exists}].
$$

`dead_star` uses an exact memoized completion solver. It is never exposed directly except in the $\eta=0$ oracle control and official analysis.

Primary detector:

$$
P(D_\eta=1\mid dead^*=0)=\eta_{fp},
$$

$$
P(D_\eta=0\mid dead^*=1)=\eta_{fn}.
$$

Primary sweep freezes $\eta_{fn}=0$ and target noise $\eta_{tgt}=0$.

Noise is a deterministic hash function of:

- instance ID;
- canonical partial assignment;
- query index;
- noise seed.

Thus the same state/query receives the same coupled signal across systems; signal randomness is independent of the truth computation.

## 6. Systems

### `R_exact`

Immediately trusts one positive detector response and performs exact reversible rollback.

### `R_commit`

Ignores detector positives. It commits forward and uses a full irreversible restart after hard local exhaustion. It never performs exact state pop. This is the operational form of the proposed `R_none` control.

### `R_soft2`

Requires two independent positive detector queries on the same unchanged state before exact rollback. No threshold is tuned from outcomes. At primary $\eta_{fn}=0$, true dead states are confirmed; live-state false-positive probability is approximately $\eta_{fp}^2$ at the cost of one verification round.

### Optional `R_verify`

Pays frozen verification cost $v$ to query exact truth after a positive detector signal. It is a cost-quality upper bound, never a primary proposed method.

All systems use the same branch order, value order, recurrent round budget, register representation, and official scorer.

## 7. Primary phase sweep

Signal noise:

$$
\eta_{fp}\in\{0,0.05,0.10,0.20,0.35,0.50\}.
$$

Diameter:

$$
\delta\in\{2,4,8,16\}.
$$

Systems: `R_exact`, `R_commit`, `R_soft2`.

Main study target: at least 50 independent instances per $(\delta,\eta)$ cell. Development preflight may use smaller fixed samples and is never headline eligible.

Primary outcomes:

- solve rate at matched budget;
- failure-penalized aggregate work;
- actual recurrent rounds;
- over-rollbacks;
- correct rollbacks;
- correct committed work destroyed;
- restarts;
- message/verification cost.

## 8. Recurrent spatial–temporal extension

After the environment and noise gate passes, sweep fixed $B=MT$:

$$
B\in\{32,64,128\},
$$

$$
(M,T)\in\{(1,B),(2,B/2),(4,B/4),(8,B/8),(16,B/16)\}.
$$

The main RPD prediction is:

$$
T\gtrsim\delta
$$

for reliable cross-partition correction propagation. At fixed $B$, wider teams eventually become recurrence-starved.

The central artifact is then a family of boundaries:

$$
\eta^*(\delta,T),
$$

not only $\eta^*(\delta)$.

## 9. Frozen predictions

1. At $\eta_{fp}=0$, `R_exact` is solve-noninferior and no worse in expected work than `R_commit`; rollback engagement gate passes.
2. As $\eta_{fp}$ increases, `R_exact` over-rollback and wasted correct work increase monotonically in expectation.
3. `R_soft2` occupies an intermediate/high-noise Pareto region.
4. A liability boundary exists if `R_commit` or `R_soft2` overtakes `R_exact` in failure-penalized work or solve.
5. Increasing $\delta$ weakly lowers $\eta^*$ once $T$ is held fixed near the communication-depth limit.
6. Increasing $T$ at fixed $M$ can shift $\eta^*$ upward by allowing recurrent correction/confirmation.
7. At fixed $B=MT$, an interior $M^*$ is expected when local capacity and communication depth both bind.

## 9.1 Recurrent hazard accumulation law

Let $L(M,T,\delta)$ be the number of live-state detector exposures for which a false positive destroys indispensable correct progress. For `R_exact`, the probability of avoiding every harmful false positive is approximately:

$$
P_{survive}^{exact}=(1-\eta_{fp})^{L(M,T,\delta)}.
$$

For a frozen $k$-hit confirmation policy with independent repeated queries:

$$
P_{survive}^{soft-k}=(1-\eta_{fp}^{k})^{L(M,T,\delta)}.
$$

For required survival level $p_0$, the corresponding hazard boundary is:

$$
\eta^*_{exact}=1-p_0^{1/L},
$$

$$
\eta^*_{soft-k}=\left(1-p_0^{1/L}\right)^{1/k}.
$$

This creates a non-monotone role for recurrence:

- too few rounds: messages cannot traverse dependency diameter;
- more rounds: communication and correction improve;
- too many noisy correction opportunities: cumulative over-rollback hazard grows.

Therefore the predicted optimum is:

$$
T^*(\eta,\delta)
=\arg\min_T
\left[
C_{underprop}(T,\delta)
C_{signal}(\eta,L(M,T,\delta))
C_{sync}(T)
\right].
$$

The new headline object is a three-dimensional boundary $\eta^*(\delta,T)$ and the induced optimal recurrent depth $T^*(\eta,\delta)$.

## 10. Gates

### G-env — environment

- exact partition diameter for every instance;
- fixed edge count and cross-edge count;
- planted solution valid and unavailable to systems;
- exact completion oracle deterministic;
- at least three true rollback engagements per accepted development instance;
- difficulty summaries overlap across $\delta$ rather than separating trivially.

### G0 — perfect-signal sanity

At $\eta=0$:

- `R_exact` solve ≥ `R_commit`;
- correct rollback count > 0;
- over-rollback count = 0;
- exact register push→pop residual within tolerance;
- official scoring passes.

Failure blocks every noise sweep.

### G1 — signal calibration

For sufficiently many live/dead states:

- realized false-positive rate is within a frozen binomial tolerance of $\eta_{fp}$;
- realized false-negative rate is consistent with frozen $\eta_{fn}$;
- deterministic replay is exact;
- signal samples are independent of branch outcome generation code.

### G2 — asset/liability identifiability

At least one low-noise cell favors `R_exact`, and at least one higher-noise cell favors `R_soft2` or `R_commit`, using solve first and penalized work second.

If no crossing exists, report rollback-noise robustness rather than forcing a phase-transition claim.

### G3 — recurrence necessity

On dependency depth $>1$:

- recurrent state beats state-reset at matched $B$;
- correct messages beat shuffled messages;
- one-shot $T=1$ cannot match the best recurrent point with equal calls.

### G4 — independent confirmation

New zero-overlap graph and SAT pools; ≥50/cell; frozen thresholds and source hashes; paired tests with multiplicity control.

### G5 — real anchor

Only after G0–G4: measure frozen Qwen/PRM dead-end judge $\eta_{fp},\eta_{fn}$ on the same states and place it on the synthetic phase diagram.

## 11. Controls

- perfect detector;
- detector-only noise with exact target;
- target-only noise at fixed detector;
- state-reset recurrence;
- shuffled messages;
- no-message parallel agents;
- sequential sharded recurrence;
- single recurrent monolith;
- one-shot parallel ensemble;
- exact reversible register versus matched explicit stack audit;
- equal total calls, state, memory, and failure penalty.

## 12. Honesty boundaries

- G-env/G0 preflight does not establish a phase transition.
- A synthetic $\eta^*$ without a real anchor is a symbolic systems result only.
- A real anchor in the asset region falsifies the claim that false-positive rollback explains the prior Qwen wall.
- Diameter effects cannot be claimed if difficulty or density differs by $\delta$.
- Recurrent parallelism cannot be claimed from idealized rounds alone; actual two-GPU timing is required.
- No LLM claim before symbolic recurrence and signal gates pass.

## 13. Run order

1. Build/audit exact-diameter fixed-density graph substrate and detector calibration (`G-env`).
2. Run $\eta=0$ exact/commit/soft sanity (`G0`).
3. Run development $(\eta,\delta)$ sweep; freeze whether a crossing is identifiable.
4. Add fixed-$B=MT$ recurrent controls (`G3`).
5. Generate new graph and SAT confirmation pools (`G4`).
6. Use GPUs 2–3 for actual recurrent parallel timing only when clean cards are available.
7. Measure real Qwen signal anchor last (`G5`).
