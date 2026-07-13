# Cost-Sensitive Recurrent Verification Development v1

- Frozen date: 2026-07-12
- Status: frozen before cost-sensitive outcomes
- Calibration data: eta=0 exact trajectories from the exposed independent graph and SAT pools
- Evaluation data: the same exposed pools; development only

## Objective

For each substrate and diameter, estimate from eta=0 exact recurrence:

- $L_{live}$: mean detector opportunities where correction is unnecessary;
- $L_{dead}$: mean true correction opportunities.

For candidate confirmation depth $k\in\{1,\ldots,8\}$ and noise eta, estimate:

$$
E[Q_k]
=L_{live}\frac{1-\eta^k}{1-\eta}+L_{dead}k,
$$

$$
P_{harm}(k)=1-(1-\eta^k)^{L_{live}},
$$

$$
C(k)=E[Q_k]+5000P_{harm}(k).
$$

Choose the smallest $k$ minimizing $C(k)$. At eta=0 choose $k=1$.

This is one universal optimization rule. Substrate-specific schedules are permitted only through measured eta=0 exposure counts.

## Development execution

- exposed independent graph pool: 200 instances;
- exposed independent SAT pool: 200 instances;
- six eta values;
- one new cost-sensitive arm;
- 2,400 new rows;
- stored exact, soft2, and exposure-only adaptive controls reused.

## Gates

- K0 formula/replay/protocol integrity.
- K1 robust solve ≥0.95 in every graph and SAT cell.
- K2 graph repair: diameter16 eta=.20 solve≥0.95, work lower than fixed soft2, and mean over-corrections≤soft2.
- K3 SAT repair: diameter8/16 eta=.20 solve≥0.95 and work lower than fixed soft2.
- K4 verification economy: every selected depth is below the maximum $k=8$; for eta≤.10 every selected depth is at most 5; actual detector-query overhead is reported for every cell.
- K5 perfect-signal equivalence to exact.
- K6 every selected k is the exact argmin of the frozen cost objective.

## Verdicts

- all gates: `RPD_COST_SENSITIVE_GUARD_DEV_GO_CONFIRMATION`;
- robust but economy/repair fails: `RPD_COST_SENSITIVE_GUARD_ROBUST_NO_VALUE`;
- robustness fails: `RPD_COST_SENSITIVE_GUARD_NO_GO`;
- integrity fails: `RPD_COST_SENSITIVE_GUARD_PROTOCOL_FAIL`.

A GO authorizes new zero-overlap graph and SAT confirmations with calibration/schedule frozen. No Qwen claim is authorized.
