# Graph-Color Matched-Window Route Confirmation v1

- Frozen date: 2026-07-12
- Timing: after `GRAPH_MATCHED_ROUTE_DEV_GO_CONFIRMATION`, before new manifest generation and outcomes
- Study role: independent cross-substrate confirmation of capacity-valid-before-priority routing
- Evidence tier: symbolic mechanism confirmation; no algorithm-novelty or LLM claim

## New manifest

- same fixed-density four-block graph-color generator family as the prior structural confirmation;
- $M=4$, 12 vertices/block, 48 vertices, $k=4$, exactly 96 edges;
- low/high boundary settings 2/8;
- under/over target conflict depths 4/12;
- split seed 206000;
- 50 instances per cell, 200 total;
- structural reference selection only, no bounded-arm outcomes;
- zero instance-ID and canonical graph-hash overlap with the prior 64-instance development and 200-instance confirmation pools.

## Resources

- $R=8$, $MR=32$;
- activation/failure cap 20,000;
- request channel cap 16;
- route seed 20260711;
- no GPU, LLM, or oracle fallback;
- official graph-color validation.

## Arms

1. `independent_local_deepest_window_valid_graph`;
2. `independent_local_random_valid`;
3. `independent_local_cbj_v1_exact`;
4. `independent_local_no_cross`;
5. `monolith_MR`.

## Frozen gates

- C0 execution integrity: 200 instances, 1,000 rows, all hashes/cardinality/shadow/protocol/scoring checks pass.
- C1 pooled over route solve: proposed minus random $\geq0.10$ and one-sided exact McNemar $p\leq0.05$.
- C2 pooled over route work: proposed/random penalized ratio $\leq0.80$ with bootstrap upper 95% $<1.00$.
- C3 cell stability: proposed minus random solve $\geq-0.05$ in both over cells and proposed solve $\geq0.95$ in each.
- C4 operational safety: proposed mean NACKs $\leq1.0$, window rejections $\leq2.0$, zero out-of-window executions, matched resources.
- C5 repair mechanism: proposed/frozen-deepest penalized ratio $\leq0.80$ with upper 95% $<1.00$.
- C6 equal-memory solve NI on pooled over cells: observed proposed-minus-monolith $\geq-0.05$ and one-sided CP upper monolith-only discordance $\leq0.05$; each over-cell difference must be $\geq-0.10$.
- C7 equal-memory expected work: proposed/monolith penalized ratio $\leq0.80$ with upper 95% $<1.00$.

Paired bootstrap uses 100,000 replicates. Failure cost is 20,000.

## Verdicts

- all C0–C7: `GRAPH_MATCHED_ROUTE_STRONG_CONFIRMATION`;
- C0–C5 pass but C6/C7 fails: `GRAPH_MATCHED_ROUTE_CONFIRMATION_ONLY`;
- route/repair gate failure: `GRAPH_MATCHED_ROUTE_CONFIRMATION_NO_GO`;
- integrity failure: `GRAPH_MATCHED_ROUTE_PROTOCOL_FAIL`.

A route confirmation combined with the independent SAT result supports a cross-substrate capacity-valid tail-control mechanism. It does not establish algorithm novelty or authorize Qwen.
