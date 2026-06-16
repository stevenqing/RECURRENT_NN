# RECURRENT_NN Reproducibility Contract

Last audited: 2026-06-16 at commit `d509790`.

This repository is reproducible as a workflow, not as a fully self-contained binary snapshot.

## What Is Git-Contained

The following are tracked and should exist immediately after checkout:

- environment/setup instructions in `ENV_SPEC.md`
- canonical repo note in `CANONICAL_REPO.md`
- validation and ledger code in `analysis/validate_outputs.py` and `analysis/experiment_log.py`
- KV-cache matched-budget runners and HB-2 external baseline adapters:
  - `analysis/kvcache_matched_budget_scaled.py`
  - `analysis/kvcache_graph_color_budget_curves.py`
  - `analysis/kvcache_graph_color_c1_budget.py`
  - `analysis/kvcache_best_of_n_baseline.py`
  - `analysis/kvcache_lfs_baseline.py`
  - `analysis/kvcache_tot_rap_baselines.py`
  - `analysis/kvcache_external_budget_baselines.py`
- HB-2 launchers:
  - `scripts/launch_hb2_best_of_n_full_grid.sh`
  - `scripts/launch_hb2_lfs_full_grid.sh`
  - `scripts/launch_hb2_tot_rap_full_grid.sh`
  - `scripts/launch_hb2_external_full_grid.sh`
  - `scripts/launch_hb2_vllm_server.sh`
  - `scripts/launch_hb2_vllm_servers_gpu0_3.sh`
  - `scripts/launch_hb2_lfs_multistate_vllm_full_grid.sh`
  - `scripts/launch_hb2_lfs_multistate_vllm_multi_server.sh`
  - `scripts/launch_hb2_lfs_multistate_vllm_multi_server_detached.sh`
- Stage A fill-in entrypoints in `experiments/stage_a_adapter_wiring.py`, `experiments/stage_a_banded_gate_refusal.py`, and `experiments/stage_a_sudoku6_bridge.py`
- W3 Qwen3.5 metadata probe in `experiments/w3_qwen35_probe.py`
- specs in `specs/g1_fix_spec.md` and `specs/w3_qwen35_probe_spec.md`
- small JSON/markdown ledger records under `results/`

## External Or Regenerated Assets

These are not stored in git and must be regenerated or downloaded:

- Python environment under `.venv/`
- local external repo clones under `external_repos/`; only repo URL/commit provenance is tracked
- Hugging Face model cache for `Qwen/Qwen3-4B-Instruct-2507`, `Qwen/Qwen3-4B-Thinking-2507`, and `Qwen/Qwen3.5-4B`
- Stage A reconstructed binaries:
  - `artifacts/stage_a/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt`
  - `artifacts/stage_a/item142_factored_cell_digit_decoder_depth8_D128.pt`
  - `artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl`

Those Stage A files are intentionally ignored because they are generated binary/trace artifacts. Recreate them with:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m experiments.reconstruct_stage_a_artifacts \
  --output-dir artifacts/stage_a \
  --n-instances 1024 \
  --seed 42 \
  --device cuda:0 \
  --operator-steps 300 \
  --bridge-steps 500 \
  --batch-size 256
```

## One-Command Continuation Refresh

After environment creation, run:

```bash
bash scripts/reproduce_continuation_state.sh
```

By default this does not redownload Qwen weights. To redownload/refresh model records too:

```bash
DOWNLOAD_MODELS=1 bash scripts/reproduce_continuation_state.sh
```

Expected current-state validation after refresh currently has the known Stage-A red checks:

```text
967 PASS / 3 FAIL / 970 total
```

The 3 failures are the long-standing Stage-A autonomous learned-track blockers. Do not reinterpret them as HB-2 regressions.

## Current KV-Cache / HB-2 Reproduction Entrypoints

Use the repo-local Python command pattern:

```bash
PY="$HOME/.local/bin/uv run --python .venv/bin/python python"
```

### Primary A-cache vs C-in-context Results

The tracked item records and small merged JSON artifacts document the current primary results. To regenerate the main CSP matched-budget grid, use:

```bash
scripts/launch_matched_budget_scaled_primary.sh
```

This reproduces the scaled CSP A-vs-C grid under `results/kvcache_matched_budget_v0/scaled_primary_n64/`.

Graph-color symbolic and C1 budget curves are produced by:

```bash
$PY -m analysis.kvcache_graph_color_budget_curves \
  --input results/kvcache_matched_budget_v0/graph_color_part_a/v16_r16_symbolic_n64.json \
  --output results/kvcache_matched_budget_v0/graph_color_part_a/v16_r16_symbolic_budget_curve_n64.json

