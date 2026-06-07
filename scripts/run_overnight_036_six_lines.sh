#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/run_overnight_036_six_lines.sh --run
       scripts/run_overnight_036_six_lines.sh --dry-run

Six-line overnight package for item 036+.

Modes:
  --run      Launch all configured lines and wait for rollup.
  --dry-run  Print the resolved configuration without launching jobs.
  --help     Show this help text.

Useful environment overrides:
  RUN_ROOT, DEADLINE_HOUR_UTC, POLL_SECONDS
  T2_STEPS, T2_TRAIN_INSTANCES, T2_EVAL_INSTANCES, T2_L4_INSTANCES
  T2_BATCH_SIZE, T2_HIDDEN_DIM, T2_EVAL_EVERY, T2_GENERATION_WORKERS
  T2_GPUS, LINE2_DEVICE, LINE6_N_INSTANCES, UV_BIN, PYTHON_BIN
EOF
}

MODE=${1:-}
case "$MODE" in
  --run) ;;
  --dry-run) ;;
  --help|-h) usage; exit 0 ;;
  "") usage; exit 2 ;;
  *) echo "unknown mode: $MODE" >&2; usage >&2; exit 2 ;;
esac

UV_BIN=${UV_BIN:-$HOME/.local/bin/uv}
PYTHON_BIN=${PYTHON_BIN:-.venv/bin/python}
RUN_ROOT=${RUN_ROOT:-results/overnight_036_$(date -u +%Y%m%dT%H%M%SZ)}
DEADLINE_HOUR_UTC=${DEADLINE_HOUR_UTC:-6}
POLL_SECONDS=${POLL_SECONDS:-900}

T2_STEPS=${T2_STEPS:-60000}
T2_TRAIN_INSTANCES=${T2_TRAIN_INSTANCES:-16384}
T2_EVAL_INSTANCES=${T2_EVAL_INSTANCES:-1024}
T2_L4_INSTANCES=${T2_L4_INSTANCES:-512}
T2_BATCH_SIZE=${T2_BATCH_SIZE:-512}
T2_HIDDEN_DIM=${T2_HIDDEN_DIM:-256}
T2_LR=${T2_LR:-0.0003}
T2_EVAL_EVERY=${T2_EVAL_EVERY:-1000}
T2_MIN_STEPS=${T2_MIN_STEPS:-5000}
T2_GENERATION_WORKERS=${T2_GENERATION_WORKERS:-8}
T2_FUSE_MIN_LOSS_DROP=${T2_FUSE_MIN_LOSS_DROP:-0.01}
T2_GPUS=${T2_GPUS:-0,1,2,3}
LINE2_DEVICE=${LINE2_DEVICE:-cuda:3}
LINE6_N_INSTANCES=${LINE6_N_INSTANCES:-200}
IFS=, read -r T2_GPU_SEED102_R32 T2_GPU_SEED137_R32 T2_GPU_SEED256_R32 T2_GPU_SEED102_R16 <<< "$T2_GPUS"
if [[ -z "${T2_GPU_SEED102_R32:-}" || -z "${T2_GPU_SEED137_R32:-}" || -z "${T2_GPU_SEED256_R32:-}" || -z "${T2_GPU_SEED102_R16:-}" ]]; then
  echo "T2_GPUS must provide four comma-separated CUDA device indices, e.g. T2_GPUS=0,1,6,7" >&2
  exit 2
fi

if [[ "$MODE" == "--dry-run" ]]; then
  cat <<EOF
run_root=$RUN_ROOT
deadline_hour_utc=$DEADLINE_HOUR_UTC
poll_seconds=$POLL_SECONDS
t2_steps=$T2_STEPS
t2_train_instances=$T2_TRAIN_INSTANCES
t2_eval_instances=$T2_EVAL_INSTANCES
t2_l4_instances=$T2_L4_INSTANCES
t2_batch_size=$T2_BATCH_SIZE
t2_hidden_dim=$T2_HIDDEN_DIM
t2_eval_every=$T2_EVAL_EVERY
t2_generation_workers=$T2_GENERATION_WORKERS
t2_gpus=$T2_GPUS
line2_device=$LINE2_DEVICE
line6_n_instances=$LINE6_N_INSTANCES
lines=line1_t2_four_runs,line2_stage_a_gate,line3_blocked_cached_push,line4_w3_merge_watch,line5_trm_quarantine,line6_9x9_audit
EOF
  exit 0
fi

mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/line1_t2" "$RUN_ROOT/line2_stage_a" "$RUN_ROOT/line3_w3_push" "$RUN_ROOT/line4_w3_50x2" "$RUN_ROOT/line5_trm" "$RUN_ROOT/line6_9x9"

declare -a PIDS=()
declare -a NAMES=()

