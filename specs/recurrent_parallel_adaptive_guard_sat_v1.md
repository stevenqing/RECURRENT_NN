# Exposure-Calibrated Recurrent Verification — SAT Development v1

- Frozen date: 2026-07-12
- Status: frozen before adaptive-guard outcomes
- Parent failure: `RPD_SIGNAL_SAT_DEV_NO_GO`
- Source data: exposed 32-instance SAT development manifest
- Headline eligible: No

## Policy

For false-positive rate $\eta$, dependency diameter $\delta$, target survival $p_0=0.95$, and conservative harmful-exposure proxy

$$
L_{proxy}=16(\delta+1),
$$

choose the smallest confirmation depth $k$ satisfying

$$
(1-\eta^k)^{L_{proxy}}\ge p_0.
$$

Equivalently, for $\eta>0$:

$$
 k(\eta,\delta)
 =\max\left(1,
 \left\lceil
 \frac{\log(1-p_0^{1/L_{proxy}})}{\log\eta}
 \right\rceil
 \right),
$$

and $k(0,\delta)=1$.

The formula, $p_0$, and exposure proxy are frozen before adaptive-policy outcomes. No $k$ is selected from current solve results.

## Frozen schedule

| Diameter | eta=.01 | .02 | .05 | .10 | .20 |
|---:|---:|---:|---:|---:|---:|
| 2 | 2 | 2 | 3 | 3 | 5 |
| 4 | 2 | 2 | 3 | 4 | 5 |
| 8 | 2 | 3 | 3 | 4 | 5 |
| 16 | 2 | 3 | 3 | 4 | 6 |

## Development execution

- same SAT manifest and recurrent engine;
- T=32;
- six eta values;
- one adaptive policy arm, 192 new rows;
- compare against frozen `R_exact`, `R_soft2`, and `R_commit` rows without rerunning or modifying them;
- every additional detector query is charged.

## Gates

### A0 policy integrity

- computed $k$ exactly matches the frozen schedule;
- deterministic replay;
- no same-round reads, invalid message ages, local/official failures, or planted access;
- detector queries equal the executed sequential confirmation logic.

### A1 robust solve

Adaptive solve ≥0.90 for every diameter and eta through 0.20.

### A2 repair of failed SAT cells

At eta=.20:

- adaptive solve at diameter 8 exceeds fixed soft2 by at least 0.10;
- adaptive solve at diameter 16 exceeds fixed soft2 by at least 0.50.

### A3 hazard control

For every diameter/eta cell, mean adaptive over-corrections ≤ mean soft2 over-corrections; at diameter 16, eta=.20, adaptive mean over-corrections ≤1.0.

### A4 perfect-signal efficiency

At eta=0, adaptive is identical to one-hit exact in solve, rounds, corrections, and work.

### A5 charged Pareto value

At diameter 8/16 and eta=.20, adaptive has higher solve and lower failure-penalized work than fixed soft2 despite extra verification queries.

## Verdicts

- A0–A5 pass: `RPD_ADAPTIVE_GUARD_SAT_DEV_GO_CONFIRMATION`;
- A0/A1/A4 pass but repair/Pareto fails: `RPD_ADAPTIVE_GUARD_ROBUST_NO_VALUE`;
- robust solve fails: `RPD_ADAPTIVE_GUARD_SAT_NO_GO`;
- integrity fails: `RPD_ADAPTIVE_GUARD_PROTOCOL_FAIL`.

A GO authorizes a new zero-overlap SAT confirmation with the formula unchanged. It does not authorize Qwen or a cross-substrate claim.
