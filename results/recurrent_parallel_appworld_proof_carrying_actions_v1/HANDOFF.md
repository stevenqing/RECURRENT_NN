# Proof-Carrying Actions Handoff

## Status: **`RESEARCH_CONTRIBUTION_FRAMED`**

This handoff reframes the current AppWorld work as a research contribution rather than a schema-completion engineering task.

## Core Idea

Parallel tool-using agents should propose `(action, proof sketch)` pairs. A deterministic barrier commits only when exactly one candidate proof verifies against the immutable pre-write snapshot. Missing, invalid, or competing proofs trigger recurrence or abstention.

## Current Evidence

- LLM confidence judge failed: pooled balanced accuracy 0.566 and calibration failed.
- Scalar occurrence verifier failed: 386 unsafe unique-wrong over 1266 broad instances.
- API-aware proof-family mapper saturated proof-family classification at 45/45, so family-name selection is not a research target.
- Safe derivation ledger v5: 334 commit-live, 231 ambiguous, 701 abstain, 0 unsafe over 1266 opened instances.

## Research Claim Boundary

Defensible now: proof-carrying action proposals are a better recurrent control object than confidence, voting, scalar provenance, or value occurrence for stateful writes.

Not yet defensible: autonomous LLM proof synthesis, sealed benchmark performance, or AppWorld API rules as the contribution.

## Next Real Experiment

Freeze and run LLM proof-sketch synthesis:

- model emits bounded proof sketches only;
- deterministic verifier decides validity;
- barrier commits only under unique proof;
- compare to direct action, occurrence verifier, API-aware mapper, hand-coded templates, best-of-N, and sequential matched-budget synthesis;
- keep `unsafe_unique_wrong = 0` as the safety gate;
- keep fresh variations 10-12 sealed until all gates are frozen.

## Artifacts

- Spec: `specs/recurrent_parallel_proof_carrying_actions_v1.md`
- Structured spec: `specs/recurrent_parallel_proof_carrying_actions_v1.json`
- Contribution memo: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/RESEARCH_CONTRIBUTION.md`