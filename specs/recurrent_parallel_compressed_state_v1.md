# RPD Compressed-Message State Persistence Gate v1

- Frozen date: 2026-07-12
- Status: frozen before compressed-message outcomes
- Prerequisites:
  - `RPD_MESSAGE_RECURRENCE_ONLY`
  - `RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE`
- Source pool: 32 exposed exact-diameter development instances
- Headline eligible: No

## 1. Research question

The P0 full-message environment did not require persistent local state. Does fixed-size recurrent state become necessary when each round communicates only a strict fragment of the boundary assignment?

## 2. Frozen communication bottleneck

Use 17 agents, one per base partition. Every parent→child partition edge has one or two distinct parent boundary vertices in the source pool.

For each child, the parent emits exactly one boundary `(vertex, color)` fact per round, cycling through the sorted relevant parent boundary vertices. The message becomes visible one round later.

Persistent message memory is bounded to two keyed facts per child. Updating an existing vertex replaces its color without increasing memory.

## 3. Modes

1. `full_message`: full parent boundary assignment every round; symbolic upper bound.
2. `compressed_persistent`: one fact/round; bounded message cache and candidate/tie state persist.
3. `compressed_cache_reset`: one fact/round; candidate/tie state persist, but message cache contains only the newest fragment.
4. `compressed_all_reset`: one fact/round; message cache and candidate/tie state reset each round.
5. `compressed_shuffled`: persistent bounded state, but fragments are delivered to the wrong child by a frozen cyclic permutation.
6. `no_message`: no cross-agent facts.

## 4. Round budgets

$$
T\in\{1,2,4,8,16,32\}.
$$

All 32 development instances are run under all modes and budgets.

## 5. Accounting

Report:

- solve and final cross conflicts;
- rounds and 17-agent update calls;
- fragments generated/delivered;
- full-message fact equivalent;
- compression ratio;
- maximum cache facts per agent;
- cache insert/update/eviction counts;
- candidate state changes;
- same-round cross-agent reads;
- official verification.

## 6. Frozen gates

### S0 — semantics and memory bound

- deterministic replay on at least eight rows;
- same-round cross-agent reads = 0;
- message age = 1;
- compressed message contains exactly one fact when a boundary exists;
- maximum cache facts per agent ≤2;
- no hidden full-message access in compressed modes;
- local and official validity pass.

### S1 — compressed persistent competence

At T=32, pooled $\delta\ge4$:

- `compressed_persistent` solve ≥0.90;
- solve is within 0.10 of `full_message`;
- compressed delivered facts are at most 0.60 of the full-message fact equivalent.

### S2 — message-memory necessity

At T=32, pooled $\delta\ge4$:

- compressed persistent solve exceeds `compressed_cache_reset` by at least 0.15;
- final cross conflicts are lower;
- the direction holds in at least two diameter groups.

### S3 — full recurrent-state necessity

At T=32, compressed persistent solve exceeds `compressed_all_reset` by at least 0.15.

### S4 — correct-message necessity

At T=32, compressed persistent solve exceeds shuffled and no-message controls by at least 0.15.

### S5 — recurrence depth

Compressed persistent solve is nondecreasing with T, and its first T reaching 0.90 solve is weakly larger for at least one high-diameter group than for a low-diameter group.

## 7. Verdicts

- S0–S5 pass: `RPD_COMPRESSED_STATE_NECESSITY_GO`;
- S0/S1/S4/S5 pass but S2 or S3 fails: `RPD_COMPRESSED_MESSAGE_RECURRENCE_ONLY`;
- S0 passes but S1 fails: `RPD_COMPRESSED_STATE_NO_GO`;
- S0 fails: `RPD_COMPRESSED_STATE_SEMANTICS_FAIL`.

A GO authorizes lightweight GRU/structured-state development. It does not authorize Qwen or a GPU speedup claim.
