#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/aiscuser/RECURRENT_NN
VLLM_PY=/home/aiscuser/UI-S1/UI-S1/.venv-qwen35-vllm/bin/python
MODEL=/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
OUT="$ROOT/results/multiagent_overnight_gpu4_7/servers"
mkdir -p "$OUT"

for gpu in 4 5 6 7; do
  port=$((8100 + gpu))
  free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i "$gpu" | tr -d ' ')
  if (( free_mib < 24000 )); then
    echo "GPU${gpu} has only ${free_mib} MiB free; refusing to disturb existing work" >&2
    exit 2
  fi
  if curl -fsS --max-time 2 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1; then
    echo "GPU${gpu} endpoint already healthy on port ${port}"
    continue
  fi
  log="$OUT/gpu${gpu}_port${port}.log"
  pidfile="$OUT/gpu${gpu}_port${port}.pid"
  CUDA_VISIBLE_DEVICES="$gpu" nohup "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --served-model-name Qwen/Qwen3.5-4B \
    --host 127.0.0.1 \
    --port "$port" \
    --dtype bfloat16 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.22 \
    --max-num-seqs 8 \
    --enforce-eager \
    >"$log" 2>&1 &
  echo $! >"$pidfile"
  echo "launched GPU${gpu} pid=$(cat "$pidfile") port=${port} log=${log}"
done
