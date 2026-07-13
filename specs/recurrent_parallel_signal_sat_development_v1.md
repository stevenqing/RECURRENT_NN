# Recurrent Parallel Signal-Noise SAT Development v1

- Frozen date: 2026-07-12
- Status: frozen before SAT substrate outcomes
- Role: second-substrate development gate for recurrent signal hazard
- Parent graph result: `RPD_SIGNAL_GRAPH_CONFIRMATION_PASS`
- Headline eligible: No

## Substrate

- 17 SAT partitions arranged as trees of exact diameter 2, 4, 8, or 16;
- four Boolean variables per partition: two boundary-state bits and two local auxiliary bits;
- eight fixed local 3-SAT clauses per partition;
- every local boundary-bit pair has at least one satisfying auxiliary extension;
- every partition-tree edge uses two Boolean equality gadgets, each encoded by four 3-literal clauses;
- 264 clauses total: 136 local and 128 cross-partition;
- planted assignment verifies generation and is removed before execution;
- initial non-root boundary states are deterministic and heterogeneous, ensuring correction engagement without outcome-based selection.

## Recurrent engine

Each agent enumerates only locally satisfying assignments. A one-round-delayed parent message contains the parent's two boundary bits. Candidate cost is the number of falsified equality-gadget clauses on the parent edge.

Systems:

- `R_exact` one-hit correction;
- `R_soft2` two-hit correction;
- `R_commit` ignores correction.

Sweep:

- 8 development instances per diameter;
- T=32;
- $\eta_{fp}\in\{0,0.01,0.02,0.05,0.10,0.20\}$;
- 576 rows.

## Gates

### D0 environment and semantics

- exact diameter and fixed clause counts;
- unique IDs/clause hashes;
- every planted assignment valid and removed;
- every local boundary pair extendable;
- at least eight structurally mismatched parent-child initial states per instance;
- deterministic replay, one-round message age, no same-round reads, local and official validity.

### D1 perfect-signal asset

At eta=0 for every diameter:

- exact and soft solve ≥0.95;
- exact over-corrections =0;
- exact solve exceeds commit by ≥0.80;
- exact work < soft work.

### D2 SAT asset/liability crossing

At least three diameter groups have a nonzero-noise crossing where soft2 is better by solve or penalized work.

### D3 recurrent hazard

Pooled exact over-corrections are nondecreasing with eta and exact solve at eta=0.20 is below eta=0.

### D4 two-hit robustness

For eta≥0.05, pooled soft solve ≥ exact solve and soft over-corrections are lower. Soft solve at eta=0.20 is ≥0.90 in at least three diameter groups.

### D5 diameter direction

At T=32, preliminary $\eta^*(16)\le\eta^*(2)$ and exact solve at eta=0.10 for diameter 16 is no greater than diameter 2.

## Verdicts

- D0–D5 pass: `RPD_SIGNAL_SAT_DEV_GO_CONFIRMATION`;
- D0–D4 pass but D5 fails: `RPD_SIGNAL_SAT_DEV_NO_DIAMETER`;
- crossing/robustness fails: `RPD_SIGNAL_SAT_DEV_NO_GO`;
- semantics fails: `RPD_SIGNAL_SAT_DEV_PROTOCOL_FAIL`.

A GO authorizes a new zero-overlap SAT confirmation. It does not itself establish a cross-substrate law or authorize Qwen.