launch() {
  local name=$1
  shift
  local log="$RUN_ROOT/logs/${name}.log"
  local status_file="$RUN_ROOT/logs/${name}.status"
  {
    echo "[{\"event\":\"start\",\"name\":\"$name\",\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}]"
    "$@"
  } > "$log" 2>&1 &
  local pid=$!
  echo "$pid" > "$RUN_ROOT/logs/${name}.pid"
  PIDS+=("$pid")
  NAMES+=("$name")
  echo "launched $name pid=$pid log=$log status=$status_file"
}

train_t2() {
  local name=$1
  local seed=$2
  local gpu=$3
  local recurrence_steps=$4
  local out_dir="$RUN_ROOT/line1_t2/${name}"
  mkdir -p "$out_dir"
  launch "$name" env CUDA_VISIBLE_DEVICES="$gpu" "$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.train_recurrent_operator \
    --output-dir "$out_dir" \
    --seed "$seed" \
    --device cuda:0 \
    --train-instances "$T2_TRAIN_INSTANCES" \
    --eval-instances "$T2_EVAL_INSTANCES" \
    --l4-instances "$T2_L4_INSTANCES" \
    --steps "$T2_STEPS" \
    --batch-size "$T2_BATCH_SIZE" \
    --hidden-dim "$T2_HIDDEN_DIM" \
    --recurrence-steps "$recurrence_steps" \
    --lr "$T2_LR" \
    --generation-workers "$T2_GENERATION_WORKERS" \
    --eval-every "$T2_EVAL_EVERY" \
    --forced-loss focal \
    --focal-gamma 2.0 \
    --fuse-step 100 \
    --fuse-min-loss-drop "$T2_FUSE_MIN_LOSS_DROP" \
    --min-steps "$T2_MIN_STEPS" \
    --cosine-schedule
}

echo "overnight run root: $RUN_ROOT"

train_t2 seed102_r32 102 "$T2_GPU_SEED102_R32" 32
train_t2 seed137_r32 137 "$T2_GPU_SEED137_R32" 32
train_t2 seed256_r32 256 "$T2_GPU_SEED256_R32" 32
train_t2 seed102_r16 102 "$T2_GPU_SEED102_R16" 16

ACCEPTANCE_DIRS="$RUN_ROOT/line1_t2/seed102_r32,$RUN_ROOT/line1_t2/seed137_r32,$RUN_ROOT/line1_t2/seed256_r32"

launch line2_stage_a_gate "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_six_lines line2-watch \
  --out-dir "$RUN_ROOT/line2_stage_a" \
  --acceptance-dirs "$ACCEPTANCE_DIRS" \
  --deadline-hour "$DEADLINE_HOUR_UTC" \
  --poll-seconds "$POLL_SECONDS" \
  --python-bin "$PYTHON_BIN" \
  --device "$LINE2_DEVICE"

launch line3_cached_push_survival "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_six_lines block \
  --out "$RUN_ROOT/line3_w3_push/line3_cached_push_survival.json" \
  --line line3 \
  --status STRUCTURED_PUSH_SURVIVAL_NOT_IMPLEMENTED \
  --reason "No audited cached-GDN structured push/pop decoder exists yet; perturbation survival is not acceptable evidence for this line." \
  --evidence experiments/w3_qwen35_probe.py

launch line4_w3_50x2_merge_watch "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_six_lines line4-watch \
  --out-dir "$RUN_ROOT/line4_w3_50x2" \
  --w3-output-dir results/w3_qwen35_probe \
  --deadline-hour "$DEADLINE_HOUR_UTC" \
  --poll-seconds "$POLL_SECONDS" \
  --python-bin "$PYTHON_BIN"

launch line5_trm_defensive env CUDA_VISIBLE_DEVICES=6 "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_six_lines line5-trm \
  --out-dir "$RUN_ROOT/line5_trm" \
  --quarantine-dir artifacts/trm_defensive

launch line6_9x9_audit env CUDA_VISIBLE_DEVICES=7 "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_six_lines line6-audit \
  --out-dir "$RUN_ROOT/line6_9x9" \
  --n-instances "$LINE6_N_INSTANCES"

exit_code=0
for index in "${!PIDS[@]}"; do
  pid=${PIDS[$index]}
  name=${NAMES[$index]}
  if wait "$pid"; then
    echo "0" > "$RUN_ROOT/logs/${name}.status"
  else
    code=$?
    echo "$code" > "$RUN_ROOT/logs/${name}.status"
    exit_code=1
  fi
done

"$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_six_lines rollup --run-root "$RUN_ROOT" > "$RUN_ROOT/logs/rollup.log" 2>&1 || exit_code=1
echo "overnight complete: $RUN_ROOT"
exit "$exit_code"