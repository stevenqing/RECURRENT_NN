#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-p2b_graph_color_overnight_v0_$(date -u +%Y%m%dT%H%M%SZ)}"
ROOT="${ROOT:-results/kvcache_overnight_v0/p2b_graph_color}"
UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
GPUS=(0 1 2 3)
mkdir -p "$ROOT/logs" "$ROOT/reason_couple_shards" "$ROOT/cost_shards"
MANIFEST="$ROOT/launch_manifest_${RUN_ID}.jsonl"

echo_json() {
  python - "$@" <<'PY'
import json, sys
keys = sys.argv[1::2]
vals = sys.argv[2::2]
print(json.dumps(dict(zip(keys, vals)), sort_keys=True))
PY
}

launch_reason_couple() {
  for shard in "${!GPUS[@]}"; do
    gpu="${GPUS[$shard]}"
    output="$ROOT/reason_couple_shards/shard_${shard}.json"
    checkpoint="$ROOT/reason_couple_shards/shard_${shard}_checkpoint.json"
    log="$ROOT/logs/reason_couple_shard_${shard}.log"
    echo_json run_id "$RUN_ID" job p2b_reason_couple gpu "$gpu" shard_index "$shard" output_path "$output" checkpoint_path "$checkpoint" log_path "$log" status launched >> "$MANIFEST"
    CUDA_VISIBLE_DEVICES="$gpu" "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.kvcache_backjump_lora eval-search \
      --model "$MODEL" --dtype fp32 --device cuda \
      --output "$output" --checkpoint-path "$checkpoint" --resume \
      --bins v14_p04:14:0.4,v16_p04:16:0.4,v18_p04:18:0.4,v20_p04:20:0.4 \
      --r-values 2,4,8,16 \
      --conditions isolation,autonomous \
      --backjump-policies conflict_cot,chrono,oracle,random \
      --n-instances 40 --max-selected-instances 180 --scan-limit 5000 --min-backtracks 4 --node-cap 700 --call-cap 220 \
      --cot-max-new-tokens 256 --cot-fallback fail --cot-invalid-repair none --cot-prompt-style per_color --cot-trace-samples 4 \
      --num-shards 4 --shard-index "$shard" \
      > "$log" 2>&1 &
    echo $! > "$ROOT/reason_couple_shards/shard_${shard}.pid"
  done
  wait
  "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.kvcache_backjump_lora merge-search \
    --output "$ROOT/merged_p2b_reason_couple.json" \
    --inputs "$ROOT"/reason_couple_shards/shard_*.json \
    > "$ROOT/logs/merge_reason_couple.log" 2>&1
  echo_json run_id "$RUN_ID" job p2b_reason_couple_merged output_path "$ROOT/merged_p2b_reason_couple.json" log_path "$ROOT/logs/merge_reason_couple.log" status complete >> "$MANIFEST"
}

launch_cost_bin() {
  local vertices="$1"
  local label="v${vertices}_p04"
  for shard in "${!GPUS[@]}"; do
    gpu="${GPUS[$shard]}"
    output="$ROOT/cost_shards/${label}_shard_${shard}.json"
    checkpoint="$ROOT/cost_shards/${label}_shard_${shard}_checkpoint.json"
    log="$ROOT/logs/cost_${label}_shard_${shard}.log"
    echo_json run_id "$RUN_ID" job "p2b_cost_${label}" gpu "$gpu" shard_index "$shard" output_path "$output" checkpoint_path "$checkpoint" log_path "$log" status launched >> "$MANIFEST"
    CUDA_VISIBLE_DEVICES="$gpu" "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.kvcache_graph_color_search \
      --model "$MODEL" --dtype fp32 --device cuda \
      --output "$output" --checkpoint-path "$checkpoint" --resume \
      --num-vertices "$vertices" --edge-probability 0.4 --difficulty-bin-label "$label" \
      --n-instances 24 --scan-limit 1000 --min-backtracks 4 --node-cap 160 --call-cap 160 \
      --r-values 2,4,8,16 \
      --arms A_cache_oracle_search,C_incontext_oracle_search \
      --invalid-branch-mode fail --invalid-backtrack-mode fail \
      --num-shards 4 --shard-index "$shard" \
      > "$log" 2>&1 &
    echo $! > "$ROOT/cost_shards/${label}_shard_${shard}.pid"
  done
  wait
  echo_json run_id "$RUN_ID" job "p2b_cost_${label}" status shards_complete output_path "$ROOT/cost_shards" >> "$MANIFEST"
}

launch_reason_couple
launch_cost_bin 20
launch_cost_bin 22

echo_json run_id "$RUN_ID" job p2b_graph_color_overnight status complete root "$ROOT" manifest "$MANIFEST" >> "$MANIFEST"
