# Recurrent Parallel Specialists on AppWorld v1

- Frozen date: 2026-07-12
- Status: environment choice frozen before installation outcomes and model outcomes
- Primary online environment: AppWorld
- Package: `appworld==0.1.3.post1`
- Wheel SHA256: `db77f8003982502383a50fa2974983894bd1c54f64e2fd3f7e1540d5edd037eb`
- Runtime: isolated uv environment with CPython 3.11; no Docker

## Why AppWorld

AppWorld is the intermediate real-agent environment between symbolic graph/SAT and Dockerized repository repair. It provides nine day-to-day apps, 457 APIs, stateful online interaction, task-specific database state, checkpoints, API/runtime feedback, and database-state evaluation. It runs locally in one Python process without Docker or an external service.

The real application is a team of app specialists executing a cross-app workflow, such as finding information in Gmail, reconciling it with a calendar or payment state, and committing an action in another app.

| Alternative | Decision |
|---|---|
| AppWorld | Primary: multi-app state, exact evaluator, checkpointing, local/no-Docker execution |
| BIRD Mini-Interact | Secondary: clean SQLite interaction but narrower database-only specialization |
| tau-bench/tau3 | Secondary: realistic policy/tool interaction, but user-simulator variance and less natural spatial partitioning |
| Overcooked-AI | Mechanism control only: native simultaneous agents, but weak correspondence to LLM tool specialists |
| Multi-SWE-bench | Deferred hard external-validity track requiring Docker |

## Agent architecture

- one specialist per task-relevant app or app cluster;
- every recurrent round begins from an immutable world/message snapshot;
- specialists may inspect documentation and propose bounded read/write tool calls in parallel;
- a barrier merges proposals;
- state-mutating calls are serialized by a deterministic commit layer;
- call results and bounded cross-app entity messages become visible in the next round;
- model budget is fixed as $B=M\times T$ calls, with token totals also reported.

Parallelism applies to reasoning and read-only discovery. Simultaneous writes to the same AppWorld state are forbidden because they would make ordering an uncontrolled confound.

## Safety and leakage

The first implementation uses schema-constrained function calls, not arbitrary model-generated Python. AppWorld's unsafe-syntax and unsafe-execution guards remain enabled. Test evaluators, task ground truth, validation solutions, and hidden state assertions are never exposed during a trajectory. Train is for demonstrations, dev for protocol development, and test_normal/test_challenge only for frozen aggregate evaluation.

## Research hypothesis

Under matched model-call and token budgets, recurrent app specialists should outperform one-shot specialists when tasks contain cross-app dependencies. The gain should concentrate in dependency depth rather than raw number of agents. Cost-sensitive write verification should reduce unnecessary replanning and collateral database changes relative to one-hit reopening.

Repeated identical temperature-zero calls are not independent evidence. Confirmation must come from distinct app state, API responses, policy checks, or a later recurrent round.

## Controls

- frozen monolithic function-calling agent;
- one-shot parallel specialists with one merge;
- recurrent specialists with one-hit replanning;
- recurrent specialists with fixed two-evidence replanning;
- recurrent specialists with empirical cost-sensitive replanning;
- no-replan/commit control.

## Metrics

- official task goal completion and scenario goal completion;
- evaluator assertions passed and collateral-state failures;
- total and per-app API calls;
- invalid/failed API calls;
- recurrent rounds and specialist replans;
- model calls, input/output tokens, serial work, and critical-path wall time;
- false reopen, missed correction, and empirical correlated-evidence survival.

## Gates

- A0 installation: pinned package installs in an isolated uv environment; official tests and train/dev task verification pass without Docker.
- A1 census: train/dev metadata yields a deterministic multi-app candidate manifest; no evaluator or solution content is exported.
- A2 mechanism: a no-LLM controller verifies snapshot, barrier, one-round message delay, write serialization, replay, and official evaluator integrity.
- A3 signal: a frozen Qwen judge is measured on blinded dev correction states.
- A4 end-to-end development: recurrent specialists beat matched controls on dev without test inspection.
- A5 confirmation: one frozen run on test_normal/test_challenge aggregate metrics only.

Only A5 can support an AppWorld end-to-end claim. Multi-SWE remains a separate later external-validity claim.
