# RELATED WORK Positioning v1

## Naming

Use **Evidence-Bound Writes (EBW)** for the experimental protocol and **Proof-Carrying Actions** for the broader mechanism.

EBW names the concrete stateful-write test: a write argument is accepted only when a proof sketch binds it to evidence roles in the immutable snapshot or prior effects.

## What We Are Not Claiming

- We do not claim to invent proof sketching or sketch-repair loops.
- We do not claim the LLM is the judge.
- We do not claim proof-family classification is hard.
- We do not claim AppWorld API rules are the contribution.

## Precedent To Cite Carefully

ProofSketcher (arXiv 2604.06401) is precedent for a sketch -> deterministic-check -> structured-feedback -> local-repair loop in math/logic. In EBW, that loop is not the novelty. The claimable object is the obligation grammar with evidence-role semantics for stateful tool writes.

## Baseline Positioning

| Baseline | Why It Matters |
|---|---|
| direct action | measures unsafe write ceiling |
| self-consistency / voting | tests whether repetition replaces proof; it should not |
| LLM binary correction judge | negative anchor: confidence signal failed |
| scalar provenance / occurrence | negative anchor: value presence is not binding |
| API-aware family mapper | saturated proof-family labels; family naming is not the task |
| hand-coded templates | deterministic skyline/lower bound for recoverable safe commits |
| sequential matched-budget synthesis | isolates parallel proof search from total call budget |
| Agent-Sentry L1+L2 taint | external taint-style safety baseline; contrasts taint flow with role binding |

## Positive Differentiator

EBW's differentiator is **role sufficiency**: true facts are not enough. The proof must explain why those facts bind the write argument for this schema. A true but irrelevant predicate is a `role_mismatch`, not a valid proof.

## Current Evidence

- Occurrence verifier: 386 unsafe unique-wrong over 1266 instances.
- API-aware family mapper: 45/45, so naming the obligation family is trivial.
- Safe derivation ledger v5: 334 commit-live, 0 unsafe over 1266 opened instances.

This positions EBW as a proof-obligation and barrier protocol, not a generic verifier engineering exercise.