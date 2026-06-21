# RECURRENT_NN

This repository tracks a research program around reversible test-time compute, bounded state, KV-cache restore, and external no-train search baselines for frozen LLMs. The original Stage D scaffold is still present, but the current paper-facing ledger also includes KV-cache exactness gates, A_cache versus C_incontext matched-budget experiments, C1.2 state-restore checks, and HB-2 external baselines.

For the current end-to-end reproduction entrypoint, use [REPRODUCTION_FULL.md](REPRODUCTION_FULL.md). The shorter workflow contract is [REPRODUCIBILITY.md](REPRODUCIBILITY.md), and the canonical item ledger is [results/experiment_log/experiment_log.md](results/experiment_log/experiment_log.md).

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

## Current Reproduction Entry

The recommended GPU0-3 reproduction path is:

```bash
cd /home/aiscuser/RECURRENT_NN
~/.local/bin/uv venv .venv --python 3.10
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt huggingface_hub accelerate peft
scripts/reproduce_gpu0_3_campaign.sh
```

The current completed ToT/RAP vLLM full-grid reproduction is recorded as Item169:

```text
results/reproduction_gpu0_3_20260620/hb2_tot_rap/full_grid_n64_vllm_gpu0_3_shards16/merged_tot_rap_vllm_full_grid_n64.json
```

Summary:

```text
rows = 1920 / 1920
backend = vllm_openai_compatible
tasks = sudoku 640, futoshiki 640, graph_color 640
methods = ToT 960, RAP 960
statuses = NO_FRONTIER 1268, SOLVED 397, BUDGET_EXHAUSTED 255
bad_zero_budget = 0
```

See [REPRODUCTION_FULL.md](REPRODUCTION_FULL.md) for exact commands, vLLM setup, A/C reproduction commands, gate checks, cleanup, ledger update procedure, and caveats.

## Legacy Stage D Run Order

The original Stage D scaffold run order is retained for historical context. It is not the current full-paper reproduction path.

```bash
cd /home/aiscuser/RECURRENT_NN
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
