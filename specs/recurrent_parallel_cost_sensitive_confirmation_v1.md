# Cost-Sensitive Recurrent Verification — Joint Confirmation v1

- Frozen date: 2026-07-12
- Status: frozen before new manifests/outcomes
- Prerequisite: `RPD_COST_SENSITIVE_GUARD_DEV_GO_CONFIRMATION`

Unified policy:

$$
k^*=\arg\min_{k\in\{1,\ldots,8\}}
\left[L_{live}\frac{1-\eta^k}{1-\eta}+L_{dead}k+5000\left(1-(1-\eta^k)^{L_{live}\right)\right].
$$

$L_{live},L_{dead}$ are frozen eta=0 calibration means from prior independent pools. No recalibration occurs on confirmation data.

## New pools

- Graph: seed 750000, 50/diameter, 200 total, zero prior hash overlap.
- SAT: seed 760000, 50/diameter, 200 total, zero prior hash overlap.
- Fixed density/clause counts and exact diameters unchanged.

## Execution

- T=32; six eta levels;
- adaptive-cost, exact, soft2, commit;
- 4,800 rows/substrate, 9,600 total;
- every query charged; failure penalty 5,000.

## Gates

- J0 all locks, manifests, schedules, replay, Jacobi/message/local/official integrity.
- J1 adaptive solve≥0.95 in every graph and SAT cell.
- J2 eta=0 adaptive identical exact in both substrates.
- J3 graph diameter16/eta.20 adaptive has higher solve and lower work than soft2.
- J4 SAT diameter8/16 eta.20 adaptive has higher solve and lower work than soft2.
- J5 adaptive over-corrections≤1 in every cell and schedules exactly match frozen cost argmins.
- J6 exact one-hit hazard increases with eta and commit fails at eta=0, in both substrates.

## Verdicts

- all gates: `RPD_COST_SENSITIVE_CROSS_SUBSTRATE_CONFIRMATION_PASS`;
- one substrate fails value but robustness passes: `RPD_COST_SENSITIVE_ROBUST_SCOPE_LIMITED`;
- robustness fails: `RPD_COST_SENSITIVE_CONFIRMATION_FAIL`;
- integrity fails: `RPD_COST_SENSITIVE_PROTOCOL_FAIL`.

A pass supports a common cost-sensitive allocation rule with substrate-calibrated exposure statistics. It does not establish a real signal anchor, learned policy, Qwen benefit, or GPU speedup.
