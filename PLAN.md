# Stage D Plan - Qwen3-4B Falsifiable LLM Instantiation

This is the repo-local execution plan generated from the Stage D addendum. It keeps the claim falsifiable: token CoT already has an append-only stack, so Stage D only tests whether fixed-width latent reasoning can backtrack when the stack is stored in a bounded reversible register.

## D.0 Claim

Latent-only extra forward computation, with no emitted tokens and no growing tape, should not solve genuinely backtracking-required tasks. A structured reversible register should solve those tasks up to the predicted capacity ceiling:

```text
d*_dyn ~= D / (2 ln K)
```

The comparison is therefore not "LLM vs LLM" in general. It is where the search stack lives:

- `latent_structured`: stack lives in fixed-width register `h`.
- `qwen_thinking_cot`: stack lives in append-only `<think>` tokens.
- `latent_only` / `naive_pass_scaling`: no causal revert stack.

## D.1 Pinned Backbone And Roles

- Operator: `Qwen/Qwen3-4B-Instruct-2507`, frozen, non-thinking, one bounded current-node forward pass per operator step.
- Token-CoT baseline: `Qwen/Qwen3-4B-Thinking-2507`, allowed to use `<think>` as the external append-only stack.
- Trainable components only: structured register update/readout, controller head, verifier head.
- LoRA on the operator is a recorded deviation, not the default.

Operator interface rules:

- Prompt contains only givens plus the partial assignment at the current search node.
- Prompt is re-rendered every step and is never append-only.
- Register `h` owns branch restore-points and is the only search stack.
- Revert pops `h`, reconstructs the current partial assignment, and re-renders the prompt.

Repo mapping:

- Operator wrapper: `llm_operator/wrapper.py` and `llm_operator/prompt_renderer.py`.
- Controller/search loop: `controller/controller_head.py`.
- Verifier: `controller/verifier_head.py`.
- Structured register and GRU baseline: `register/structured.py`, `register/gru_baseline.py`.
- CoT baseline and compute accounting: `baseline/cot_harness.py`, `baseline/compute_accounting.py`.

## D.2 Substrates

Core controlled tasks are self-generated CSPs graded by minimal DPLL backtrack depth, with symbolic oracle traces:

- 4x4 Sudoku for the small-model controlled regime.
- 9x9 Sudoku as an external/non-core anchor.
- Horn-SAT for propagation-only tasks.
- General SAT, graph coloring, and logic-grid tasks for branching-required tasks.
- Optional demo tier: Blocksworld, Sokoban, Countdown/Game-of-24, search-before-act only.

Rules:

- Supervision comes from symbolic oracle traces only.
- Sudoku-Bench is not a core depth benchmark; use only as an external comparability anchor.
- Browser/GUI agents with irreversible side effects are out of scope for Stage D.

## D.3 First Gate: 2x2 Falsification

Factors:

- Methods: `latent_only`, `latent_plus_structured_register`.
- Task columns: `propagation_only`, `backtracking_required`.

Prediction:

- Register should not improve propagation-only tasks.
- Register should improve backtracking-required tasks.

Executable entry:

```bash
python -m experiments.two_by_two_falsification
```

Output:

- `results/two_by_two/results.json`

## D.4 Gated Stages

### D-stage 0 - Propagation Spine

Claim: the frozen operator, driven for more propagation steps without branching, extrapolates deductive depth.

Kill-test: train to `d_train`, test to `d_train + k`, and plot solve rate against required propagation depth and step budget.

Executable scaffold:

```bash
python -m experiments.d_stage_0_propagation
```

Output:

- `results/d_stage_0/results.json`

### D-stage 1 - Latent Boundary And Depth-1 Revert Gate

Claims:

- Latent-only does not cross backtracking-required tasks no matter how many passes.
- Structured register passes a depth-1 gate with `applied_reverts > 0`.
- GRU-register and no-revert ablation collapse to the latent-only floor.

Executable scaffold:

```bash
python -m experiments.d_stage_1_depth1_gate
```

Output:

- `results/d_stage_1/results.json`

### D-stage 2 - Capacity Frontier

Claim: structured-register depth capacity is approximately linear in register width `D`, following `D / (2 ln K)`, while GRU is sublinear.

Executable scaffold:

```bash
python -m experiments.d_stage_2_capacity
```

Output:

- `results/d_stage_2/results.json`

### D-stage 3 - Structured Register Vs Token CoT

Claim: within preregistered `depth < d*(D, K)`, the structured latent method beats token-CoT at matched compute; beyond the ceiling, residual externalization should take over.

Required before running:

```bash
python -m analysis.preregistration
```

Executable scaffold:

```bash
python -m experiments.d_stage_3_vs_cot
```

Outputs:

- `results/preregistration/preregistration.json`
- `results/d_stage_3/results.json`

## D.5 Verifier Verification

The verifier is answer-free and first-class. It must be ablated across:

- `oracle`
- `learned`
- `noisy`
- `disabled`

Metrics:

- solve rate
- false-positive reverts
- false-negative misses

Executable scaffold:

```bash
python -m experiments.verifier_verification
```

Output:

- `results/verifier/results.json`

## D.6 TTT Reversibility Diagnostic

Gradient fast-weight / TTT-style updates are not cleanly invertible, while rotation/VSA push-pop is designed to be reversible.

