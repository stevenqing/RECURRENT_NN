# Recurrent Parallel Deliberation P0 Contract v1

- Frozen date: 2026-07-12
- Status: frozen before recurrent-engine outcomes
- Role: symbolic synchronous-semantics and recurrence-necessity preflight
- Source pool: [SPEC v7-RPD development manifest](../results/recurrent_signal_phase_v7_preflight/instance_manifest.json)
- Headline eligible: No

## 1. Architecture

Each of the 17 graph partitions is one local agent. Every agent owns exactly four variables and the induced local constraints.

A recurrent round has strict Jacobi semantics:

1. freeze all local candidate states and incoming messages at round start;
2. every agent computes its proposal from that immutable snapshot;
3. no agent can read another agent's same-round proposal;
4. proposals commit together at a barrier;
5. boundary assignments become messages visible only in the next round;
6. official global verification occurs after the barrier.

All agents use the same deterministic update rule. State size is fixed: one local-coloring candidate index, one tie cursor, one parent-message cache, and bounded round counters.

## 2. Local candidate state

For each four-variable partition, enumerate all locally valid 3-color assignments. Candidate enumeration is lexicographic and independent of planted solutions.

The partition tree is rooted at partition 0. A non-root agent receives only its parent partition's boundary-color message. Given a parent message, it chooses a local candidate minimizing cross-edge conflicts with that parent. The update is stable:

- keep the current candidate if it is among the minima;
- otherwise choose the minimum candidate at the persistent tie cursor and advance the cursor.

The root keeps its initial candidate throughout P0. Child-to-parent residual repair is outside this semantics preflight.

## 3. Modes

1. `recurrent_parallel`: persistent candidate/tie state; one-round delayed correct messages.
2. `state_reset`: candidate and tie state reset before every round, while the same delayed messages are provided.
3. `shuffled_message`: persistent state, but parent-message recipients are permuted by a frozen deterministic permutation.
4. `no_message`: persistent local state with no cross-partition messages.
5. `sequential_sharded`: same local update rule and root orientation, but agents are processed root-to-leaf within a round and descendants immediately see same-round parent updates. This is a Gauss–Seidel critical-path control, not a parallel arm.

`T=1` for `recurrent_parallel` is the one-shot control.

## 4. Round budgets

$$
T\in\{1,2,4,8,16,32\}.
$$

All 32 exposed development instances are run in every mode and round budget. No result is headline eligible.

## 5. Accounting

Report separately:

- official solve;
- local and cross-edge conflicts;
- rounds executed;
- agent update calls;
- state changes;
- boundary messages generated/delivered;
- maximum message age;
- same-round cross-agent reads;
- idealized parallel critical path;
- sequential local-update critical path.

No wall-clock or GPU claim is permitted in P0.

## 6. Gates

### P0 — synchronous semantics

- deterministic replay on at least eight fixed episodes;
- same-round cross-agent reads = 0 for all parallel modes;
- every delivered message age = 1 round;
- all local candidates satisfy local edges;
- every solved output passes official verification;
- no planted assignment is read.

### P1 — recurrent communication depth

For pooled $\delta\ge4$ instances:

- `recurrent_parallel(T=32)` solve exceeds one-shot `T=1` by at least 0.15;
- solve is nondecreasing from $T=1$ to $T=32$ in pooled summaries;
- at least one larger-diameter group requires more rounds than a smaller-diameter group.

### P2 — message necessity

At $T=32$, recurrent solve exceeds both `no_message` and `shuffled_message` by at least 0.10 on pooled $\delta\ge4$ instances.

### P3 — state persistence

At $T=32$, recurrent solve exceeds `state_reset` by at least 0.10 on pooled $\delta\ge4$ instances.

If P0–P2 pass but P3 fails, the allowed verdict is `RPD_MESSAGE_RECURRENCE_ONLY`: recurrent communication depth matters, but persistent local latent state is not identified.

### P4 — critical-path control

`sequential_sharded` must use the same candidate rule and final official scorer. Report its solve and sequential local-update critical path. P0 does not require parallel to beat sequential solve; it requires transparent separation of critical path and aggregate updates.

## 7. Verdicts

- P0–P4 pass: `RPD_P0_FULL_RECURRENCE_GO`;
- P0–P2 and P4 pass, P3 fails: `RPD_MESSAGE_RECURRENCE_ONLY`;
- P0 passes but P1/P2 fails: `RPD_P0_NO_RECURRENCE_SIGNAL`;
- P0 fails: `RPD_P0_SEMANTICS_FAIL`.

No verdict authorizes Qwen. The next fixed-$B=MT$ width sweep is authorized only by a non-failing P1/P2 result.
