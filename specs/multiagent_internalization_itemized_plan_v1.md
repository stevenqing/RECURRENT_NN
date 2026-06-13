# Multi-Agent LLM Internalization Itemized Plan v1

## Objective

Turn the externalized graph-coloring result from Item095 into a staged internalization program. Externalization keeps CSP state, reversible register, conflict routing, and official scoring in Python while the frozen LLM emits bounded JSON decisions. Internalization means progressively removing those external supports until the model or model agents maintain bounded search state in token space.

No training item may claim internalization while the external scaffold still owns the register or controller.

## Itemized Execution

| item | stage | artifact target | pass gate | does not establish |
| --- | --- | --- | --- | --- |
| 096 | Plan and gates | This spec plus log item | Itemized route exists; each future stage has a measurable pass gate and caveat | No new traces or training |
| 097 | Single-agent trace schema and harvester | `results/internalization_traces/graph_color_single_agent_mregister_trace_smoke.{json,jsonl}` | Exports step-level branch/backtrack/final rows from solved R8 graph_color episodes; schema includes visible state, target action, before/after summaries, and SFT messages | No LLM training; oracle-scaffold teacher only |
| 098 | Multi-agent trace schema and trace pilot | Multi-agent team/monolith trace artifacts | Row-isolated team/monolith episodes export branch, local backtrack, cross-block conflict, message, rollback, and final rows | No internalized agents yet |
| 099 | Trace-to-SFT dataset builder | JSONL train/validation splits plus dataset card | Converts traces into stable chat-format examples with split hashes and leakage checks | No model update |
| 100 | Policy LoRA under external scaffold | LoRA smoke plus external-scaffold eval | LoRA improves parseable/valid/target-action accuracy and solves inside the external scaffold | Scaffold still owns register and state, so not internalized |
| 101 | Register-in-text eval harness | Closed-loop transcript evaluator | Frozen or LoRA model must maintain a bounded textual register; evaluator only parses transcript and official final answer | No training claim |
| 102 | Single-agent register internalization LoRA | LoRA checkpoint plus transcript eval | External register removed; model maintains bounded textual state and beats one-shot/two-stage baselines on held-out graph_color | Single-agent only |
| 103 | Multi-agent internalized dataset and controls | Homo/hetero/team/monolith dataset cards | Produces comparable train/eval splits for team, monolith-R, and monolith-KR controls | No capacity claim |
| 104 | Multi-agent internalized LoRA pilot | Homo vs hetero LoRA controls | Team agents maintain local bounded registers and communicate conflicts; compare to monolith-R/KR with official scoring | Pilot only unless n>=30 per K |
| 105 | Scale or fail-close | Full table or scoped negative | Either scale the successful internalized setting or record why internalization fails | Does not move goalposts |

## Trace Schema Requirements

Each step trace must include:

- `trace_schema_version`
- `episode_id`, `trace_id`, `step_index`
- `benchmark`, `source_index`, `R`, and later `K`/`agent_id` for multi-agent traces
- `teacher_source`: `oracle_scaffold`, `llm_scaffold`, or later `internalized_model`
- `visible_state`: only what the learner may see
- `target_action`: one of `branch`, `backtrack`, `message`, `rollback`, `final`, or `fail`
- `state_before_summary` and `state_after_summary`
- `training_messages`: chat-format prompt/target pairs for SFT
- `official_outcome` fields at final rows or episode summary level

## Gates

Trace gates:

- All JSONL rows parse.
- Action counts are nonzero for branch and backtrack on trace smoke.
- Bounded register view never exceeds declared `R`.
- Solved trace smoke has official score 1.0 for all selected episodes.

Policy LoRA gates:

- Parseable action rate >= frozen baseline.
- Valid action rate >= frozen baseline.
- Backtrack target accuracy improves over frozen baseline or solve rate improves under the external scaffold.

Register-internalization gates:

- External register removed from the execution loop.
- Transcript register length remains bounded.
- Rollback consistency checks pass.
- Closed-loop official solve rate beats one-shot/two-stage baselines.

Multi-agent internalization gates:

- Team, monolith-R, and monolith-KR controls use matched data and official scoring.
- Team advantage is not claimed unless n>=30 per K.
- Homo and hetero LoRA settings are reported separately.

## Routing

Start with Item097 single-agent traces because Item095 already supplies the method-positive source. Then run Item098 multi-agent traces before any training. Training without trace-positive externalized runs is premature.