# AppWorld A4 — Comparative Evidence Development v1

- Frozen date: 2026-07-12
- Status: frozen before comparative-model outcomes
- Source: the 15 exposed train pairs from A3
- Purpose: method development only; no confirmation or task-completion claim

## Motivation

A3 failed because Qwen returned the same Boolean decision for all 15 matched live/dead pairs with confidence 0.95. An independent binary judge confounds proposal quality with task/API-level risk and discards entity evidence discovered earlier than the final four calls.

## Frozen arms

For each A3 pair, construct two candidate orders (AB and BA) for each arm:

1. **C1 comparative-local:** task goal, public API schema, the same bounded recent history as A3, and both candidate argument objects.
2. **C2 comparative-provenance:** C1 plus candidate-specific evidence citations extracted deterministically from the complete committed prefix.
3. **D provenance guard:** no model call; choose the candidate with more field-compatible provenance citations, otherwise abstain.

Expected model prompts: $15\times2\text{ arms}\times2\text{ orders}=60$.

## Provenance extraction

For every field where candidates differ, scan only calls committed before the proposal. Match scalar values against non-sensitive response and argument fields. A citation contains source app, API, call index, field path, and a compact redacted containing object. Passwords, tokens, cards, CVVs, hidden evaluators, future calls, and labels are forbidden. At most three citations per differing field and candidate are shown.

The extractor is candidate-symmetric and label-blind. Candidate order is hash-determined; the second prompt swaps the order exactly.

## Output

Strict JSON only:

`{"preferred_candidate":"A"|"B","confidence":number}`

Confidence is the probability that the chosen candidate is better. No fallback or parse repair.

## Development gates

- D0 manifest: 15 pairs, 60 unique prompts, exact AB/BA swaps, no protected leakage.
- D1 order: C2 order consistency at least 0.80.
- D2 quality: C2 accuracy at least 0.70 in each order and pair-both-orders-correct at least 0.60.
- D3 comparative value: C2 accuracy exceeds C1 by at least 0.10.
- D3 deterministic value: provenance guard achieves at least 0.80 accuracy on covered pairs with at least 0.50 coverage.
- D4 honesty: A3 remains unchanged; all tasks are exposed train development; latency under GPU contention is non-authoritative.

There are two independent exits:

- comparative-LLM GO requires D0, D1, D2, D3-comparative, and D4;
- deterministic-provenance GO requires D0, D3-deterministic, and D4, regardless of the LLM arm.

Either GO authorizes one corresponding frozen confirmation on untouched multi-app dev task types. It does not authorize test use or an end-to-end claim.
