#!/usr/bin/env bash
set -euo pipefail

BASELINES="${BASELINES:-best_of_n,lfs,tot_rap}"
SHARDS="${SHARDS:-8}"
GPUS="${GPUS:-4}"
INSTANCES="${INSTANCES:-64}"
TASKS="${TASKS:-sudoku,futoshiki,graph_color}"
BUDGET_SCALES="${BUDGET_SCALES:-0.25,0.5,1,2,4}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"

run_baseline() {
  local baseline="$1"
  case "$baseline" in
    best_of_n)
      ROOT="${BEST_OF_N_ROOT:-results/kvcache_matched_budget_v0/hb2_best_of_n/full_grid_n64_gpu0_3_x2_batched}" \
      SHARDS="$SHARDS" GPUS="$GPUS" INSTANCES="$INSTANCES" TASKS="$TASKS" BUDGET_SCALES="$BUDGET_SCALES" PY="$PY" \
        scripts/launch_hb2_best_of_n_full_grid.sh
      ;;
    lfs)
      ROOT="${LFS_ROOT:-results/kvcache_matched_budget_v0/hb2_lfs/full_grid_n64_gpu0_3_x2_batched}" \
      SHARDS="$SHARDS" GPUS="$GPUS" INSTANCES="$INSTANCES" TASKS="$TASKS" BUDGET_SCALES="$BUDGET_SCALES" PY="$PY" \
        scripts/launch_hb2_lfs_full_grid.sh
      ;;
    tot_rap)
      ROOT="${TOT_RAP_ROOT:-results/kvcache_matched_budget_v0/hb2_tot_rap/full_grid_n64_gpu0_3_x2_batched}" \
      SHARDS="$SHARDS" GPUS="$GPUS" INSTANCES="$INSTANCES" TASKS="$TASKS" BUDGET_SCALES="$BUDGET_SCALES" PY="$PY" \
        scripts/launch_hb2_tot_rap_full_grid.sh
      ;;
    *)
      echo "unknown HB-2 baseline: $baseline" >&2
      return 2
      ;;
  esac
}

IFS=',' read -r -a baseline_list <<< "$BASELINES"
for baseline in "${baseline_list[@]}"; do
  echo "[hb2] starting $baseline at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  run_baseline "$baseline"
  echo "[hb2] finished $baseline at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