$PY -m analysis.kvcache_graph_color_c1_budget merge \
  --inputs 'results/kvcache_matched_budget_v0/graph_color_part_a/c1_v16_r16_n64_shards/shard_[0-9].json' \
  --output results/kvcache_matched_budget_v0/graph_color_part_a/c1_v16_r16_n64_shards/merged_c1_v16_r16_n64.json
```

The graph-color C1 shard generation itself is expensive and uses `analysis.kvcache_graph_color_c1_budget run-shard`; see `results/experiment_items/item_123_graph_color_c1_budget_targeting_independence.json` for the exact recorded scope.

### HB-2 External No-Train Baselines

Current external baseline methods are all repo-grounded and no-train:

- best-of-n parallel sampling: `analysis/kvcache_best_of_n_baseline.py`
- LFS repo-port: `analysis/kvcache_lfs_baseline.py`
- ToT/RAP repo-port: `analysis/kvcache_tot_rap_baselines.py`

Official upstream provenance is tracked in:

- `results/kvcache_matched_budget_v0/external_repo_provenance.json`
- `results/kvcache_matched_budget_v0/external_budget_runner_registry.json`

The current accelerated HB-2 external full-grid launcher uses GPUs 0-3 only, 8 shards (two model processes per GPU), and higher batching for the methods that support it:

```bash
BASELINES=lfs,tot_rap,best_of_n \
SHARDS=8 \
GPUS=4 \
INSTANCES=64 \
TASKS=sudoku,futoshiki,graph_color \
BUDGET_SCALES=0.25,0.5,1,2,4 \
SAMPLE_BATCH_SIZE=32 \
VALUE_BATCH_SIZE=8 \
scripts/launch_hb2_external_full_grid.sh
```

For long runs, prefer the detached wrapper so the run survives VS Code terminal lifecycle events:

```bash
scripts/launch_hb2_external_full_grid_detached.sh
```

It writes a master log and pid file under `results/kvcache_matched_budget_v0/hb2_external_runs/`.

By default this writes to separate GPU0-3 batched roots:

- `results/kvcache_matched_budget_v0/hb2_lfs/full_grid_n64_gpu0_3_x2_batched/`
- `results/kvcache_matched_budget_v0/hb2_tot_rap/full_grid_n64_gpu0_3_x2_batched/`
- `results/kvcache_matched_budget_v0/hb2_best_of_n/full_grid_n64_gpu0_3_x2_batched/`

These roots are intentionally separate from the cancelled earlier roots. Do not merge rows across `full_grid_n64/`, `full_grid_n64_gpu0_3_batched/`, and `full_grid_n64_gpu0_3_x2_batched/`; their shard partitions differ.

Use the individual launchers when reproducing one baseline at a time:

```bash
scripts/launch_hb2_lfs_full_grid.sh
scripts/launch_hb2_tot_rap_full_grid.sh
scripts/launch_hb2_best_of_n_full_grid.sh
```

All these launchers use checkpoint/resume files. If interrupted, rerun the same command with the same `ROOT`, `SHARDS`, `TASKS`, and `BUDGET_SCALES`.

### Optional vLLM External Backend Smoke

The vLLM backend is for external no-train baselines only. It is not used for exact KV-cache A/C mechanism runs.

Start a small OpenAI-compatible vLLM server with:

```bash
RUN_ROOT=results/kvcache_matched_budget_v0/hb2_vllm_servers/qwen3_4b_gpu4_port8012 \
GPU=4 \
PORT=8012 \
GPU_MEMORY_UTILIZATION=0.35 \
MAX_MODEL_LEN=4096 \
scripts/launch_hb2_vllm_server.sh
```

Then run the multi-state LFS vLLM backend smoke with:

```bash
$PY -m analysis.kvcache_lfs_multistate_baseline run-shard \
  --output results/kvcache_matched_budget_v0/hb2_lfs/speed_micro_vllm/result.json \
  --checkpoint-path results/kvcache_matched_budget_v0/hb2_lfs/speed_micro_vllm/checkpoint.json \
  --tasks sudoku \
  --n-instances 4 \
  --budget-anchors sudoku:28070 \
  --budget-scales 0.032 \
  --backend vllm \
  --openai-base-url http://127.0.0.1:8012/v1 \
  --openai-model Qwen/Qwen3-4B-Instruct-2507 \
  --request-workers 4
