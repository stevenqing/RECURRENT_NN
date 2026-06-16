#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="${RUN_ROOT:-results/kvcache_matched_budget_v0/hb2_external_runs/lfs_vllm_multiserver_$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$RUN_ROOT"
LOG="$RUN_ROOT/master.log"
PID_FILE="$RUN_ROOT/master.pid"
ENV_FILE="$RUN_ROOT/env.sh"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE")"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "already running: pid=$old_pid log=$LOG" >&2
    exit 1
  fi
fi

ROOT="${ROOT:-results/kvcache_matched_budget_v0/hb2_lfs/full_grid_n64_vllm_gpu0_3_multiserver}"
TASKS="${TASKS:-sudoku,futoshiki,graph_color}"
INSTANCES="${INSTANCES:-64}"
BUDGET_SCALES="${BUDGET_SCALES:-0.25,0.5,1,2,4}"
OPENAI_BASE_URLS="${OPENAI_BASE_URLS:-http://127.0.0.1:8010/v1,http://127.0.0.1:8011/v1,http://127.0.0.1:8012/v1,http://127.0.0.1:8013/v1}"
OPENAI_MODEL="${OPENAI_MODEL:-Qwen/Qwen3-4B-Instruct-2507}"
ACTIVE_ROWS="${ACTIVE_ROWS:-512}"
STATE_BATCH_SIZE="${STATE_BATCH_SIZE:-256}"
REQUEST_WORKERS="${REQUEST_WORKERS:-256}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-96}"
SHARDS="${SHARDS:-4}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"

cat > "$ENV_FILE" <<EOF
ROOT=$ROOT
TASKS=$TASKS
INSTANCES=$INSTANCES
BUDGET_SCALES=$BUDGET_SCALES
OPENAI_BASE_URLS=$OPENAI_BASE_URLS
OPENAI_MODEL=$OPENAI_MODEL
ACTIVE_ROWS=$ACTIVE_ROWS
STATE_BATCH_SIZE=$STATE_BATCH_SIZE
REQUEST_WORKERS=$REQUEST_WORKERS
MAX_NEW_TOKENS=$MAX_NEW_TOKENS
SHARDS=$SHARDS
PY=$PY
EOF

nohup env \
  ROOT="$ROOT" \
  TASKS="$TASKS" \
  INSTANCES="$INSTANCES" \
  BUDGET_SCALES="$BUDGET_SCALES" \
  OPENAI_BASE_URLS="$OPENAI_BASE_URLS" \
  OPENAI_MODEL="$OPENAI_MODEL" \
  ACTIVE_ROWS="$ACTIVE_ROWS" \
  STATE_BATCH_SIZE="$STATE_BATCH_SIZE" \
  REQUEST_WORKERS="$REQUEST_WORKERS" \
  MAX_NEW_TOKENS="$MAX_NEW_TOKENS" \
  SHARDS="$SHARDS" \
  PY="$PY" \
  scripts/launch_hb2_lfs_multistate_vllm_multi_server.sh > "$LOG" 2>&1 &

pid=$!
echo "$pid" > "$PID_FILE"
echo "launched pid=$pid log=$LOG env=$ENV_FILE"
