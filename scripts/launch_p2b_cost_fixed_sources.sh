#!/usr/bin/env bash
set -euo pipefail
RUN_ID="${RUN_ID:-p2b_cost_fixed_sources_v0_$(date -u +%Y%m%dT%H%M%SZ)}"
ROOT="${ROOT:-results/kvcache_overnight_v0/p2b_graph_color_cost_fixed}"
UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
GPUS=(0 1 2 3)
mkdir -p "$ROOT/logs" "$ROOT/cost_shards"
MANIFEST="$ROOT/launch_manifest_${RUN_ID}.jsonl"
echo_json(){ python - "$@" <<'PY'
import json,sys
print(json.dumps(dict(zip(sys.argv[1::2],sys.argv[2::2])),sort_keys=True))
PY
}
launch_bin(){
  local vertices="$1"
  local label="v${vertices}_p04"
  local source_file="$ROOT/${label%%_p04}_source_indices.json"
  if [[ "$vertices" == "20" ]]; then source_file="$ROOT/v20_source_indices.json"; fi
  if [[ "$vertices" == "22" ]]; then source_file="$ROOT/v22_source_indices.json"; fi
  for shard in "${!GPUS[@]}"; do
    gpu="${GPUS[$shard]}"
    output="$ROOT/cost_shards/${label}_shard_${shard}.json"
    checkpoint="$ROOT/cost_shards/${label}_shard_${shard}_checkpoint.json"
    log="$ROOT/logs/cost_${label}_shard_${shard}.log"
    echo_json run_id "$RUN_ID" job "p2b_cost_${label}_fixed" gpu "$gpu" shard_index "$shard" output_path "$output" checkpoint_path "$checkpoint" log_path "$log" source_index_file "$source_file" status launched >> "$MANIFEST"
    CUDA_VISIBLE_DEVICES="$gpu" "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.kvcache_graph_color_cost_from_sources \
      --model "$MODEL" --dtype fp32 --device cuda \
      --output "$output" --checkpoint-path "$checkpoint" --resume \
      --source-index-file "$source_file" --selection-source "fixed_source_indices_${label}" \
      --num-vertices "$vertices" --edge-probability 0.4 --difficulty-bin-label "$label" \
      --n-instances 24 --scan-limit 1000 --node-cap 160 --call-cap 160 \
      --r-values 2,4,8,16 --arms A_cache_oracle_search,C_incontext_oracle_search \
      --num-shards 4 --shard-index "$shard" > "$log" 2>&1 &
    echo $! > "$ROOT/cost_shards/${label}_shard_${shard}.pid"
  done
  wait
  echo_json run_id "$RUN_ID" job "p2b_cost_${label}_fixed" status shards_complete output_path "$ROOT/cost_shards" >> "$MANIFEST"
}
launch_bin 20
launch_bin 22
echo_json run_id "$RUN_ID" job p2b_cost_fixed_sources status complete root "$ROOT" manifest "$MANIFEST" >> "$MANIFEST"
