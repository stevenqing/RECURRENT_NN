# Full Reproduction Guide

Last updated: 2026-06-21.

This guide is the paper-facing reproduction entrypoint for the current RECURRENT_NN results. It covers the GPU0-3 reproduction campaign, A_cache/C_incontext mechanism runs, ToT/RAP vLLM external baseline, and the ledger update procedure.

The follow-up model-size sweep for other text-only Qwen3 checkpoints is documented in [QWEN3_MODEL_SIZE_SWEEP.md](QWEN3_MODEL_SIZE_SWEEP.md).

## Scope

The current reproducible claim is workflow-level rather than a fully self-contained artifact bundle.

Tracked in git:

- runner code under `analysis/`, `experiments/`, and `scripts/`
- item records under `results/experiment_items/`
- canonical ledger under `results/experiment_log/`
- reproduction status under `results/reproduction_gpu0_3_20260620/reproduction_status.md`

Regenerated or externally cached:

- `.venv/` and optional `.venv-vllm/`
- Hugging Face model weights for Qwen and Mamba models
- large runtime checkpoints/logs under ignored `results/reproduction_gpu0_3_20260620/**`
- Stage A generated binaries under ignored `artifacts/stage_a/**`

## Environment

From the repo root:

```bash
cd /home/aiscuser/RECURRENT_NN
~/.local/bin/uv venv .venv --python 3.10
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt huggingface_hub accelerate peft
```

For vLLM external baselines:

```bash
~/.local/bin/uv venv .venv-vllm --python 3.10
~/.local/bin/uv pip install --python .venv-vllm/bin/python vllm openai requests aiohttp
```

The standard Python command used by launchers is:

```bash
PY="$HOME/.local/bin/uv run --python .venv/bin/python python"
```

## One-Command GPU0-3 Campaign

The primary orchestrator is:

```bash
scripts/reproduce_gpu0_3_campaign.sh
```

It is resumable. Stages skip completed final artifacts unless `FORCE=1` is set.

Useful controls:

```bash
DRY_RUN=1 scripts/reproduce_gpu0_3_campaign.sh
STAGES=graph_color_symbolic,external_registry scripts/reproduce_gpu0_3_campaign.sh
RUN_EXTERNAL_FULL=1 scripts/reproduce_gpu0_3_campaign.sh
```

Important shard controls:

```bash
DECISION_SHARDS=4
GRAPH_SYMBOLIC_SHARDS=4
GRAPH_C1_SHARDS=4
AC_SHARDS=8
EXTERNAL_SHARDS=8
```

The current campaign root is:

```text
results/reproduction_gpu0_3_20260620/
```

## Current Locked GPU0-3 Results

These items are tracked in the ledger:

| item | result | status |
| --- | --- | --- |
| 164 | exactness gates, decision probe, C1.2 Mamba GPU0-3 | complete |
| 165 | A_cache/C_incontext sudoku and futoshiki primary reproduction | complete |
| 166 | reproduction policy and automation | complete |
| 167 | ToT/RAP corrected direct-run snapshot | pushed snapshot |
| 168 | ToT/RAP vLLM backend restored | complete |
| 169 | ToT/RAP vLLM full grid | complete |

Key current ToT/RAP vLLM result:

```text
results/reproduction_gpu0_3_20260620/hb2_tot_rap/full_grid_n64_vllm_gpu0_3_shards16/merged_tot_rap_vllm_full_grid_n64.json
```

Summary:

```text
rows = 1920 / 1920
summary_rows = 30
backend = vllm_openai_compatible for all rows
methods = ToT 960, RAP 960
tasks = sudoku 640, futoshiki 640, graph_color 640
statuses = NO_FRONTIER 1268, SOLVED 397, BUDGET_EXHAUSTED 255
bad_zero_budget = 0
```

Reference-budget solve rates from Item169:

