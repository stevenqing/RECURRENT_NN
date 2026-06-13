# Reasoning Gym Baseline-First Plan v1

The program is reweighted again: before additional method claims, build a stable Reasoning Gym baseline matrix and run it on the target benchmarks. Methods are evaluated only after the baseline ledger is in place.

## Scope

Initial Tier-1 benchmarks:

- `graph_color`
- `sudoku`
- `zebra_puzzles`

All rows use official Reasoning Gym `dataset.score_answer(answer, entry)` for solve labels.

## Baseline Arms

- `official_oracle_answer`: scoring sanity and upper-bound answer-format check.
- `empty_answer`: trivial floor and scorer smoke.
- `L0-symbolic-heuristic`: deterministic CSP heuristic where a structural adapter exists.
- `L0-symbolic-random`: random CSP search where a structural adapter exists.
- `L1-one_shot_direct`: frozen LLM direct answer with total token accounting.
- `L1-one_shot_cot`: optional frozen LLM CoT/direct-final baseline with total token accounting.

Graph_color and sudoku have structural adapters. Zebra symbolic baselines remain adapter-pending until a structural parser/adapter is built; zebra still participates in official scoring and LLM one-shot baselines.

## Execution Order

1. Build and smoke-test the unified baseline matrix harness.
2. Run no-LLM official/scoring/symbolic baselines on Tier-1.
3. Run LLM one-shot baselines with anti-truncation/token accounting.
4. Only then resume externalized M-register and multi-agent method comparisons on the same benchmark/config rows.

## Guardrails

- No method superiority claim before baseline matrix exists.
- No completion-only token comparisons.
- Do not treat zebra symbolic baselines as complete until a structural adapter exists.
- Externalization and internalization work resumes after baselines are present.