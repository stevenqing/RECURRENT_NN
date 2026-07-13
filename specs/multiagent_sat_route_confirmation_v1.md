# Community-SAT Route Identifiability Confirmation v1

- Frozen date: 2026-07-12
- Study role: independent symbolic prerequisite for any SAT Qwen-routing development
- Evidence tier: confirmatory for a narrow route-identifiability claim; not an LLM or algorithm-novelty claim
- Parent result: [Community SAT closeout](../results/multiagent_community_sat_replication/CLOSEOUT.md)

## 1. Research question

In the preregistered high-coupling, over-local-fit community-3-SAT regime, does deterministic deepest conflict routing materially outperform a matched random-valid rollback target under the same owner-local memory, scheduler, communication channel, and activation cap?

The exposed second-substrate study produced a secondary signal (solve 0.68 versus 0.50, 16 versus 7 one-sided discordances). This new study uses an untouched structural manifest and promotes route identifiability to the sole primary question.

## 2. Contribution boundary

A positive result supports only:

> Rollback-route choice is an identifiable control variable in high-coupling owner-local SAT search, making a bounded route-policy study scientifically testable.

It does not establish:

- Qwen or LLM routing quality;
- multi-agent superiority over an equal-memory monolith;
- a novel CBJ, portfolio, or distributed-CSP algorithm;
- a result outside the frozen community-SAT regime.

## 3. Frozen substrate and selection

- generator: planted fixed-density community 3-SAT;
- variables: 48 in four communities of 12;
- clauses: exactly 192 clauses of size 3;
- high coupling: exactly 77 cross-community clauses;
- target stratum: `over_local_fit`, requiring global reference rollback distance $>8$ and target-owner local distance $\leq8$;
- split: `route_confirmation`;
- base seed: 410000;
- candidate indices: ascending from zero;
- maximum candidates: 20,000;
- accepted instances: first 200 structurally eligible candidates;
- evaluated arm outcomes are forbidden during selection;
- planted assignments are removed before execution;
- zero instance-ID and clause-hash overlap is required against both the 64-instance development pool and prior 200-instance independent pool.

## 4. Frozen resources

- agents: $M=4$;
- local register: $R=8$;
- equal total recovery memory: $MR=32$;
- activation/failure cap: 20,000;
- request channel cap: 16;
- route seed: 20260712;
- values: 0 then 1;
- fixed variable order;
- no unit propagation;
- full-clause official verification;
- no oracle/model fallback.

## 5. Arms

All arms use the frozen solver implementation.

1. `independent_local_cbj_sat` — queued deepest valid-by-priority target;
2. `independent_local_random_valid_sat` — queued uniformly random target among currently window-valid candidates with frozen per-instance RNG;
3. `independent_local_no_cross_sat` — queued route restricted to the source owner;
4. `factorized_central_cbj_sat` — same-order deepest route with immediate target callback;
5. `monolith_MR_sat` — equal-total-memory context control.

The primary contrast is arm 1 versus arm 2. All others are secondary mechanism/context controls and cannot rescue a failed primary gate.

## 6. Primary estimands

For deepest versus random-valid on the same 200 instances:

1. paired solve-rate difference;
2. one-sided exact McNemar probability for deepest superiority;
3. ratio of mean failure-penalized aggregate work;
4. paired 100,000-replicate bootstrap 95% interval for that work ratio.

Failures are charged 20,000 work. Raw stopped work cannot be used for the primary work comparison.

## 7. Frozen gates

### P0 — execution integrity

- 200 unique instances and 1,000 rows;
- all manifest, lock-hash, protocol, request-conservation, memory-window, and official-verification checks pass.

### P1 — practically identifiable solve effect

$$
\widehat p_{deepest}-\widehat p_{random}\geq0.10.
$$

### P2 — paired statistical direction

The one-sided exact McNemar probability for deepest superiority is $\leq0.05$.

### P3 — expected-work direction

- failure-penalized deepest/random ratio $\leq0.90$; and
- paired-bootstrap upper 95% bound $<1.00$.

### Authorization verdict

`SAT_ROUTE_CONFIRMATION_GO_QWEN_DEV` requires P0–P3 all pass. Otherwise the verdict is `SAT_ROUTE_CONFIRMATION_NO_GO`, and no Qwen route experiment is launched from this premise.

## 8. Conditional Qwen boundary

If and only if the authorization verdict is GO, the next stage may use GPUs 2 and 3 for a development-only frozen-Qwen route gate. That later stage must:

- use bounded deployment-visible SAT state only;
- exclude planted assignments and future trajectory outcomes;
- compare Qwen against deepest, random-valid, and no-cross controls;
- fail closed on invalid output;
- charge calls and tokens;
- make no headline claim without another untouched end-to-end manifest.

## 9. Reporting

All outcomes, including a failed gate, are reported. A Markdown result is mandatory. No supporting secondary comparison may override P0–P3.
