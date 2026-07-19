# EBW Test-Time Compute Protocol v1

## Status: **`FROZEN_BEFORE_PROSPECTIVE_TEST_TIME_COMPUTE_OUTCOMES`**

This protocol corrects the claim boundary after v29b. The current EBW result proves the residual-to-frontier repair substrate and model-in-the-loop primitive selection over a fixed action space. It does **not** yet prove that extra test-time compute discovers repairs on held-out tasks without human frontier edits.

## Research Question

Can typed verifier residuals make test-time compute useful for multi-agent proof-carrying action systems by turning failed verifier checks into structured repair decisions selected by a RepairAgent under a fixed compiler and MetaVerifier?

## Frozen Substrate

The following must be frozen before any prospective held-out outcome is observed:

- strict parser and proof schemas;
- runner verifier and CPU rescorer;
- v29 primitive library;
- deterministic compiler and MetaVerifier;
- RepairAgent primitive-selection response contract;
- residual packet schema.

## Allowed Test-Time Compute

At test time, the system may:

1. run proof agents under the frozen proof schema;
2. collect verifier-emitted typed residual packets;
3. ask RepairAgent to select primitive IDs from the frozen library;
4. compile selected primitives with the frozen compiler;
5. accept only proposals accepted by the frozen MetaVerifier;
6. rerun or continue proof search under accepted frozen frontiers.

## Forbidden Test-Time Compute

At test time, the system may not:

- manually add proof families or primitive IDs;
- edit parser, verifier, compiler, or MetaVerifier;
- relax strict JSON parsing;
- count prompt-only instructions as frontier repair;
- create residual taxonomies after seeing held-out outcomes;
- open sealed AppWorld variations before this protocol and code freeze are recorded.

## Two-Stage Execution

### Stage A: Retrospective Replay

Use v17 as the base gate and v29b selected primitives as frozen RepairAgent decisions. This checks that the loop mechanics are executable end to end, but it is not a held-out claim because v21-v28 frontiers were researcher-designed on opened data.

### Stage B: Prospective Held-Out TTC

After this freeze, generate or open a preregistered held-out split, preferably fresh AppWorld variations 10-12. The headline test-time compute claim requires this stage.

## Required Baselines

- one-shot proof agents, no repair;
- best-of-N proof sketches, no repair;
- free-form RepairAgent patch JSON;
- structured RepairAgent without MetaVerifier;
- structured RepairAgent with MetaVerifier.

## Claim Boundary

v30 retrospective replay can validate the frozen loop mechanics. Only a preregistered held-out run can support the stronger claim that test-time compute itself solves new residuals without human frontier edits.