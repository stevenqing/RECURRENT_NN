# Recurrent Parallel Signal-Noise Phase Sweep v1

- Frozen date: 2026-07-12
- Status: frozen before recurrent-noise outcomes
- Prerequisites:
  - `V7_PREFLIGHT_PHASE_IDENTIFIABLE`
  - `RPD_MESSAGE_RECURRENCE_ONLY`
  - `RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE`
- Source pool: 32 exposed exact-diameter graph instances
- Headline eligible: No

## 1. Correction signal

At every non-root agent update, the exact parent-boundary message defines a local candidate cost. Let:

$$
correction^*(s,m)=\mathbb 1[cost(current,m)>\min_y cost(y,m)].
$$

This is the ground-truth correction label. The agent observes a detector signal with false-positive rate $\eta_{fp}$ and frozen $\eta_{fn}=0$.

A false positive means the current candidate is already optimal under the received message, but the detector reports that rollback/correction is required.

## 2. Systems

1. `R_exact`: one positive signal triggers correction immediately.
   - true positive: choose the exact minimum-cost candidate;
   - false positive: move to the next deterministic non-current candidate, destroying correct local progress.
2. `R_soft2`: require two independent positives on the same unchanged state.
3. `R_commit`: ignore correction signals and retain the current candidate.

All systems use the same 17-agent Jacobi engine, full one-round-delayed messages, candidate enumeration, root state, branch order, and official scorer.

## 3. Sweep

$$
\eta_{fp}\in\{0,0.01,0.02,0.05,0.10,0.20\},
$$

$$
\delta\in\{2,4,8,16\},
$$

$$
T\in\{2,4,8,16,32\}.
$$

All 32 development instances are run under every system/noise/round cell: 2,880 rows.

## 4. Accounting

Report:

- solve and final cross conflicts;
- recurrent rounds and 17-agent updates;
- detector queries;
- true corrections;
- over-corrections;
- false positives/negatives;
- correct state changes destroyed;
- idealized and sequential critical paths;
- failure-penalized work.

Work is:

$$
W=\text{agent updates}+\text{detector queries}+\text{candidate corrections}.
$$

Unsolved rows receive failure penalty 5,000.

## 5. Frozen gates

### N0 — perfect-signal recurrence

At $\eta=0$, `R_exact` must reproduce the full-message P0 recurrent solve matrix and have zero over-corrections/false positives. Register/message semantics and official verification pass.

### N1 — asset/liability identifiability

Across cells where `R_exact` solves at $\eta=0$:

- at least one low-noise cell favors `R_exact` over `R_soft2` by lower penalized work at noninferior solve;
- at least one higher-noise cell favors `R_soft2` by solve or penalized work;
- at least three diameter/round groups exhibit a crossing.

### N2 — recurrent hazard accumulation

For `R_exact`:

- mean over-corrections are nondecreasing with $\eta$ in pooled summaries;
- solve at $\eta=0.20$ is no greater than solve at $\eta=0$;
- detector exposure at $\eta=0$ is larger for $\delta=16$ than $\delta=2$ at T=32, reflecting longer recurrent trajectories.

### N3 — diameter-sensitive boundary

At T=32, the preliminary first-crossing noise must satisfy:

$$
\eta^*(16)\le\eta^*(2).
$$

Additionally, at one common nonzero $\eta$, `R_exact` solve for $\delta=16$ must be no greater than for $\delta=2$.

### N4 — two-hit robustness

At $\eta\ge0.05$, pooled `R_soft2`:

- solve is at least `R_exact` solve;
- mean over-corrections are lower;
- added detector queries are fully reported.

### N5 — correction necessity

At T=32 and $\eta=0$, `R_exact` solve exceeds `R_commit` by at least 0.15 on pooled $\delta\ge4$ instances.

## 6. Verdicts

- N0–N5 pass: `RPD_SIGNAL_PHASE_DIAMETER_CANDIDATE`;
- N0/N1/N2/N4/N5 pass but N3 fails: `RPD_SIGNAL_PHASE_NO_DIAMETER_SHIFT`;
- N0 passes but N1 fails: `RPD_SIGNAL_PHASE_NO_CROSSING`;
- N0 fails: `RPD_SIGNAL_PHASE_HARNESS_FAIL`.

No verdict authorizes Qwen, GPU timing, or a paper claim. A positive development result authorizes new zero-overlap graph and SAT confirmation pools with frozen thresholds.
