# Recurrent Parallel Deliberation Fixed-Budget Width Sweep v1

- Frozen date: 2026-07-12
- Status: frozen before width-sweep outcomes
- Prerequisite: `RPD_MESSAGE_RECURRENCE_ONLY`
- Source pool: 32 exposed SPEC v7-RPD development instances
- Evidence tier: symbolic spatial–temporal development; not headline eligible

## 1. Fixed primitive budget

The graph contains 17 base partitions. These base partitions are grouped into execution agents:

$$
M\in\{1,2,4,8,17\}.
$$

Each execution-agent call updates exactly one owned base partition. An agent cycles deterministically through its owned partitions. Therefore total primitive local-cell updates equal total agent calls.

Budget caps:

$$
B\in\{136,272\},
$$

with:

$$
T=B/M.
$$

All selected widths exactly divide both budgets.

## 2. Group construction

Root the 17-node partition tree at node 0 and take its frozen breadth-first order. Split that order into $M$ contiguous groups with sizes differing by at most one.

Report:

- group sizes;
- variables per execution agent;
- cross-agent partition edges;
- induced execution-agent graph diameter;
- internal versus messaged dependency edges.

## 3. Update semantics

Every round uses an immutable snapshot.

For each execution agent:

1. choose one owned base partition by round-robin cursor;
2. if its parent base partition is in the same execution agent, read the parent's round-start local state;
3. otherwise use the one-round-delayed parent message;
4. apply the frozen P0 candidate update rule;
5. commit all $M$ selected proposals together at the barrier;
6. generate cross-agent boundary messages for the next round.

There are no same-round cross-agent reads. Internal same-agent reads use only the round-start snapshot.

## 4. Primary arms

For every $(B,M)$:

- `fixed_budget_recurrent`: correct delayed messages and persistent local candidate state.

Context controls are derived from the same run:

- $M=1$: maximally centralized recurrent depth;
- $M=17$: maximally spatial, recurrence-shallow endpoint;
- $1<M<17$: interior width/depth allocations.

P0 no-message/shuffled-message controls remain the communication-necessity evidence and are not rerun as primary width arms.

## 5. Accounting

For every row report:

- budget cap $B$;
- width $M$;
- temporal depth cap $T$;
- actual rounds and agent calls;
- primitive base-partition updates;
- solve and final cross conflicts;
- idealized parallel critical path;
- sequential execution path;
- state changes and messages;
- group/context sizes;
- induced agent-graph diameter.

No FLOP, wall-clock, or GPU claim is made from symbolic calls.

## 6. Gates

### W0 — accounting and semantics

- deterministic replay on at least ten rows;
- $M T=B$ exactly for every configured arm;
- every agent call updates at most one base partition;
- same-round cross-agent reads = 0;
- message age = 1;
- official verification and no planted access pass.

### W1 — interior Pareto point

At $B=136$, at least one $M\in\{2,4,8\}$ must:

- have solve no worse than the better endpoint by more than 0.05;
- use at most half the $M=1$ idealized critical path;
- lie on the solve/critical-path Pareto frontier.

### W2 — shallow-width failure or cost

At $B=136$, either:

- $M=17$ solve is at least 0.10 below the best interior point; or
- $M=17$ requires a longer realized recurrent path than the best interior point after early stopping.

This tests recurrence starvation at excessive width.

### W3 — budget scaling

From $B=136$ to $B=272$:

- solve is nondecreasing for every width;
- any failed endpoint can recover only through added temporal depth, not extra per-call local work;
- the Pareto frontier is reported without selecting a single winner post hoc.

### W4 — resource transparency

All group sizes, context variables, cross-agent edges, actual calls, primitive updates, and both critical paths are present and internally conserved.

## 7. Verdicts

- W0–W4 pass: `RPD_FIXED_B_INTERIOR_OPTIMUM_CANDIDATE`;
- W0/W1/W3/W4 pass but W2 fails: `RPD_FIXED_B_PARETO_NO_WIDTH_FAILURE`;
- W0 passes but W1 fails: `RPD_FIXED_B_NO_INTERIOR_VALUE`;
- W0 fails: `RPD_FIXED_B_ACCOUNTING_FAIL`.

No verdict authorizes Qwen or a wall-clock claim. A positive result authorizes implementation of the same width sweep with a lightweight learned recurrent cell before real GPU timing.
