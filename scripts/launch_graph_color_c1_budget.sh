#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/kvcache_matched_budget_v0/graph_color_part_a/c1_v16_r16_n64_shards}"
SHARDS="${SHARDS:-8}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
mkdir -p "$ROOT/shards"

for shard in $(seq 0 $((SHARDS - 1))); do
  CUDA_VISIBLE_DEVICES="$shard" $PY -m analysis.kvcache_graph_color_c1_budget \
    --output "$ROOT/shards/shard_${shard}.json" \
    --checkpoint-path "$ROOT/shards/shard_${shard}_checkpoint.json" \
    --resume \
    --n-instances 64 \
    --scan-limit 1000 \
    --min-backtracks 4 \
    --node-cap 500 \
    --bins v16_p04:16:0.4 \
    --r-value 16 \
    --call-cap 160 \
    --cot-max-new-tokens 256 \
    --cot-fallback chrono \
    --cot-prompt-style per_color \
    --dtype fp32 \
    --device cuda \
    --num-shards "$SHARDS" \
    --shard-index "$shard" > "$ROOT/shards/shard_${shard}.log" 2>&1 &
done

wait
$PY -m analysis.kvcache_graph_color_c1_budget \
  --merge-inputs "$ROOT/shards/shard_[0-9].json" \
  --output "$ROOT/merged_c1_v16_r16_n64.json" \
  --checkpoint-path "$ROOT/unused_checkpoint.json"
