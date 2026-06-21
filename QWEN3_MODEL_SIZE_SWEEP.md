# Qwen3 Model Size Sweep

This file defines the follow-up experiment for running the current Qwen3-4B protocol on other text-only Qwen3 model sizes. Results must stay under a model-size root and must not be merged with the Qwen3-4B-Instruct-2507 Item169 root.

## Verified Candidate Models

The accessible text-only Hugging Face IDs verified for this sweep are:

| model | notes |
| --- | --- |
| `Qwen/Qwen3-0.6B` | smallest smoke target |
| `Qwen/Qwen3-1.7B` | small smoke target |
| `Qwen/Qwen3-4B` | base-size comparison, distinct from `Qwen/Qwen3-4B-Instruct-2507` |
| `Qwen/Qwen3-8B` | first larger target |
| `Qwen/Qwen3-14B` | large target, run only after smaller gates pass |
| `Qwen/Qwen3-32B` | largest single-node target, requires careful GPU scheduling |

The `Qwen/Qwen3-*-Instruct` IDs without the 2507 suffix were not accessible in the preflight. `Qwen/Qwen3-VL-8B-Instruct` is a vision-language model and is excluded from this text-only comparison unless explicitly requested.

## Order Of Operations

Run the stages in this order for each model size:

1. `manifest`: verify model availability and snapshot Hugging Face metadata.
2. `exactness`: run KM-3 cache exactness before reading any A_cache evidence for that model.
3. `ac_smoke`: run tokenizer-level A_cache versus C_incontext matched-budget smoke on sudoku/futoshiki.
4. `tot_rap_vllm_smoke`: run corrected ToT/RAP with vLLM on one served model.
5. `lfs_vllm_smoke`: run LFS multistate with vLLM on the same served model.
6. `tot_rap_full_detached` and `lfs_full_detached`: run full grids only after the smoke rows show real search work and no zero-work exhaustion regression.

## Safe Preflight

This command does not load model weights onto GPU. It writes the manifest, A/C tokenizer smoke rows, and a status summary:

```bash
ROOT=results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep \
MODELS=Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-8B \
STAGES=manifest,ac_smoke,summary \
scripts/reproduce_qwen3_model_size_sweep_gpu0_3.sh
```

## Exactness Gate

Run exactness only when GPU0-3 are clear enough to avoid external jobs. Start small, then expand:

```bash
ROOT=results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep \
MODELS=Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B \
STAGES=exactness,summary \
EXACTNESS_DTYPE=bf16 \
EXACTNESS_TOL=1e-3 \
EXACTNESS_PARALLEL=1 \
scripts/reproduce_qwen3_model_size_sweep_gpu0_3.sh
```

For larger models, keep `EXACTNESS_PARALLEL=1` unless GPU utilization is known to be idle. A model is not eligible for an A_cache headline claim unless its exactness output has `status=KVCACHE_EXACTNESS_GATE_PASS` under the dtype/tolerance used by the downstream run.

## vLLM Baseline Smokes

vLLM stages require exactly one model in `MODELS`, with servers already launched for that same model name. Example for 0.6B on GPU0-3:

```bash
ROOT=results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep/vllm_servers/qwen3_0_6b \
MODEL=Qwen/Qwen3-0.6B \
GPUS=0,1,2,3 \
BASE_PORT=8010 \
GPU_MEMORY_UTILIZATION=0.35 \
MAX_MODEL_LEN=4096 \
DTYPE=float32 \
MAX_NUM_SEQS=256 \
MAX_NUM_BATCHED_TOKENS=65536 \
scripts/launch_hb2_vllm_servers_gpu0_3.sh
```

Then run smoke rows:

```bash
ROOT=results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep \
MODELS=Qwen/Qwen3-0.6B \
STAGES=tot_rap_vllm_smoke,lfs_vllm_smoke,summary \
OPENAI_BASE_URLS=http://127.0.0.1:8010/v1,http://127.0.0.1:8011/v1,http://127.0.0.1:8012/v1,http://127.0.0.1:8013/v1 \
VLLM_TASKS=sudoku,futoshiki,graph_color \
VLLM_BUDGET_SCALES=1 \
scripts/reproduce_qwen3_model_size_sweep_gpu0_3.sh
```

The same ToT/RAP guard from Item169 applies: any `BUDGET_EXHAUSTED` row with zero tokens, zero depth, and zero expansions is a regression and must stop the sweep.

## Full vLLM Grids

After smoke rows pass, launch one model at a time. Keep roots isolated by model slug:

```bash
ROOT=results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep \
MODELS=Qwen/Qwen3-0.6B \
STAGES=tot_rap_full_detached,lfs_full_detached,summary \
OPENAI_BASE_URLS=http://127.0.0.1:8010/v1,http://127.0.0.1:8011/v1,http://127.0.0.1:8012/v1,http://127.0.0.1:8013/v1 \
VLLM_SHARDS=16 \
REQUEST_WORKERS=128 \
scripts/reproduce_qwen3_model_size_sweep_gpu0_3.sh
```

Default full-grid outputs are:

```text
results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep/hb2_tot_rap/<model_slug>_full_grid_n64_vllm_gpu0_3_shards16/
results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep/hb2_lfs/<model_slug>_full_grid_n64_vllm_gpu0_3_shards16/
```

## Status Files

The sweep script writes:

```text
results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep/manifest.json
results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep/summary.json
results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep/status.md
```

Record each completed batch as a new item JSON under `results/experiment_items/` and regenerate `results/experiment_log/experiment_log.md`.