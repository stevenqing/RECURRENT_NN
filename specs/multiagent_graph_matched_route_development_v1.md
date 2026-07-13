# Graph-Color Matched-Window Route Development v1

- Frozen date: 2026-07-12
- Timing: after SAT matched-route confirmation and graph control audit, before any graph matched-window arm outcome
- Evidence tier: exposed-pool cross-substrate mechanism development
- Source pool: prior 200-instance structural confirmation manifest

## Mechanism

`independent_local_deepest_window_valid_graph` calls the exact frozen graph `queued_random_valid` control path. It retains the same target-owner-window filter and changes only the draw among filtered candidates to the maximum fixed-order position.

Calls are sequential because the shadow implementation temporarily substitutes the control module's RNG factory.

## Development data and resources

- all 200 exposed graph-color confirmation instances, 50/cell;
- $M=4$, $R=8$, $MR=32$;
- activation cap 20,000;
- request channel cap 16;
- route seed 20260711;
- no GPU, LLM, oracle fallback, or new instance selection.

## Frozen gates

- D0: 200 rows, 16-row deterministic replay, and all protocol/scoring checks pass.
- D1: mean NACKs $\leq1.0$, mean window rejections $\leq2.0$, and resources match random-valid.
- D2: pooled over-cell proposed minus random-valid solve $\geq0.10$ with one-sided exact McNemar $p\leq0.05$.
- D3: proposed solve is no worse than random-valid by more than 0.05 in either `over_low` or `over_high`.
- D4: pooled over-cell proposed/random failure-penalized work ratio $\leq0.80$ with paired-bootstrap upper 95% bound $<1.00$.
- D5: pooled over-cell proposed/frozen-deepest failure-penalized work ratio $\leq0.80$ with paired-bootstrap upper 95% bound $<1.00$.

## Verdicts

- all gates pass: `GRAPH_MATCHED_ROUTE_DEV_GO_CONFIRMATION`;
- any effect gate fails: `GRAPH_MATCHED_ROUTE_DEV_NO_GO`;
- implementation/protocol failure: `GRAPH_MATCHED_ROUTE_DEV_PROTOCOL_FAIL`.

A GO authorizes only a new untouched symbolic graph confirmation. It does not authorize Qwen or a cross-substrate headline.
