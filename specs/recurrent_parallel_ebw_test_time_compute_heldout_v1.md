# EBW Test-Time Compute Held-Out Protocol v1

## Status: **`FROZEN_AFTER_V30_BEFORE_HELDOUT_VALUE_OUTCOMES`**

This protocol starts the prospective held-out test-time compute evaluation after the v30 freeze.

## Scope

- Held-out source: fresh AppWorld variations 10-12.
- Fresh semantic certification must be PASS before use.
- This stage exports only a value-free instance manifest.
- Argument values, response values, value hashes, and protected content remain unexported.
- No model/GPU action is part of this preflight.

## Claim Boundary

This preflight opens held-out structure after the v30 freeze. It does not yet support a held-out test-time compute claim. The claim begins only after frozen baselines and the structured RepairAgent loop are run on held-out rows without editing parser, verifier, primitive library, compiler, or MetaVerifier.

## Next Gates

1. Build held-out value-free instance manifest.
2. Build held-out prompt/context manifests under frozen proof schemas.
3. Run one-shot/no-repair baseline.
4. Run structured RepairAgent with frozen MetaVerifier.
5. Report safe commit, abstain, unsafe, parse/compile/accept rates, and test-time model calls.