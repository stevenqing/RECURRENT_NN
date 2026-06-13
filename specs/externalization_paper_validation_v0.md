# Externalization Paper Validation v0

This preregistration validates only the externalization thesis: a bounded reversible register outside a frozen LLM confers search-completeness, register capacity produces a budgeted solve-rate law, bounded teams can exceed a monolith under separator structure, and CBJ coordination is structure-dependent.

It explicitly does not cover internalization into model parameters: no training, distillation, RL, or learned operator updates are in scope.

## Anchors

- Claims 1 and 2 on Reasoning Gym `graph_color` are inherited from Item070: real Qwen3.5, official `score_answer`, forward/one-shot zero, reversible R sweep to 0.9667.
- Multi-agent claim 4 symbolic capacity and claim 3 structure-dependent closeout are inherited from Item076.

## Mandatory Method Upgrade

- Primary observable: solve rate under matched node budget, swept over budgets `{20, 40, 80, 160, 320}`.
- Raw complete-solver solve rate is not a primary comparison.
- Difficulty bins must reach a hard regime where no-LLM random or pure heuristic arms degrade, targeting random-culprit solve rate below 0.7 in the hardest bin when possible.

## Primary Matrix

- Benchmarks: Reasoning Gym `graph_color`, `zebra_puzzles`, `sudoku`.
- Arms: M-register R sweep `{0, 2, 4, 8, 16}`, L0-symbolic-heuristic, L0-symbolic-random, L1-oneshot-vanilla, L1-oneshot-thinking.
- Verdicts: claim 1, claim 2, and the LLM-adds-value fork.

## Secondary Positioning Matrix

- Benchmarks: one Tier-1 benchmark plus ZebraLogic.
- Arms: L1-bestofN, L1-selfverify, L2-ToT, L3-llm2solver, optional L3-llm-modulo.
- L3-llm2solver is a ceiling/context arm, not the target to beat.

## Multi-Agent Matrix

- Venues: AgentsNet direct `Coloring.get_score`, controlled partitions of `graph_color`, controlled partitions of `zebra_puzzles`.
- Arms: CBJ, chrono, forward, team-vs-monolith no-LLM, team-vs-monolith frozen-LLM agents.
- Claim 3 is a one-read separator sweep after Item076; no new dense graph_color instrument cycle.
- Claim 4b real-LLM capacity must sweep global-trail length relative to a single register rather than condition on the Item076 symbolic monolith-fail intersection.

## Kill Forks

- If L1-oneshot-thinking solves a non-trivial fraction above 0.3 on hard bins, scope claim 1 to vanilla one-shot rather than all thinking-style one-shot inference.
- If M-register is within noise of L0-symbolic-random or L0-symbolic-heuristic at matched budget, bank the LLM-adds-value negative and frame the contribution as external structure conferring search-completeness on a frozen LLM.
- If ToT/best-of/selfverify match M-register, narrow the contribution to bounded-memory prompt-flat efficiency.
- If the frozen-LLM team gap does not open past single-register capacity, scope real-LLM claim 4b while preserving the symbolic capacity positive.

## Current v0 Status

This document is paired with `results/externalization_validation_v0/preflight.json`. The v0 artifact is a preregistration and harness preflight, not the full real-LLM matrix result.