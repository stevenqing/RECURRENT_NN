# Matched-Window SAT Route Development Contract v1

- Frozen date: 2026-07-12
- Timing: after the route-confirmation no-go and its post-hoc control audit, before any `deepest-window-valid` arm outcome
- Evidence tier: exposed-pool mechanism development only
- Parent closeout: [SAT route confirmation](../results/multiagent_sat_route_confirmation/CLOSEOUT.md)

## 1. Motivation

The frozen deepest and random-valid policies did not isolate target ranking. Random-valid filters candidates to the current target-owner window before sampling; frozen deepest can first request an out-of-window priority target and receive a NACK. The observed request/NACK gap is too large to interpret the no-go as a pure deepest-versus-random ranking result.

## 2. New control

`independent_local_deepest_window_valid_sat` reuses the exact frozen `queued_random_valid` engine, including:

- the same owner-local state and scheduler;
- the same target-window prefilter;
- the same queued request protocol;
- the same memory/channel/work accounting;
- the same no-fallback behavior.

Its only intended change is selection within the filtered candidates: choose the candidate with maximum fixed-order position rather than a frozen random draw.

Implementation uses a sequential shadow wrapper that substitutes a deterministic last-index RNG while calling the frozen engine, then relabels the resulting arm. Concurrent calls are forbidden because the substitution is process-global within its context.

## 3. Development data

- all 200 instances from the now-exposed route-confirmation manifest;
- existing frozen random-valid and deepest rows may be reused as controls;
- these instances can never provide future confirmation for this new policy;
- no new instance generation occurs in development.

## 4. Frozen resources

- $M=4$, $R=8$, $MR=32$;
- activation cap 20,000;
- channel cap 16;
- route seed 20260712;
- no GPU, LLM, oracle fallback, planted assignment, or post-outcome target change.

## 5. Development gates

### D0 — implementation and protocol

- 200 new-arm rows;
- deterministic replay on at least 16 fixed rows;
- all ownership, priority, request-conservation, channel, memory-window, and official verification checks pass.

### D1 — operational matching

- mean NACKs $\leq1.0$;
- mean window rejections $\leq1.0$;
- declared memory/channel resources exactly match random-valid.

### D2 — practical solve signal

Matched-window deepest minus random-valid solve rate $\geq0.10$.

### D3 — paired statistical direction

One-sided exact McNemar probability for matched-window deepest superiority $\leq0.05$.

### D4 — expected-work direction

- failure-penalized matched-window-deepest/random-valid ratio $\leq0.90$;
- paired-bootstrap upper 95% bound $<1.00$.

## 6. Verdicts

- all D0–D4 pass: `SAT_MATCHED_ROUTE_DEV_GO_CONFIRMATION`;
- otherwise: `SAT_MATCHED_ROUTE_DEV_NO_GO`;
- protocol failure: `SAT_MATCHED_ROUTE_DEV_PROTOCOL_FAIL`.

A development GO authorizes only a new untouched symbolic confirmation. It does not authorize Qwen. Qwen can be considered only after the new matched policy independently passes the same solve, exact-pair, and expected-work gates.

## 7. Claim boundary

This is control repair, not algorithm novelty. A positive development result would show only that the prior comparison was obscured by candidate-validity handling and that a clean route-ranking confirmation is worth running.
