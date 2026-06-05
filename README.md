# Stage D LLM Instantiation (Qwen3-4B)

This folder implements the Stage D scaffold from the addendum: a frozen Qwen3-4B-Instruct operator wrapped by a controller, verifier, and bounded reversible register, with Qwen3-4B-Thinking as the token-CoT baseline. The repo-local execution plan is [PLAN.md](PLAN.md).

## Core Claim

Token CoT already has an unbounded append-only tape, so the non-vacuous claim is about latent reasoning with a fixed-width reused state. Latent-only passes cannot backtrack; bounded structured reversible registers can hold branch restore-points up to the predicted capacity ceiling:

```text
d*_dyn ~= D / (2 ln K)
```

## Layout

- `config/`: backbone, register, and experiment configs.
- `llm_operator/`: bounded prompt renderer and frozen Qwen operator wrapper.
- `baseline/`: Qwen Thinking CoT harness and compute accounting.
- `register/`: rotation/VSA register, GRU baseline, TTT diagnostic.
- `controller/`: controller head, search loop, answer-free verifier.
- `tasks/`: symbolic oracle, Sudoku, SAT, graph coloring, logic grid, and demo agentic domains.
- `experiments/`: D.3, D-stage 0-3, D.5, and D.6 entry scripts.
- `analysis/`: pre-registration, scaffold evaluation, plotting, and summary helpers.
- `disciplines.md`: D.9 checklist.
- `PLAN.md`: D.0-D.9 execution plan generated from the addendum.

## Run Order

```bash
cd /home/aiscuser/stage_d_llm
~/.local/bin/uv venv .venv --python 3.10
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt huggingface_hub accelerate
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

The experiment scripts are runnable scaffolds: they create task sets/result JSON and expose the exact gates where full training/evaluation loops should be connected. Current executable outputs are marked `evaluation_mode: oracle_trace_scaffold`.

`python -m analysis.operator_cache` defaults to deterministic hashed prompt features for local runs. To cache real frozen Qwen operator hidden states, run `python -m analysis.operator_cache --load-model` in an environment with the Qwen weights available. `python -m experiments.learned_wiring_baseline` trains on seeds other than `999` and reports seed-999 holdout metrics separately.

The Qwen snapshots are downloaded with uv via `python -m analysis.download_qwen`; current setup records both `Qwen/Qwen3-4B-Instruct-2507` and `Qwen/Qwen3-4B-Thinking-2507` under `results/model_download/`.

## Non-Negotiable Disciplines

- Prompt is bounded current-node rendering only; no stack in prompt.
- Search stack lives only in register `h`.
- Revert is causal and in-loop.
- Supervision is symbolic oracle traces only.
- No-revert and GRU baselines are mandatory.
- Win band must be pre-registered before D-stage 3.
