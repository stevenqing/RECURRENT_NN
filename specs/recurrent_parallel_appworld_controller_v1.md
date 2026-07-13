# AppWorld A2 — Recurrent Controller Integrity v1

- Frozen date: 2026-07-12
- Status: frozen before controller outcomes and model outcomes
- Prerequisite: `RPD_APPWORLD_A1_PREFLIGHT_PASS`
- Scope: no-LLM controller semantics only

## Controller semantics

For each round $t$:

1. Save a real AppWorld checkpoint and construct one immutable snapshot.
2. All specialist proposal functions receive exactly that snapshot and run concurrently.
3. No environment call occurs until every specialist reaches the barrier.
4. Commit all read-only proposals first against the pre-write state.
5. Commit write proposals serially in deterministic `(agent_id, proposal_id)` order.
6. Proposal results become messages created at $t$ and are visible only in $t+1$.
7. On any commit failure, restore the round-start checkpoint.

Parallelism is in specialist reasoning/proposal generation. AppWorld state access is deterministically ordered because concurrent writes would introduce an uncontrolled race.

## Generic core audit

A deterministic in-memory adapter must verify:

- snapshot/message immutability;
- concurrent proposal entry for every agent;
- zero commit before the barrier;
- reads before writes;
- maximum concurrent writes exactly one;
- message age exactly one and no same-round message read;
- failed-round rollback;
- byte-identical normalized replay.

## Real AppWorld smoke

Select six train episodes from the A1 adjudication pool without reading instructions:

- one variation from each of the two available three-app task types;
- four deterministic two-app task types;
- lowest selection hash within each category/type.

Protected required-app names may be used only inside this no-LLM smoke to issue read-only API-document queries. They are never exported.

For every selected episode:

- round 0: one app specialist per required app proposes an API-document read;
- round 1: a coordinator reads current task status, then serially writes `status=fail`;
- round 2: specialists observe only round-1 messages and read the changed task status;
- restore the initial checkpoint;
- rerun the same schedule;
- compare normalized transcript, active-state, checkpoint-state, and official evaluator hashes.

The smoke intentionally does not solve tasks. Official solutions and API-call traces are not executed. Test splits remain unread.

## Gates

- C0 prerequisite and execution locks pass.
- C1 immutable snapshots and concurrent proposals pass.
- C2 barrier, read-before-write, deterministic serial write semantics pass.
- C3 messages are visible exactly one round later; no same-round cross-agent reads.
- C4 failure rollback and normalized fake-adapter replay pass.
- C5 all six real AppWorld episodes restore initial state and replay identically.
- C6 protected app names, responses, instructions, evaluator content, and ground truth are absent from exported rows; no test content, model, GPU, or Docker.

All gates yield `RPD_APPWORLD_A2_CONTROLLER_PASS`; otherwise `RPD_APPWORLD_A2_CONTROLLER_FAIL` or `RPD_APPWORLD_A2_PROTOCOL_FAIL` for C0/C6 integrity failures. A pass authorizes A3 signal-state design only. It is not evidence that multi-agent reasoning improves task completion.