| task | method | budget | solve rate |
| --- | --- | ---: | ---: |
| sudoku | ToT | 28070 | 0.1875 |
| sudoku | RAP | 28070 | 0.015625 |
| futoshiki | ToT | 3206226 | 0.03125 |
| futoshiki | RAP | 3206226 | 0.0 |
| graph_color | ToT | 32895 | 0.65625 |
| graph_color | RAP | 32895 | 0.578125 |

## A_cache / C_incontext Reproduction

Primary sudoku/futoshiki A/C:

```bash
ROOT=results/reproduction_gpu0_3_20260620/ac_primary_scaled_n64 \
SHARDS=8 \
PY="$HOME/.local/bin/uv run --python .venv/bin/python python" \
scripts/launch_matched_budget_scaled_primary.sh
```

Current reproduced reference-budget results:

```text
sudoku B*=28070: A_cache 57/64 = 0.890625, C_incontext 7/64 = 0.109375
a gap = 0.78125

futoshiki B*=3206226: A_cache 64/64 = 1.0, C_incontext 19/64 = 0.296875
a gap = 0.703125
```

Graph-color symbolic A/C:

```bash
STAGES=graph_color_symbolic scripts/reproduce_gpu0_3_campaign.sh
```

Current reproduced graph-color symbolic result:

```text
n=64, B*=22901, A_cache=1.0, C_incontext=0.40625, gap=0.59375
```

Graph-color C1 A/C:

```bash
ROOT=results/reproduction_gpu0_3_20260620/graph_color_c1_budget_n64 \
SHARDS=4 \
scripts/launch_graph_color_c1_budget.sh
```

Current reproduced graph-color C1 result:

```text
n=64, B*=32895, A_cache=0.96875, C_incontext=0.515625, gap=0.453125
```

## Exactness / Gate Reproduction

The exactness and decision-probe gates are included in the campaign script. Important outputs are:

```text
results/reproduction_gpu0_3_20260620/exactness_gates/
results/reproduction_gpu0_3_20260620/item105_decision_probe/
results/c1_2_architecture_restore_characterization/item162_repro_gpu0_3_20260620/
```

Current locked gates:

```text
Item100 Qwen3.5 KM-3: fail-closed reproduced
Item102 Qwen3 pure-KV KM-3: fp32 tol=1e-3 pass reproduced
Item105 decision probe: 1080 rows reproduced, DP_1=false, DP_2=false
Item162/163 C1.2 real Mamba: TRADE-OFF-FLIPS on GPU0-3
```

## ToT/RAP vLLM Full-Grid Reproduction

Start GPU0-3 vLLM servers:

```bash
ROOT=results/reproduction_gpu0_3_20260620/hb2_vllm_servers/gpu0_3_qwen3_4b_tot_rap_vllm \
GPUS=0,1,2,3 \
BASE_PORT=8010 \
GPU_MEMORY_UTILIZATION=0.70 \
MAX_MODEL_LEN=4096 \
DTYPE=float32 \
MAX_NUM_SEQS=256 \
MAX_NUM_BATCHED_TOKENS=65536 \
scripts/launch_hb2_vllm_servers_gpu0_3.sh
```

Check readiness:

```bash
python - <<'PY'
import urllib.request
for port in [8010, 8011, 8012, 8013]:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=8) as resp:
        print(port, resp.status)
PY
```

Run a small smoke first:

```bash
ROOT=results/reproduction_gpu0_3_20260620/hb2_tot_rap/vllm_smoke_gpu0_3
mkdir -p "$ROOT"
$PY -m analysis.kvcache_tot_rap_baselines run-shard \
  --output "$ROOT/smoke.json" \
  --checkpoint-path "$ROOT/smoke_checkpoint.json" \
  --resume \
  --n-instances 1 \
  --scan-limit 20 \
  --tasks sudoku \
  --methods tot,rap \
  --budget-anchors sudoku:28070 \
  --budget-scales 1 \
  --max-expansions 8 \
  --mcts-iters 4 \
  --max-depth 4 \
  --n-actions 4 \
  --beam-size 4 \
  --value-batch-size 8 \
  --rollout-depth 1 \
  --rollout-branching 1 \
  --max-new-tokens 96 \
  --backend vllm \
  --openai-base-url http://127.0.0.1:8010/v1 \
  --openai-model Qwen/Qwen3-4B-Instruct-2507 \
  --request-workers 32 \
  --num-shards 1 \
  --shard-index 0 \
  --dtype fp32 \
  --device cuda
```

