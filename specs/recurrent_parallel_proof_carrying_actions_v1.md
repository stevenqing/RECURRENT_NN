# Recurrent Parallel Proof-Carrying Actions v1

## Status

`FROZEN_AFTER_OPENED_BROAD_DETERMINISTIC_BASELINES_BEFORE_MODEL_WITNESS_SYNTHESIS`

## Central Claim

Stateful tool-use agents should serialize writes only when exactly one candidate action carries a deterministic, replayable proof binding immutable evidence to the proposed write arguments.

## Mechanism

1. Parallel agents propose candidate actions and proof sketches.
2. A barrier evaluates all proofs against the same immutable pre-write snapshot.
3. The controller commits only if exactly one candidate proof is valid.
4. Missing, invalid, or competing proofs become recurrent state for the next round.

## Proof Obligations

- `literal_intent_binding`
- `derived_path_binding`
- `prior_effect_binding`
- `ordered_role_binding`
- `relational_entity_binding`
- `state_delta_binding`

## Current Opened-Data Lower Bound

The broad safe derivation ledger v5 establishes a deterministic opened-data lower bound:

- 1266 value-bound witness instances
- 334 commit-live
- 231 ambiguous both valid
- 701 abstain no valid
- 0 unsafe unique-wrong

This is not a sealed confirmation result and not an LLM synthesis result.

## Claim Boundary

The contribution is the recurrent commit protocol and proof-obligation framing, not hand-written AppWorld API rules. The verifier implementations are measurement instruments for testing whether proof obligations recover safe commits while preserving a zero-unsafe gate.

## Next Required Protocol

Before any LLM result can be meaningful:

- freeze prompt grammar for proof-sketch synthesis;
- keep labels and proof outcomes blinded from prompts;
- compare against direct action, provenance count, occurrence verifier, API-aware mapper, hand-coded template witnesses, best-of-N, and sequential matched-budget synthesis;
- keep variations 10-12 sealed until adversarial witness search and budget gates are frozen.