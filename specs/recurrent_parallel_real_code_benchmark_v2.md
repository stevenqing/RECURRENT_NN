# Recurrent Parallel Agents — Real-Code Benchmark v2

- Frozen date: 2026-07-12
- Status: frozen before any model outcome
- Primary benchmark: `ByteDance-Seed/Multi-SWE-bench-flash`
- Dataset revision: `b0485dbebaf8a1317ebf140e80e6fc6c02d3502b`
- Official harness revision: `24f493f8a103e72312ded4f6b9c89f081d69cb09`
- Supersedes: v1 structural test semantics only

## Transparent v1 failure

The v1 preflight required aggregate `test_patch_result.failed_count>0` and `fix_patch_result.failed_count=0`. It retained only 16 tasks in three languages and correctly returned `RPD_REAL_CODE_BENCHMARK_STRUCTURAL_PREFLIGHT_FAIL`.

Field-level diagnosis, before any model call, showed that aggregate counts include unrelated pre-existing repository failures and therefore do not implement Multi-SWE's official scoring semantics. v2 changes only this field interpretation. It does not relax cross-file structure, component count, patch-size, or gold-blinding rules.

## Primary benchmark decision

Multi-SWE-bench Flash remains the primary substrate: 300 real GitHub issue-resolution tasks, 24 repositories, seven languages, official Docker evaluation, and substantially more cross-file fixes than SWE-bench Verified. SWE-bench Pro Public remains a later high-difficulty external-validity track; CodeClash remains a later open-ended recurrence track.

## Structural pool

A task enters the candidate pool only if:

- the gold fix changes 3–6 non-test code files;
- those files span at least two directories;
- the fix changes at most 300 added/deleted lines;
- at least one official target test exists;
- every F2P test has `test=FAIL, fix=PASS`;
- every S2P test has `test=SKIP, fix=PASS`;
- every N2P test has `test=NONE, fix=PASS`;
- every P2P test has `test=PASS, fix=PASS`.

The `run` field is recorded but is not constrained because new tests may not exist before `test.patch`, and repositories may contain pre-existing failures. Aggregate failed counts are recorded diagnostically but are not used for eligibility.

Gold patch text and changed paths are never exported. The 3–6 component range caps exact binary component-state enumeration at $2^6=64$ official target-test runs per task.

## Claim-separated tracks

1. **Track A — exact real-state correction anchor.** Exhaust old/gold component combinations. For component $i$ in state $x$,

   $$y_i(x)=\mathbf{1}\left[\max_{z:z_i=x_i}V(z)=0\right].$$

   This tests whether a frozen judge can detect a non-extendable local component. It is not autonomous coding.

2. **Track B — recurrent integration mechanism.** Parallel Jacobi updates, barrier commit, and one-round-delayed diagnostics use an oracle component repair operator. It tests coordination and rework scheduling, not code generation.

3. **Track C — end-to-end coding agents.** Frozen coding agents generate repairs with no gold path, patch, label, or fallback. Only this track supports an autonomous coding-agent claim.

## Correlated verification

Identical temperature-zero calls are not independent. Verification hits must use distinct evidence or changed recurrent states. Estimate empirical survival $q_j$ and episode false-reopen hazard $H_k$:

$$
C(k)=c_q\left[L_{live}\sum_{j=0}^{k-1}q_j+L_{dead}k\right]+C_{fail}H_k.
$$

The symbolic $\eta^k$ rule is only the independent-signal special case.

## Required controls and metrics

Controls: monolithic agent, one-shot parallel, recurrent one-hit, recurrent fixed-two, recurrent empirical-cost, and no-reopen. Match total model calls and input/output tokens. Separately report official resolve rate, F2P/P2P results, rounds, rewrites, false reopens, serial work, critical-path wall time, and failure-tail cost.

## Gates

- B0 structural: pinned 300 rows, exact language counts, deterministic hashes, at least 30 eligible tasks from at least four languages, no gold content exported.
- B1 operational: official Docker replay, component patches apply, target transitions replay, dependency graph connected with diameter at least two, runtime feasible.
- B2 label: exhaustive component states deterministically yield both live and correction-required labels.
- B3 signal: frozen real judge passes preregistered parse/error/calibration/correlated-survival gates.
- B4 mechanism: empirical-cost recurrence improves resolve or failure-tail cost under matched budgets.
- B5 end-to-end: Track C passes on a model-outcome-hidden confirmation pool.

Structural B0 alone authorizes no Qwen or headline claim.
