# Static Tail-Risk Prediction Preflight v1

- Frozen date: 2026-07-11
- Stage: development-only kill gate on already exposed data
- Parent contract: [Tail-Risk-Aware Multi-Agent Factorization](multiagent_tail_risk_factorization_contract_v1.md)
- Headline eligibility: **false**
- GPU/LLM use: none

## Question

Before collecting online traces or running another model, test the cheapest hypothesis:

> Are unsafe factorized trajectories predictable from deployment-visible static graph/partition/order features alone, across held-out generator groups?

A failure means the static selector line stops. Under this preflight's deliberately strict routing rule, online-trace and Qwen work are not authorized from the current substrate.

## Frozen data

Only already exposed pools are used:

1. 64-instance development manifest and structural results;
2. 200-instance failed-confirmation manifest and raw results.

Total: 264 instances.

Label:

- `unsafe=1` iff `independent_local_cbj` / `independent_local_cbj_v1_exact` did not solve under the frozen 20,000 activation cap;
- otherwise `unsafe=0`.

Failure-penalized work is `aggregate_work` for solved factorized rows and `max(aggregate_work, 20000)` for unsafe rows.

## Forbidden features

The extractor must fail closed if any forbidden field enters the matrix:

- `cell`, `capacity`, `coupling`, `b`;
- seed, batch/cell id, source index/kind, instance id;
- target depth or target-met fields;
- unlimited-reference steps, recoveries, retractions, conflict depth, or recovery distances;
- planted/reference solution information;
- any proposed/control outcome, work, status, trace, request, NACK, or post-horizon field.

Generator pool and seed are used only to define groups, never as features.

## Permitted static feature families

All are recomputed from immutable task data available before search:

1. total/cross/within degree distribution summaries;
2. boundary-vertex fraction and per-partition boundary concentration;
3. sorted intra-partition and inter-partition edge-count profiles;
4. normalized edge-span summaries under the supplied variable order;
5. boundary-position summaries and early-boundary fraction;
6. partition-switch and run-length summaries in the order;
7. prefix cutwidth and cross-cutwidth summaries;
8. graph degeneracy, triangle count, wedge count, and transitivity;
9. partition load-imbalance summaries;
10. `n_vertices`, `k`, partition count, and edge density recomputed from the graph.

Feature names and order are written to the output artifact and must be identical in every fold.

## Frozen grouped cross-validation

Group key:

- `development::<seed>` for the 64 pool;
- `confirmation::<seed>` for the 200 pool.

Fold:

$$
fold=\operatorname{uint32}(\operatorname{SHA256}(group)[:4])\bmod5.
$$

No group may appear in both train and test. Fold assignment is not optimized using labels.

## Frozen model

- standardized L2 logistic regression;
- preprocessing mean/std fitted on training fold only;
- IRLS/Newton optimizer, at most 100 iterations;
- L2 coefficient `1.0`, excluding intercept;
- probability clipping only for numerical stability;
- no hyperparameter search, feature selection, ensembling, or outcome-driven model choice.

The prevalence baseline probability is fitted on each training fold.

## Primary D1 gate

All must pass on concatenated out-of-fold predictions:

1. unsafe AUROC ≥ 0.80;
2. Brier score strictly below the fold-specific prevalence baseline;
3. 10-bin equal-width expected calibration error ≤ 0.05;
4. every fold contains both labels and all 23 generator groups are held out exactly once.

Status:

- `STATIC_RISK_SIGNAL_PASS` if all pass;
- `STATIC_RISK_SIGNAL_FAIL` otherwise.

## Frozen selector readout

Within each training fold, choose a probability threshold that minimizes fully charged mean work subject to training solve being no more than 0.05 below `monolith_MR`. Candidate thresholds are the training predictions plus endpoints.

Apply that threshold once to the held-out fold:

- predicted unsafe → run `monolith_MR`;
- predicted safe → run factorized CBJ;
- no probe cost is charged because this is a static selector.

Secondary D2 readout passes only if out-of-fold aggregate:

1. solve is within 0.05 of always-monolith;
2. mean penalized work is ≤0.90× always-monolith;
3. work is lower than a random selector with the same fallback rate;
4. selector uses no more than `MR=32` recovery memory at a time.

D2 cannot rescue a failed D1.

## Honesty boundary

This is development model selection on exposed data. Even a PASS authorizes only a separately frozen online/static selector development stage; it establishes no out-of-sample research claim and no Qwen contribution.
