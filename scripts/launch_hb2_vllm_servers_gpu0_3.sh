#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/kvcache_matched_budget_v0/hb2_vllm_servers/gpu0_3_qwen3_4b}"
GPUS="${GPUS:-0,1,2,3}"
BASE_PORT="${BASE_PORT:-8010}"
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.80}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
DTYPE="${DTYPE:-float32}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-256}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-65536}"
mkdir -p "$ROOT"

IFS=',' read -r -a gpu_list <<< "$GPUS"
for offset in "${!gpu_list[@]}"; do
  gpu="${gpu_list[$offset]}"
  port=$((BASE_PORT + offset))
  run_root="$ROOT/gpu${gpu}_port${port}"
  RUN_ROOT="$run_root" \
  GPU="$gpu" \
  PORT="$port" \
  MODEL="$MODEL" \
  GPU_MEMORY_UTILIZATION="$GPU_MEMORY_UTILIZATION" \
  MAX_MODEL_LEN="$MAX_MODEL_LEN" \
  DTYPE="$DTYPE" \
  MAX_NUM_SEQS="$MAX_NUM_SEQS" \
  MAX_NUM_BATCHED_TOKENS="$MAX_NUM_BATCHED_TOKENS" \
    scripts/launch_hb2_vllm_server.sh
  echo "gpu=$gpu port=$port base_url=http://127.0.0.1:$port/v1 run_root=$run_root"
done