Executable diagnostic:

```bash
python -m experiments.ttt_reversibility
```

Output:

- `results/ttt/results.json`

## D.7 Preregistered d*_dyn Bands

Use `D` and branch domain `K` so the predicted ceiling lands in the measurable range.

| D | K | predicted d*_dyn | Use |
|---:|---:|---:|---|
| 256 | 729 | ~19 | small-D large-K |
| 512 | 729 | ~39 | medium-D large-K |
| 256 | 60 | ~31 | small-D medium-K |
| 512 | 60 | ~63 | medium-D medium-K |
| 1024 | 729 | ~78 | large-D large-K |
| 4096 | 60 | ~500 | off-screen large-D control |

Entry:

```bash
python -m analysis.preregistration
```

## D.8 Artifacts To Build

Current repo status:

- Done scaffold: frozen Qwen operator wrapper.
- Done scaffold: bounded current-node prompt renderer.
- Done scaffold: CoT baseline harness with compute accounting.
- Done scaffold: structured register, GRU baseline, controller head, verifier head.
- Done scaffold: SAT, Sudoku 4x4, graph coloring, synthetic logic-grid with oracle traces, and demo agentic generators.
- External anchor stub: 9x9 Sudoku is present but intentionally non-core for the Qwen3-4B Stage D proof.
- Done scaffold: preregistration, gated experiment entries, TTT diagnostic.
- Done scaffold: oracle-trace evaluation layer for executable JSON outputs.
- Done scaffold: oracle-supervision JSONL builder for controller/register/verifier training examples.
- Done scaffold: operator feature cache builder; default local mode uses deterministic hashed prompt features, while `--load-model` switches to frozen Qwen hidden states.
- Done scaffold: supervised cached-feature controller/verifier wiring baseline.
- Next full-model work: replace scaffold outcome rules with trained controller/register/verifier evaluation loops while preserving the same gates and result schema.

## D.9 Disciplines

- Backbone frozen; train only register/controller/verifier heads.
- LoRA is a deviation and must be recorded as such.
- Prompt is bounded current-node rendering only; no stack in prompt.
- Search stack lives only in register `h`.
- Revert must use the register in-loop, causally.
- Supervision is symbolic oracle traces only.
- No-revert ablation is mandatory and must collapse to latent-only.
- GRU-register is the labeled negative baseline.
- Verifier is answer-free and must be ablated.
- Win band is preregistered before D-stage 3.
- Comparisons use matched compute and report mean +/- std over seeds for headline numbers.
- Agentic tier is demo-only, single-agent, and search-before-act over reversible models.

## Full Run Order

```bash
cd /home/aiscuser/stage_d_llm
python -m analysis.preregistration
python -m analysis.oracle_dataset
python -m analysis.model_readiness
python -m analysis.operator_cache
python -m experiments.learned_wiring_baseline
python -m experiments.two_by_two_falsification
python -m experiments.d_stage_0_propagation
python -m experiments.d_stage_1_depth1_gate
python -m experiments.d_stage_2_capacity
python -m experiments.d_stage_3_vs_cot
python -m experiments.verifier_verification
python -m experiments.ttt_reversibility
python -m analysis.plotting
python -m analysis.validate_outputs
python -m analysis.experiment_log
```

## Reporting

After the run order completes, collect:

- `results/preregistration/preregistration.json`
- `results/oracle_dataset/examples.jsonl`
- `results/oracle_dataset/summary.json`
- `results/operator_cache/operator_cache.pt`
- `results/operator_cache/summary.json`
- `results/model_readiness/readiness.json`
- `results/model_download/qwen_download.json`
- `results/model_download/thinking/qwen_download.json`
- `results/operator_cache/qwen_probe_cache.pt`
- `results/operator_cache/qwen_probe_cache_summary.json`
- `results/operator_cache/qwen_128_cache.pt`
- `results/operator_cache/qwen_128_cache_summary.json`
- `results/learned_wiring_qwen_128/results.json`
- `results/learned_wiring_qwen_128/heads.pt`
- `results/operator_cache/qwen_balanced_320_cache.pt`
- `results/operator_cache/qwen_balanced_320_cache_summary.json`
- `results/learned_wiring_qwen_balanced_320/results.json`
- `results/learned_wiring_qwen_balanced_320/heads.pt`
- `results/module1_stack_capacity/results.json`
- `results/module1_stack_capacity/run.log`
- `results/module1_stack_capacity_full/results.json`
- `results/module1_stack_capacity_full/run.log`
- `results/learned_wiring/results.json`
- `results/learned_wiring/heads.pt`
- `results/two_by_two/results.json`
- `results/d_stage_0/results.json`
- `results/d_stage_1/results.json`
- `results/d_stage_2/results.json`
- `results/d_stage_3/results.json`
- `results/verifier/results.json`
- `results/ttt/results.json`
- `results/analysis/summary.md`
- `results/validation/validation.md`
- `results/validation/validation.json`
- `results/experiment_log/experiment_log.md`
- `results/experiment_log/experiment_log.json`

The current executable layer is explicitly marked as `oracle_trace_scaffold`. It is useful for checking the plan, gate logic, result schema, and causal controls before expensive full-model training/evaluation is connected.