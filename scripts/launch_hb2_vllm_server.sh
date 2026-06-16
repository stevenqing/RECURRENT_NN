#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="${RUN_ROOT:-results/kvcache_matched_budget_v0/hb2_vllm_servers/qwen3_4b_gpu${GPU:-4}_$(date -u +%Y%m%dT%H%M%SZ)}"
GPU="${GPU:-4}"
PORT="${PORT:-8012}"
HOST="${HOST:-127.0.0.1}"
MODEL="${MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
DTYPE="${DTYPE:-float32}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.35}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-}"
VLLM_PY="${VLLM_PY:-.venv-vllm/bin/python}"
mkdir -p "$RUN_ROOT"
LOG="$RUN_ROOT/server.log"
PID_FILE="$RUN_ROOT/server.pid"
ENV_FILE="$RUN_ROOT/env.sh"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE")"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "already running: pid=$old_pid log=$LOG" >&2
    exit 1
  fi
fi

cat > "$ENV_FILE" <<EOF
GPU=$GPU
HOST=$HOST
PORT=$PORT
MODEL=$MODEL
DTYPE=$DTYPE
MAX_MODEL_LEN=$MAX_MODEL_LEN
GPU_MEMORY_UTILIZATION=$GPU_MEMORY_UTILIZATION
MAX_NUM_SEQS=$MAX_NUM_SEQS
MAX_NUM_BATCHED_TOKENS=$MAX_NUM_BATCHED_TOKENS
VLLM_PY=$VLLM_PY
EOF

extra_args=()
if [[ -n "$MAX_NUM_SEQS" ]]; then
  extra_args+=(--max-num-seqs "$MAX_NUM_SEQS")
fi
if [[ -n "$MAX_NUM_BATCHED_TOKENS" ]]; then
  extra_args+=(--max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS")
fi

nohup env CUDA_VISIBLE_DEVICES="$GPU" "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
  --host "$HOST" \
  --port "$PORT" \
  --model "$MODEL" \
  --served-model-name "$MODEL" \
  --dtype "$DTYPE" \
  --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  "${extra_args[@]}" \
  --trust-remote-code \
  --disable-uvicorn-access-log > "$LOG" 2>&1 &

pid=$!
echo "$pid" > "$PID_FILE"
echo "launched vLLM pid=$pid base_url=http://$HOST:$PORT/v1 log=$LOG env=$ENV_FILE"
