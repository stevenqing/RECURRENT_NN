#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/kvcache_matched_budget_v0/hb2_tot_rap/full_grid_n64_gpu0_3_batched}"
SHARDS="${SHARDS:-4}"
GPUS="${GPUS:-4}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
TASKS="${TASKS:-sudoku,futoshiki,graph_color}"
METHODS="${METHODS:-tot,rap}"
INSTANCES="${INSTANCES:-64}"
BUDGET_SCALES="${BUDGET_SCALES:-0.25,0.5,1,2,4}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-96}"
N_ACTIONS="${N_ACTIONS:-4}"
BEAM_SIZE="${BEAM_SIZE:-4}"
ROLLOUT_BRANCHING="${ROLLOUT_BRANCHING:-1}"
VALUE_BATCH_SIZE="${VALUE_BATCH_SIZE:-8}"
mkdir -p "$ROOT/shards"

for shard in $(seq 0 $((SHARDS - 1))); do
  gpu=$((shard % GPUS))
  CUDA_VISIBLE_DEVICES="$gpu" $PY -m analysis.kvcache_tot_rap_baselines run-shard \
    --output "$ROOT/shards/result_${shard}.json" \
    --checkpoint-path "$ROOT/shards/checkpoint_${shard}.json" \
    --resume \
    --n-instances "$INSTANCES" \
    --scan-limit 120 \
    --tasks "$TASKS" \
    --methods "$METHODS" \
    --budget-anchors sudoku:28070,futoshiki:3206226,graph_color:32895 \
    --budget-scales "$BUDGET_SCALES" \
    --max-expansions 0 \
    --mcts-iters 0 \
    --max-depth 0 \
    --n-actions "$N_ACTIONS" \
    --beam-size "$BEAM_SIZE" \
    --value-batch-size "$VALUE_BATCH_SIZE" \
    --rollout-depth 0 \
    --rollout-branching "$ROLLOUT_BRANCHING" \
    --max-new-tokens "$MAX_NEW_TOKENS" \
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
$PY -m analysis.kvcache_tot_rap_baselines merge \
  --inputs "$ROOT/shards/result_*.json" \
  --output "$ROOT/merged_tot_rap_full_grid_n64.json"
