#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/kvcache_matched_budget_v0/hb2_lfs/full_grid_n64_vllm_multistate}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
TASKS="${TASKS:-sudoku,futoshiki,graph_color}"
INSTANCES="${INSTANCES:-64}"
BUDGET_SCALES="${BUDGET_SCALES:-0.25,0.5,1,2,4}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-http://127.0.0.1:8012/v1}"
OPENAI_MODEL="${OPENAI_MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
ACTIVE_ROWS="${ACTIVE_ROWS:-32}"
STATE_BATCH_SIZE="${STATE_BATCH_SIZE:-32}"
REQUEST_WORKERS="${REQUEST_WORKERS:-32}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-96}"
SHARDS="${SHARDS:-1}"
mkdir -p "$ROOT/shards"

for shard in $(seq 0 $((SHARDS - 1))); do
  $PY -m analysis.kvcache_lfs_multistate_baseline run-shard \
    --output "$ROOT/shards/result_${shard}.json" \
    --checkpoint-path "$ROOT/shards/checkpoint_${shard}.json" \
    --resume \
    --n-instances "$INSTANCES" \
    --scan-limit 120 \
    --tasks "$TASKS" \
    --budget-anchors sudoku:28070,futoshiki:3206226,graph_color:32895 \
    --budget-scales "$BUDGET_SCALES" \
    --max-expansions 0 \
    --max-new-tokens "$MAX_NEW_TOKENS" \
    --active-rows "$ACTIVE_ROWS" \
    --state-batch-size "$STATE_BATCH_SIZE" \
    --backend vllm \
    --openai-base-url "$OPENAI_BASE_URL" \
    --openai-model "$OPENAI_MODEL" \
    --request-workers "$REQUEST_WORKERS" \
    --futoshiki-size 7 \
    --futoshiki-difficulty 3 \
    --graph-num-vertices 16 \
    --graph-num-colors 3 \
    --graph-edge-probability 0.4 \
    --graph-difficulty-bin-label v16_p04 \
    --num-shards "$SHARDS" \
    --shard-index "$shard" \
    --dtype fp32 \
    --device cuda > "$ROOT/shards/result_${shard}.log" 2>&1 &
done

wait
$PY -m analysis.kvcache_lfs_multistate_baseline merge \
  --inputs "$ROOT/shards/result_*.json" \
  --output "$ROOT/merged_lfs_multistate_vllm_full_grid_n64.json"