Run the completed 16-shard full grid:

```bash
RUN_ROOT=results/reproduction_gpu0_3_20260620/runs/tot_rap_vllm_gpu0_3_shards16 \
ROOT=results/reproduction_gpu0_3_20260620/hb2_tot_rap/full_grid_n64_vllm_gpu0_3_shards16 \
TASKS=sudoku,futoshiki,graph_color \
METHODS=tot,rap \
INSTANCES=64 \
BUDGET_SCALES=0.25,0.5,1,2,4 \
VALUE_BATCH_SIZE=32 \
REQUEST_WORKERS=128 \
SHARDS=16 \
OPENAI_BASE_URLS=http://127.0.0.1:8010/v1,http://127.0.0.1:8011/v1,http://127.0.0.1:8012/v1,http://127.0.0.1:8013/v1 \
scripts/launch_hb2_tot_rap_vllm_multi_server_detached.sh
```

After completion, stop repo-owned vLLM servers unless another vLLM baseline is scheduled:

```bash
for pid_file in results/reproduction_gpu0_3_20260620/hb2_vllm_servers/gpu0_3_qwen3_4b_tot_rap_vllm/gpu*_port*/server.pid; do
  pid=$(cat "$pid_file")
  kill "$pid" 2>/dev/null || true
done
```

## LFS / Best-of-N Status

LFS and best-of-n are separate external baselines and should not be conflated with Item169. Current tracked status says ToT/RAP vLLM is complete; LFS and best-of-n finalization should be recorded as separate items when their merged outputs are available.

Existing LFS vLLM entrypoints:

```bash
scripts/launch_hb2_vllm_servers_gpu0_3.sh
scripts/launch_hb2_lfs_multistate_vllm_multi_server_detached.sh
```

Direct best-of-n entrypoint:

```bash
scripts/launch_hb2_best_of_n_full_grid.sh
```

## Ledger Update Procedure

After a completed run:

1. Write a new `results/experiment_items/item_XXX_*.json` record.
2. Regenerate the ledger:

```bash
$PY -m analysis.experiment_log
```

3. Verify the item appears:

```bash
grep -n "Item XXX" results/experiment_log/experiment_log.md
```

4. Commit and push:

```bash
git add results/experiment_items/item_XXX_*.json results/experiment_log/experiment_log.json results/experiment_log/experiment_log.md
git add -f results/reproduction_gpu0_3_20260620/reproduction_status.md
git commit -m "Record <short description>"
git push origin main
```

## Current GitHub Anchor

The current pushed commit after ToT/RAP vLLM completion is:

```text
403fa4e Record ToT RAP vLLM full grid
```

Remote:

```text
https://github.com/stevenqing/RECURRENT_NN.git
```

## Known Caveats

- `results/experiment_log/experiment_log.json` is larger than GitHub's recommended 50 MB threshold; GitHub accepts the push but warns about LFS.
- Large runtime outputs under `results/reproduction_gpu0_3_20260620/**` are ignored by git. Item JSONs record their paths and summaries.
- Do not merge direct-Transformers ToT/RAP rows with vLLM ToT/RAP rows.
- Valid `BUDGET_EXHAUSTED` rows may occur after real search work. The quarantined bug is zero-work `BUDGET_EXHAUSTED` with `tokens_used=0`, `depth_reached=0`, and `expansions=0`.
- Recovered summary-only historical items cannot be faithfully replayed unless original cluster JSON/scripts are recovered.
