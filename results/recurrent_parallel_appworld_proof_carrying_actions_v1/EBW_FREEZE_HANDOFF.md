# EBW Obligation-Sketch Freeze Handoff

## Status: **`FREEZE_DOCUMENT_WRITTEN_NOT_TAGGED`**

The EBW LLM obligation-sketch synthesis freeze spec has been written. No git tag has been created, and sealed variations 10-12 remain closed.

## Artifacts

- Main freeze spec: `specs/recurrent_parallel_ebw_obligation_sketch_synthesis_v1.md`
- Structured freeze contract: `specs/recurrent_parallel_ebw_obligation_sketch_synthesis_v1.json`
- Related-work positioning: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/RELATED_WORK_positioning_v1.md`
- Research contribution memo: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/RESEARCH_CONTRIBUTION.md`

## Track A Gate

Track A is the viability gate. It uses a narrow four-pattern grammar and passes only if:

- `unsafe_unique_wrong == 0`; and
- safe commits are at least 167, which is 0.5 recovery against ledger v5's 334 safe commits.

## Track B Gate

Track B is locked behind Track A PASS. It introduces compositional predicates plus a role-sufficiency table and adversarial wrong-value witness search.

## Important Boundary

The model emits sketches, never decisions. The deterministic verifier and unique-validity barrier remain the commit authority.