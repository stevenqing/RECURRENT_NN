# Recurrent Parallel Signal-Noise Graph Confirmation v1

- Frozen date: 2026-07-12
- Status: frozen before new manifest and outcomes
- Prerequisite: `RPD_SIGNAL_PHASE_DIAMETER_CANDIDATE`
- Study role: independent graph confirmation of recurrent signal hazard and diameter boundary
- Headline eligible: No

## Manifest

- new split `signal_graph_confirmation`;
- base seed 720000;
- exact partition diameters 2, 4, 8, 16;
- 50 accepted instances per diameter, 200 total;
- same fixed 117 graph edges: 85 local, 32 cross;
- reference true rollback engagements ≥3;
- zero instance-ID and canonical graph-hash overlap with the 32-instance development pool;
- no signal-system outcomes during selection;
- planted assignments removed before execution.

## Execution

- T=32;
- systems `R_exact`, `R_soft2`, `R_commit`;
- $\eta_{fp}\in\{0,0.01,0.02,0.05,0.10,0.20\}$;
- $\eta_{fn}=0$;
- deterministic signal seed 20260712;
- failure penalty 5,000;
- 3,600 rows.

## Frozen gates

### C0 integrity

- all lock hashes, manifest cardinality, density, diameter, overlap, signal replay, Jacobi semantics, message age, local validity, and official scoring pass.

### C1 perfect-signal recurrence

For every diameter at $\eta=0$:

- `R_exact` solve ≥0.95;
- `R_soft2` solve ≥0.95;
- exact false positives and over-corrections =0;
- exact solve exceeds `R_commit` by ≥0.80.

### C2 diameter-sensitive asset/liability boundary

At T=32:

- first crossing $\eta^*(16)\le0.05$;
- first crossing $\eta^*(2)\ge0.05$;
- $\eta^*(16)\le\eta^*(8)\le\eta^*(2)$;
- at $\eta=0.10$, exact solve at $\delta=16$ is at least 0.20 below exact solve at $\delta=2$.

### C3 two-hit robustness

For every diameter and every $\eta\le0.20$:

- `R_soft2` solve ≥0.90;
- at $\eta\ge0.05$, pooled soft solve ≥ exact solve;
- pooled soft over-corrections < exact over-corrections.

### C4 hazard monotonicity

Pooled `R_exact` mean over-corrections are nondecreasing over the frozen eta grid, and solve at 0.20 is lower than at 0.

### C5 expected-work crossing

- at $\eta=0$, exact mean penalized work < soft2;
- at $\eta=0.10$ and 0.20, soft2 mean penalized work < exact;
- the direction holds separately for $\delta=8$ and 16 at $\eta=0.10$.

## Verdicts

- C0–C5 pass: `RPD_SIGNAL_GRAPH_CONFIRMATION_PASS`;
- C0/C1/C3/C4/C5 pass but C2 fails: `RPD_SIGNAL_GRAPH_NO_DIAMETER_CONFIRMATION`;
- C0 passes but crossing/robustness fails: `RPD_SIGNAL_GRAPH_CONFIRMATION_FAIL`;
- C0 fails: `RPD_SIGNAL_GRAPH_PROTOCOL_FAIL`.

A pass confirms only the graph substrate. Community-SAT confirmation and a real signal anchor remain mandatory before a broad paper claim.
