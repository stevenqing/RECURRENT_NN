# Multi-Agent Structural Free-Lunch Contribution Contract v1

- Frozen date: 2026-07-11
- Stage: symbolic mechanism development on the already frozen 64-instance core 2×2 manifest
- Parent memo: [Where Is the Multi-Agent Free Lunch?](multiagent_free_lunch_research_memo_v1.md)
- Headline eligibility: **false**; this is a mechanism gate before a new real-Qwen confirmatory manifest

## Research Contribution Under Test

The proposed contribution is not extra aggregate memory. It is **independent local search factorization with dependency-scoped coordination**.

A source agent may send a rollback request but may never mutate another agent's trail or assignment. The target agent executes its own local rollback during its own activation. Unrelated agents retain their search states.

## Frozen Substrate

- Input manifest: `results/multiagent_core_2x2_preflight/instance_manifest.json`
- Cells: capacity under/over-local-fit × coupling low/high
- Instances: 16 per cell, 64 total
- Agents: `M=4`
- Per-agent recovery window: `R=8`
- Equal-total-memory monolith: `MR=32`
- Graph: 48 vertices, 4 colors, exactly 96 edges
- Node/activation cap: 20,000
- Shared request channel cap: 16 pending requests

No instance is regenerated or selected using an evaluated arm outcome.

## Compared Arms

1. `independent_local_cbj`: one cursor/trail/register per agent; conflict-directed cross-agent requests;
2. `independent_local_chronological`: same local state, latest-current-assignment rollback requests;
3. `global_trail_cbj`: existing team-CBJ global-trail/global-suffix implementation;
4. `centralized_sharded_MR`: existing sharded equal-memory centralized control;
5. `monolith_MR`: existing equal-total-memory global monolith;
6. `monolith_R`: existing per-agent-memory monolith context arm.

## Resource Definitions

For every arm report:

- solve rate;
- aggregate branch/rollback work;
- total retractions;
- cross-agent requests and acknowledgements;
- communication tokens;
- critical-path rounds;
- peak local window occupancy;
- total declared memory;
- failure taxonomy.

For existing centralized/global arms, comparable aggregate work is:

$$
W_{existing}=steps+retractions+cross\_block\_messages.
$$

For independent agents:

$$
W_{independent}=branch\_attempts+retractions+requests+acks.
$$

## Protocol Invariants

All must pass:

1. `cross_agent_direct_mutations == 0`;
2. only an owner agent assigns or removes its vertices;
3. every cross-agent rollback has request → target execution → acknowledgement;
4. no target outside its declared `R=8` window is used;
5. no global trail exists in the independent arm;
6. each agent has independent cursor, tried-value state, conflict sets, and trail;
7. global completion is verified over all edges;
8. no oracle/model fallback occurs.

Any violation kills the contribution read.

## Frozen Contribution Gates

### G1 — Solve Non-Inferiority to Equal-Memory Controls

In `over_low`:

- independent-local-CBJ solve rate must be no more than 0.10 below `monolith-MR`;
- independent-local-CBJ solve rate must be no more than 0.10 below `centralized_sharded_MR`.

### G2 — Aggregate-Work Advantage

In `over_low`:

$$
\frac{W_{independent}}{W_{centralized\ sharded}}\le0.80
$$

or

$$
\frac{W_{independent}}{W_{monolithMR}}\le0.80.
$$

At least one must pass.

### G3 — Critical-Path Advantage

In `over_low`:

$$
rounds_{independent}\le0.60\times steps_{centralized\ sharded}.
$$

This is a simulated ideal-parallel critical path and must never be reported as measured wall-clock speedup.

### G4 — Coupling Boundary

Independent-local-CBJ aggregate work in `over_high` must be at least 1.20× its `over_low` work, demonstrating that separator coupling consumes the factorization gain.

### G5 — Coordination Mechanism

In at least one over-capacity cell, independent-local-CBJ must exceed independent-local-chronological solve rate by at least 0.10 or reduce aggregate work by at least 20% at non-inferior solve.

## Verdicts

- `STRONG_STRUCTURAL_FREE_LUNCH_CANDIDATE`: protocol invariants plus G1, G2, G3, G4, and G5 pass.
- `PARALLEL_ONLY_CANDIDATE`: protocol invariants, G1, G3, G4, G5 pass but G2 fails.
- `HORIZONTAL_CAPACITY_ONLY`: protocol invariants and G1 pass, but both G2 and G3 fail.
- `NO_STRUCTURAL_CONTRIBUTION`: protocol invariants or G1 fail.

## Honesty Boundary

This experiment uses symbolic local branching and routing. Even a strong candidate verdict establishes only a mechanism worth taking to an independent real-Qwen study. It does not establish LLM autonomy, measured parallel speedup, or a paper headline.