```

As of item 132, the micro smoke measured 9.698s wall-clock for vLLM multi-state LFS versus 28.451s for Transformers multi-state and 79.943s for single-state LFS. Treat this as backend feasibility only, not a final HB-2 result.

For the fastest LFS vLLM backend run on GPUs 0-3, launch one vLLM server per GPU:

```bash
ROOT=results/kvcache_matched_budget_v0/hb2_vllm_servers/gpu0_3_qwen3_4b_formal \
GPUS=0,1,2,3 \
BASE_PORT=8010 \
GPU_MEMORY_UTILIZATION=0.80 \
MAX_MODEL_LEN=4096 \
scripts/launch_hb2_vllm_servers_gpu0_3.sh
```

Then launch LFS against those servers:

```bash
RUN_ROOT=results/kvcache_matched_budget_v0/hb2_external_runs/lfs_vllm_multiserver_formal \
ROOT=results/kvcache_matched_budget_v0/hb2_lfs/full_grid_n64_vllm_gpu0_3_multiserver \
TASKS=sudoku,futoshiki,graph_color \
INSTANCES=64 \
BUDGET_SCALES=0.25,0.5,1,2,4 \
ACTIVE_ROWS=512 \
STATE_BATCH_SIZE=256 \
REQUEST_WORKERS=256 \
SHARDS=4 \
scripts/launch_hb2_lfs_multistate_vllm_multi_server_detached.sh
```

Keep this backend separate from direct-Transformers roots.

### Smoke / Adapter Gates

The adapter-only smoke records are tracked and should not be read as final performance:

- `results/experiment_items/item_125_hb2_best_of_n_exhaustive_smoke.json`
- `results/experiment_items/item_126_hb2_lfs_repo_port_smoke.json`
- `results/experiment_items/item_127_hb2_tot_rap_repo_port_smoke.json`

The launch/progress records are:

- `results/experiment_items/item_128_hb2_external_full_grid_launch.json`
- `results/experiment_items/item_129_hb2_gpu03_batched_relaunch.json`

These records establish engineering reproducibility and launch provenance only. HB-2 confirm/kill requires merged full-grid outputs.

## Bitwise Caveats

Exact byte-for-byte reproduction is not guaranteed for every generated file.

- `requirements.txt` uses lower bounds, not a lockfile. `ENV_SPEC.md` records the verified package snapshot, but `uv pip install -r requirements.txt` may resolve newer packages in the future.
- GPU training/reconstruction can be nondeterministic across CUDA/PyTorch versions. The manifest hashes record the local reconstructed artifacts, not a guaranteed future bitwise target.
- JSON files with `generated_at` timestamps will naturally differ between runs.
- HB-2 runtime checkpoints/logs under ignored `results/kvcache_matched_budget_v0/**` are not all committed. Only small item records, provenance records, and selected final/smoke JSON artifacts are tracked. Regenerate large grids with the launchers above.
- Hugging Face cache paths can differ by machine. The model ids and snapshot records are the reproducibility anchors.

## Honest Claim

The current claim is:

- environment setup is documented and verified on this machine;
- model assets are externally downloadable and records exist;
- Stage A parent artifacts are regenerable from repo code;
- continuation validation/ledger can be refreshed from tracked scripts;
- KV-cache A/C and HB-2 method code/launch commands are tracked;
- the scientific status is still red at Stage A G1/L4, and HB-2 external full-grid results remain in progress until merged outputs are present.

The current claim is not:

- a fully self-contained checkout with all binaries committed;
- a bitwise deterministic artifact bundle;
- a completed P1/P2/P3 experiment run;
- a completed HB-2 external full-grid read at the time of this audit.
