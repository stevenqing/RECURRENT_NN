#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="${RUN_ROOT:-results/kvcache_matched_budget_v0/hb2_external_runs/gpu0_3_x2_batched_$(date -u +%Y%m%dT%H%M%SZ)}"
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

BASELINES="${BASELINES:-lfs,tot_rap,best_of_n}"
SHARDS="${SHARDS:-8}"
GPUS="${GPUS:-4}"
INSTANCES="${INSTANCES:-64}"
TASKS="${TASKS:-sudoku,futoshiki,graph_color}"
BUDGET_SCALES="${BUDGET_SCALES:-0.25,0.5,1,2,4}"
SAMPLE_BATCH_SIZE="${SAMPLE_BATCH_SIZE:-32}"
VALUE_BATCH_SIZE="${VALUE_BATCH_SIZE:-8}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
BEST_OF_N_ROOT="${BEST_OF_N_ROOT:-results/kvcache_matched_budget_v0/hb2_best_of_n/full_grid_n64_gpu0_3_x2_batched}"
LFS_ROOT="${LFS_ROOT:-results/kvcache_matched_budget_v0/hb2_lfs/full_grid_n64_gpu0_3_x2_batched}"
TOT_RAP_ROOT="${TOT_RAP_ROOT:-results/kvcache_matched_budget_v0/hb2_tot_rap/full_grid_n64_gpu0_3_x2_batched}"

cat > "$ENV_FILE" <<EOF
BASELINES=$BASELINES
SHARDS=$SHARDS
GPUS=$GPUS
INSTANCES=$INSTANCES
TASKS=$TASKS
BUDGET_SCALES=$BUDGET_SCALES
SAMPLE_BATCH_SIZE=$SAMPLE_BATCH_SIZE
VALUE_BATCH_SIZE=$VALUE_BATCH_SIZE
BEST_OF_N_ROOT=$BEST_OF_N_ROOT
LFS_ROOT=$LFS_ROOT
TOT_RAP_ROOT=$TOT_RAP_ROOT
EOF

nohup env \
  BASELINES="$BASELINES" \
  SHARDS="$SHARDS" \
  GPUS="$GPUS" \
  INSTANCES="$INSTANCES" \
  TASKS="$TASKS" \
  BUDGET_SCALES="$BUDGET_SCALES" \
  SAMPLE_BATCH_SIZE="$SAMPLE_BATCH_SIZE" \
  VALUE_BATCH_SIZE="$VALUE_BATCH_SIZE" \
  PY="$PY" \
  BEST_OF_N_ROOT="$BEST_OF_N_ROOT" \
  LFS_ROOT="$LFS_ROOT" \
  TOT_RAP_ROOT="$TOT_RAP_ROOT" \
  scripts/launch_hb2_external_full_grid.sh > "$LOG" 2>&1 &

pid=$!
echo "$pid" > "$PID_FILE"
echo "launched pid=$pid log=$LOG env=$ENV_FILE"
