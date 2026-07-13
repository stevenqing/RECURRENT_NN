# Multi-Agent Capacity × Coupling Core 2×2 Preregistration v1

- Frozen date: 2026-07-11
- Stage: no-LLM symbolic phase-map preflight before any real-Qwen confirmatory run
- Primary paper line: multi-agent capacity–coupling
- Parent roadmap: [Multi-Agent Capacity–Coupling Paper Roadmap](multiagent_capacity_coupling_paper_roadmap_v1.md)

## Scientific Question

When does a bounded team outperform a monolith, and is any advantage more than the sum of its memory?

## Fixed Configuration

- Agents: `M=4`
- Per-agent recovery window: `R=8`
- Equal-total-memory monolith window: `MR=32`
- Vertices per block: `12`
- Total vertices: `48`
- Colors: `4`
- Total edges: exactly `96` in every instance
- Symbolic node cap: `5000`
- Low coupling generator parameter: `b=2`
- High coupling generator parameter: `b=8`
- Under-capacity target conflict depth: `4`
- Over-capacity/local-fit target conflict depth: `12`
- Preflight target: `16` instances per cell

## Intrinsic Capacity Strata

Strata are assigned only from an unlimited-capacity symbolic reference trace, never from the five evaluated arms.

For each instance measure:

- `global_recovery_distance`: maximum number of global trail entries removed by the reference CBJ target;
- `local_recovery_distance`: maximum number of entries from the target agent's local trail that must be addressed.

Definitions:

- `under`: `global_recovery_distance <= R`;
- `over_local_fit`: `global_recovery_distance > R` and `local_recovery_distance <= R`.

Instances with `local_recovery_distance > R`, reference failure, wrong target depth, or failed fixed-density normalization are rejected before any evaluated arm is read.

## Coupling Control

All instances have exactly 96 edges. Coupling changes the fraction of cross-partition edges; normalization may add only intra-partition edges that preserve a valid planted coloring. The target conflict depth is reverified after normalization.

Required coupling gate:

- mean `rho_actual(high) - rho_actual(low) >= 0.15`;
- every instance has exactly 96 edges.

## Four Cells

| Cell | Capacity stratum | Coupling | Prediction |
|---|---|---|---|
| A | under | low | monolith-R is sufficient; little team gain |
| B | under | high | little capacity gain; higher coordination cost |
| C | over_local_fit | low | largest team-vs-monolith-R gain |
| D | over_local_fit | high | team gain shrinks under coordination stress |

## Five Primary Arms

1. `team_cbj`: four bounded local windows, conflict-directed target;
2. `team_chronological`: four bounded local windows, latest global target;
3. `monolith_R`: one global recovery window of size 8;
4. `monolith_MR`: one global recovery window of size 32;
5. `centralized_sharded_MR`: one centralized solver with the same four local windows as the team.

The symbolic `team_cbj` and `centralized_sharded_MR` use identical search decisions in this preflight. Their required rowwise equality is an implementation control, not a positive architecture claim.

## Enforced Recovery Semantics

- The environment may hold the current assignment and a full audit trail.
- A recovery target is usable only when it lies inside the arm's declared recovery window.
- Otherwise the row fails as `NO_RECOVERY_TARGET`.
- Team arms use one window of size R per agent.
- `monolith_R` uses one global window R.
- `monolith_MR` uses one global window MR.
- No arm may silently fall back to an oracle or larger window.

## Preflight Gates

1. `pool_complete`: 16 accepted instances per cell.
2. `fixed_density`: all rows have 96 edges.
3. `capacity_strata_exact`: all under/over definitions hold.
4. `coupling_separated`: high-minus-low mean rho ≥0.15.
5. `reference_solved`: all accepted instances pass global verification under unlimited reference capacity.
6. `centralized_equivalence`: team-CBJ and centralized-sharded solve/status match rowwise.
7. `monolith_under_readable`: monolith-R solve rate ≥0.50 in under cells.
8. `capacity_relief_signal`: in over/low, team-CBJ solve rate exceeds monolith-R by ≥0.20.
9. `equal_memory_control`: team-CBJ is within ±0.10 of monolith-MR in over/low; a larger gain would require separate validation.
10. `coupling_interaction_signal`: team-minus-monolith-R gap in over/low exceeds over/high by ≥0.05.
11. `coordination_signal`: team-CBJ exceeds team-chronological by ≥0.10 in at least one over-capacity cell.

This preflight is GO for real-Qwen only if gates 1–7 pass and at least two of gates 8–11 pass. It establishes no paper claim.

## Confirmatory Hypotheses Reserved for Real Qwen

The future frozen-Qwen run will use an independent 50-instance-per-cell manifest and four Holm-corrected primary tests:

1. team-CBJ > monolith-R in over/low;
2. team-CBJ > monolith-MR in over/low;
3. capacity × coupling interaction on team-minus-monolith-MR;
4. team-CBJ communication/retraction cost < team-chronological.

No confirmatory instance may be selected by an evaluated arm's solve outcome.

## Honesty Boundary

The symbolic preflight validates generator power, capacity strata, recovery-window fairness, and implementation. It does not establish frozen-Qwen multi-agent performance, agent autonomy, or a team advantage beyond equal total memory.
