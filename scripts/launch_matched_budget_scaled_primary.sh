#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/kvcache_matched_budget_v0/scaled_primary_n64}"
SHARDS="${SHARDS:-8}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
mkdir -p "$ROOT/shards"

for shard in $(seq 0 $((SHARDS - 1))); do
  $PY -m analysis.kvcache_matched_budget_scaled run-shard \
    --output "$ROOT/shards/shard_${shard}.json" \
    --checkpoint-path "$ROOT/shards/shard_${shard}_checkpoint.json" \
    --resume \
    --n-instances 64 \
    --scan-limit 120 \
    --tasks sudoku,futoshiki \
    --policies symbolic_cbj \
    --num-shards "$SHARDS" \
    --shard-index "$shard" \
    --futoshiki-size 7 \
    --futoshiki-difficulty 3 \
    --node-cap 50000 \
    --budget-anchors sudoku:28070,futoshiki:3206226 \
    --budget-scales 0.25,0.5,1,2,4 \
    --max-event-rows-per-trace 4 > "$ROOT/shards/shard_${shard}.log" 2>&1 &
done

wait
$PY -m analysis.kvcache_matched_budget_scaled merge \
  --inputs "$ROOT/shards/shard_*.json" \
  --output "$ROOT/merged_scaled_primary_n64.json"
