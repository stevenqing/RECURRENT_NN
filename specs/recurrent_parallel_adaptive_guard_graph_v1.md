# Exposure-Calibrated Recurrent Verification — Graph Development v1

- Frozen date: 2026-07-12
- Status: frozen before graph adaptive outcomes
- SAT prerequisite: `RPD_ADAPTIVE_GUARD_SAT_CONFIRMATION_PASS`
- Source: exposed independent graph signal pool and frozen graph controls
- Policy unchanged from SAT:

$$
L_{proxy}=16(\delta+1),\qquad
k=\min\{k:(1-\eta^k)^{L_{proxy}}\ge0.95\}.
$$

## Execution

- 200 exposed graph instances;
- T=32, six eta levels;
- 1,200 new adaptive rows;
- stored exact/soft2/commit controls reused unchanged.

## Gates

- G0 integrity: formula schedule, replay, Jacobi/message/local/official validity.
- G1 robust solve: adaptive solve≥0.95 every diameter/eta.
- G2 hazard control: adaptive over-corrections≤soft2 every cell.
- G3 perfect-signal equivalence: adaptive k=1 identical to exact.
- G4 high-exposure value: at diameter16/eta.20 adaptive solve exceeds soft2 by≥0.05 and penalized work is lower.
- G5 no unnecessary broad claim: for cells where soft2 already solve=1, report adaptive verification overhead even if adaptive is not cheaper.

## Verdicts

- G0–G5: `RPD_ADAPTIVE_GUARD_GRAPH_DEV_GO_CONFIRMATION`;
- robust but no high-exposure value: `RPD_ADAPTIVE_GUARD_GRAPH_ROBUST_NO_VALUE`;
- robustness failure: `RPD_ADAPTIVE_GUARD_GRAPH_NO_GO`;
- integrity failure: `RPD_ADAPTIVE_GUARD_GRAPH_PROTOCOL_FAIL`.

A GO authorizes a new zero-overlap graph confirmation using the same formula. No Qwen claim is authorized.
