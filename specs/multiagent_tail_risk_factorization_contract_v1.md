# Tail-Risk-Aware Multi-Agent Factorization — Research Contract v1

> **Static kill-gate update (2026-07-11):** Deployment-visible static graph/partition features failed grouped prediction (`AUROC=0.602`, `ECE=0.074`). The static selector retained solve but cost `1.826×` always-monolith work because it fell back on 83% of instances. Under the frozen routing decision, online-trace and Qwen risk work are not authorized on this substrate. See [static risk closeout](../results/multiagent_static_risk_preflight/CLOSEOUT.md).

- Date: 2026-07-11
- Status: research candidate; development not yet executed
- Trigger: [failed independent structural confirmation](../results/multiagent_structural_confirmatory/RESULTS.md)
- Diagnostic: [tail-risk closeout](../results/multiagent_structural_confirmatory/DIAGNOSTIC.md)
- Literature boundary: [contribution audit](../results/multiagent_structural_confirmatory/LITERATURE_AUDIT.md)
- First-principles gain map: [Multi-Agent 的真实提升来自哪里？](multiagent_first_principles_gain_map_v2.md)

## 1. Research question

Independent factorization produced large frequent-case savings but failed the expected-resource objective because rare activation-cap failures dominated mean work.

The next scientific question is:

> Can a predeclared, leakage-free risk model detect an unsafe factorized trajectory early enough to switch to an equal-memory monolith, preserving solve non-inferiority while reducing expected aggregate work?

This is not a claim that algorithm selection, portfolios, fallback, distributed CSP, or dynamic backtracking are novel. A contribution is eligible only as a **bounded-memory multi-agent tail-risk law plus independently validated risk-control architecture**.

## 2. Break-even law

Let:

- $W_s$ be mean factorized work conditional on success;
- $W_m$ be mean monolith work;
- $B$ be the failure cost/cap;
- $q$ be factorized failure probability.

The unconditional factorized expected work is:

$$
E[W_f]=(1-q)W_s+qB.
$$

Factorization improves expected work only if:

$$
q<q^*=\frac{W_m-W_s}{B-W_s}.
$$

On the completed over-low confirmation:

- $W_s\approx354.3$;
- $W_m\approx1242.1$;
- $B=20{,}000$;
- $q^*\approx0.045$;
- observed $q=0.08$.

These values motivate the research question but are development inputs for the next stage, not future confirmatory evidence.

## 3. Data discipline

### Development only

The following are permanently development data for this new mechanism:

1. the original 64-instance structural pool;
2. the completed 200-instance failed-confirmation pool;
3. any replay/checkpoint traces collected from those instances.

### Future confirmation

A new manifest must be generated only after the risk policy, feature contract, horizon, thresholds, and code hashes are frozen. No future confirmatory instance may be selected by factorized/monolith outcome.

A general claim additionally requires a second decomposable substrate; a new graph-color pool alone supports only a graph-coloring claim.

## 4. Permitted predictor inputs

Static features must be available before solving and may include:

- graph and partition sizes;
- within/cross-edge counts and separator statistics;
- degree/domain/order summaries;
- local imbalance and boundary concentration.

Online features must be measured by a frozen early horizon $h$ and may include:

- assignment progress;
- branch/retraction rates;
- request, NACK, and window-rejection rates;
- repeated-target and repeated-state counts;
- local-window occupancy;
- per-agent progress imbalance.

Forbidden features:

- unlimited-reference solve steps or recovery distances at deployment;
- final status or post-horizon events;
- monolith outcome/work for the evaluated instance;
- oracle route or planted solution;
- any feature computed from a future confirmatory arm outcome.

## 5. Arms

1. `always_monolith_MR`;
2. `always_factorized_cbj`;
3. `risk_aware_static`: choose before search from permitted static features;
4. `risk_aware_early_abort`: run factorized to horizon $h$, then continue or restart with monolith-MR;
5. `random_selector`: matched selection rate;
6. `budget_matched_restart`: factorized probe followed by unconditional monolith restart;
7. `oracle_selector`: development-only upper bound, never a primary method.

The risk-aware arms use at most one `MR=32` recovery memory substrate at a time. Aggregate work includes discarded factorized probe work plus all monolith fallback work.

## 6. Development gates

### D0 — Leakage and protocol audit

- all feature timestamps are no later than $h$;
- no forbidden feature is present;
- owner/window/request invariants remain valid;
- replay is deterministic;
- all memory and work are counted.

### D1 — Predictive signal

Using grouped cross-validation by generator batch/seed:

- unsafe-trajectory AUROC ≥ 0.80;
- Brier score improves over prevalence-only prediction;
- calibration error ≤ 0.05 after a transform fitted inside each training fold.

Failure of D1 ends the risk-aware line; no selector is taken to confirmation.

### D2 — Development Pareto

At a threshold chosen without test-fold outcomes, early-abort must:

- retain solve within 0.05 of monolith-MR;
- reduce cross-validated failure-penalized work by at least 10%;
- outperform random selector and unconditional restart at matched fallback rate.

### D3 — Stability

The same direction must hold across low/high coupling and at least two generator seed groups. A benefit driven by one batch is insufficient.

## 7. Future confirmatory gates

These thresholds must be frozen again with a powered sample size before generating the new pool.

1. **Solve non-inferiority:** risk-aware minus monolith solve ≥ -0.05 and conservative one-sided discordance bound ≤0.05.
2. **Expected-work advantage:** ratio of failure-penalized aggregate work ≤0.90 with paired-bootstrap upper 95% bound ≤0.90.
3. **Tail control:** observed unsafe completion rate and its one-sided bound lie below the precomputed $q^*$ for the frozen cost model.
4. **Selection value:** risk-aware beats random selector and unconditional restart under matched fallback/work accounting.
5. **No hidden resource gain:** total recovery memory ≤MR, and aggregate probe/fallback work is fully charged.
6. **Second substrate:** direction replicates before making a general multi-agent law claim.

## 8. LLM boundary

No Qwen experiment is authorized until the symbolic risk policy passes independent confirmation. If that occurs, Qwen may be evaluated only as a bounded risk/route signal against:

- symbolic risk model;
- random-valid route;
- deepest deterministic route;
- no-cross;
- no-LLM risk-aware policy.

Calls, tokens, aggregate work, and fallback cost must all be matched or reported as a Pareto frontier.

## 9. Contribution and kill rules

### Eligible contribution if all gates pass

> A calibrated tail-risk law predicts when bounded local factorization ceases to be an expected-resource improvement, and a leakage-free early risk policy preserves the frequent-case savings while maintaining equal-memory solve reliability.

### Kill rules

- D1 fails: no predictable safety boundary; stop.
- Work gain disappears after charging fallback: retain only the negative tail-risk result.
- Selector does not beat matched random/restart controls: remove architecture contribution.
- Second substrate fails: scope strictly to graph coloring.
- Qwen does not beat symbolic controls: remove LLM contribution.

The selector algorithm itself is not claimed novel without a separate full-text algorithm-selection and portfolio literature review.
