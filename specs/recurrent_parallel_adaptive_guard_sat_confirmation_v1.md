# Exposure-Calibrated SAT Guard Independent Confirmation v1

- Frozen date: 2026-07-12
- Status: frozen before new manifest and outcomes
- Prerequisite: `RPD_ADAPTIVE_GUARD_SAT_DEV_GO_CONFIRMATION`
- Policy unchanged:

$$
L_{proxy}=16(\delta+1),\qquad
k(\eta,\delta)=\min\{k:(1-\eta^k)^{L_{proxy}}\ge0.95\}.
$$

## Manifest

- new split `adaptive_sat_confirmation`;
- base seed 740000;
- exact diameters 2, 4, 8, 16;
- 50 instances per diameter, 200 total;
- fixed 264 clauses per instance;
- zero ID and clause-hash overlap with development;
- planted assignments removed;
- no policy outcomes during selection.

## Execution

- T=32;
- eta 0, .01, .02, .05, .10, .20;
- adaptive, exact, soft2, and commit policies;
- 4,800 rows;
- failure penalty 5,000;
- every detector query charged.

## Frozen gates

- C0 integrity: lock, manifest, schedule, replay, Jacobi/message/local/official validity.
- C1 perfect signal: adaptive identical to exact and solve≥0.95 every diameter.
- C2 adaptive robustness: adaptive solve≥0.95 every diameter/eta.
- C3 failed-cell repair: at eta=.20 adaptive exceeds soft2 solve by ≥0.05 at diameter 8 and ≥0.50 at diameter 16.
- C4 hazard control: adaptive mean over-corrections ≤soft2 in every cell and ≤1 at diameter16/eta.20.
- C5 charged value: at diameter8/16 eta=.20 adaptive has higher solve and lower penalized work than soft2.
- C6 signal necessity: eta=0 exact/adaptive solve exceeds commit by ≥0.80 every diameter; exact one-hit hazard increases with eta.

## Verdicts

- all gates: `RPD_ADAPTIVE_GUARD_SAT_CONFIRMATION_PASS`;
- integrity/robustness pass but value fails: `RPD_ADAPTIVE_GUARD_SAT_ROBUST_NO_VALUE`;
- robustness fails: `RPD_ADAPTIVE_GUARD_SAT_CONFIRMATION_FAIL`;
- integrity fails: `RPD_ADAPTIVE_GUARD_SAT_PROTOCOL_FAIL`.

A pass confirms adaptive hazard-budgeted verification on SAT. A cross-substrate policy claim still requires applying the same adaptive formula to the independent graph pool or clearly scoping graph to fixed two-hit.
