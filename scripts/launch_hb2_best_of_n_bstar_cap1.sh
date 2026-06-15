#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/kvcache_matched_budget_v0/hb2_best_of_n/bstar_n64_cap1}"
SHARDS="${SHARDS:-8}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
mkdir -p "$ROOT/shards"

for shard in $(seq 0 $((SHARDS - 1))); do
  CUDA_VISIBLE_DEVICES="$shard" $PY -m analysis.kvcache_best_of_n_baseline run-shard \
    --output "$ROOT/shards/shard_${shard}.json" \
    --checkpoint-path "$ROOT/shards/shard_${shard}_checkpoint.json" \
    --resume \
    --n-instances 64 \
    --scan-limit 120 \
    --tasks sudoku,futoshiki,graph_color \
    --budget-anchors sudoku:28070,futoshiki:3206226,graph_color:32895 \
    --budget-scales 1 \
    --max-samples-per-budget 1 \
    --max-new-tokens 128 \
    --temperature 0.8 \
    --top-p 0.95 \
    --futoshiki-size 7 \
    --futoshiki-difficulty 3 \
    --graph-num-vertices 16 \
    --graph-num-colors 3 \
    --graph-edge-probability 0.4 \
    --graph-difficulty-bin-label v16_p04 \
    --num-shards "$SHARDS" \
    --shard-index "$shard" \
    --dtype fp32 \
    --device cuda > "$ROOT/shards/shard_${shard}.log" 2>&1 &
done

wait
$PY -m analysis.kvcache_best_of_n_baseline merge \
  --inputs "$ROOT/shards/shard_[0-9].json" \
  --output "$ROOT/merged_best_of_n_bstar_n64_cap1.json"
