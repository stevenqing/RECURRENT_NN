# Recurrent Parallel Agents — Real-Code Benchmark v1

- Frozen date: 2026-07-12
- Status: frozen before any model outcome
- Primary benchmark: `ByteDance-Seed/Multi-SWE-bench-flash`
- Dataset revision: `b0485dbebaf8a1317ebf140e80e6fc6c02d3502b`
- Official harness revision: `24f493f8a103e72312ded4f6b9c89f081d69cb09`

## Decision

The primary real-agent application is parallel repository repair across dependency-connected files, with recurrent integration feedback. Multi-SWE-bench Flash is the primary substrate because it combines real GitHub pull requests, official executable tests and Docker environments, multilingual repositories, and enough genuinely cross-file tasks for recurrent coordination.

Measured before freezing this protocol:

| Candidate | Relevant property | Decision |
|---|---|---|
| SWE-bench Verified | 500 human-validated Python tasks, but 429/500 gold fixes touch only one file; only 22 touch at least three files | calibration/control only |
| Multi-SWE-bench Flash | 300 real tasks, 24 repositories, 7 languages; 165 touch at least two files, 94 at least three, 68 at least four | primary |
| SWE-bench Pro Public | 731 public tasks, reference fixes average 4.1 files and 107.4 lines; substantially harder | later external-validity track |
| CodeClash | intrinsically recurrent over 15 edit/competition rounds, but has relative arena scores rather than exact module-correction labels | later recurrence stress test |

## Structural pool

A task enters the structural candidate pool only if:

- the gold fix changes 3–6 non-test code files;
- those code files span at least two directories;
- the fix changes at most 300 added/deleted lines;
- at least one official F2P, S2P, or N2P target test exists;
- the test-patched base has at least one failure;
- the official full fix has zero failures.

Gold patches are used only for offline selection, component construction, and labels. Gold paths, patch text, and labels must not enter model prompts.

The 3–6 component range caps exact binary component-state enumeration at $2^6=64$ official test runs per task.

## Three claim-separated tracks

### Track A — real-state correction anchor

Construct partial integration states by applying old/gold file components in all binary combinations. For component $i$ in state $x$, define the exact correction label

$$
y_i(x)=\mathbf{1}\left[\max_{z:z_i=x_i}V(z)=0\right],
$$

where $V(z)=1$ only when the official target and regression tests pass. Thus a component needs correction only when its current value cannot occur in any passing completion within the frozen component space.

The judge sees only the issue, current local code/diff, bounded neighbor interface changes, and bounded test diagnostics. This track measures correction-signal quality, not autonomous coding ability.

### Track B — recurrent integration mechanism

Use the frozen exact component space as the repair operator. Agents update in parallel from immutable round snapshots, commit at a barrier, and receive one-round-delayed boundary/test messages. This isolates recurrent coordination and rework scheduling. Any use of a hidden gold component is reported as oracle repair and is not an end-to-end coding result.

### Track C — end-to-end coding agents

Replace the oracle repair operator with frozen coding agents. No gold localization, path, patch, or label is visible. This is the only track eligible for a real autonomous coding-agent claim.

## Correlated verification

Repeated identical temperature-zero model calls are not independent confirmations. Real verification hits must use distinct evidence channels or changed evidence, such as compiler output, type checker output, disjoint test shards, neighbor-agent review, or a later recurrent state.

Let $q_j$ be the measured probability that a live component survives $j$ erroneous correction signals, and let $H_k$ be the measured episode-level false-reopen hazard. The real-code allocation objective is

$$
C(k)=c_q\left[L_{live}\sum_{j=0}^{k-1}q_j+L_{dead}k\right]+C_{fail}H_k.
$$

The previous $\eta^k$ objective is a special independent-signal case, not an assumption permitted in the real benchmark.

## Required controls

- one frozen monolithic coding agent;
- one-shot parallel agents with no recurrence;
- recurrent one-hit reopen;
- recurrent fixed two-hit reopen;
- recurrent empirical cost-sensitive reopen;
- commit/no-reopen control.

Report official resolve rate, target and regression tests, total input/output tokens, model calls, module rewrites, false reopens, rounds, serial work, critical-path wall time, and failure-tail cost. Token/model-call budgets must be matched; wall time is reported separately.

## Stage gates

- B0 structural: pinned 300-row source, exact language counts, unique IDs, deterministic patch hashes, no gold content exported.
- B1 operational: official Docker image runs; base fails and full fix passes; partial patches apply; dependency graph is connected with diameter at least two; per-state test cap is feasible.
- B2 label: exact component enumeration replays deterministically and yields both live and correction-required states.
- B3 signal: frozen real judge meets preregistered parse, false-positive, false-negative, calibration, and correlated-survival gates.
- B4 mechanism: recurrent cost-sensitive policy improves resolve/tail cost over one-hit, fixed-two, one-shot, and no-reopen controls under matched budgets.
- B5 end-to-end: Track C passes on a model-outcome-hidden confirmation pool.

No B3–B5 claim is authorized by structural preflight alone.
