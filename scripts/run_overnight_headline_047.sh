#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/run_overnight_headline_047.sh --run
       scripts/run_overnight_headline_047.sh --dry-run

Overnight 047: deep-band Track A headline separation, Track B close diagnostic,
Qwen3.5 D1 decode, and D3 mining/frontier audit.

Useful overrides:
  RUN_ROOT, UV_BIN, PYTHON_BIN, TARGET_PER_BIN, MINING_WORKERS, MINING_MAX_CHUNKS
  LINE1_GPUS, LINE2_GPU, LINE3_GPU, LINE4_GPU, SKIP_PREREGISTER
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
RUN_ROOT=${RUN_ROOT:-results/overnight_047_headline_$(date -u +%Y%m%dT%H%M%SZ)}
TARGET_PER_BIN=${TARGET_PER_BIN:-64}
MINING_WORKERS=${MINING_WORKERS:-32}
MINING_ATTEMPTS_PER_CHUNK=${MINING_ATTEMPTS_PER_CHUNK:-64}
MINING_MAX_CHUNKS=${MINING_MAX_CHUNKS:-256}
LINE1_GPUS=${LINE1_GPUS:-0,1,2,3}
LINE2_GPU=${LINE2_GPU:-5}
LINE3_GPU=${LINE3_GPU:-4}
LINE4_GPU=${LINE4_GPU:-6}
TRACK_B_CHECKPOINT=${TRACK_B_CHECKPOINT:-results/track_b_trm_retry_seed102_ddp8_sharded_20260608T114308Z/seed102_ddp8/trm_operator_seed102.pt}
QWEN35_SNAPSHOT=${QWEN35_SNAPSHOT:-}
SKIP_PREREGISTER=${SKIP_PREREGISTER:-0}

if [[ "$MODE" == "--dry-run" ]]; then
  cat <<EOF
run_root=$RUN_ROOT
target_per_bin=$TARGET_PER_BIN
mining_workers=$MINING_WORKERS
mining_attempts_per_chunk=$MINING_ATTEMPTS_PER_CHUNK
mining_max_chunks=$MINING_MAX_CHUNKS
line1_gpus=$LINE1_GPUS
line2_gpu=$LINE2_GPU
line3_gpu=$LINE3_GPU
line4_gpu=$LINE4_GPU
track_b_checkpoint=$TRACK_B_CHECKPOINT
qwen35_snapshot=$QWEN35_SNAPSHOT
skip_preregister=$SKIP_PREREGISTER
EOF
  exit 0
fi

mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/line1_headline" "$RUN_ROOT/line2_track_b_diagnostic" "$RUN_ROOT/line3_qwen_d1_decode" "$RUN_ROOT/line4_d3"

if [[ "$SKIP_PREREGISTER" != "1" ]]; then
  "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_headline preregister --run-root "$RUN_ROOT" >"$RUN_ROOT/logs/preregister.log" 2>&1
fi

declare -a PIDS=()
declare -a NAMES=()

launch() {
  local name=$1
  shift
  local log="$RUN_ROOT/logs/${name}.log"
  {
    echo "{\"event\":\"start\",\"name\":\"$name\",\"utc\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
    "$@"
  } > "$log" 2>&1 &
  local pid=$!
  echo "$pid" > "$RUN_ROOT/logs/${name}.pid"
  PIDS+=("$pid")
  NAMES+=("$name")
  echo "launched $name pid=$pid log=$log"
}

launch line1_headline env CUDA_VISIBLE_DEVICES="$LINE1_GPUS" "$UV_BIN" run --python "$PYTHON_BIN" python -u -m analysis.overnight_headline line1 \
  --out-dir "$RUN_ROOT/line1_headline" \
  --python-bin "$PYTHON_BIN" \
  --equivalence-gpu 0 \
  --target-per-bin "$TARGET_PER_BIN" \
  --workers "$MINING_WORKERS" \
  --attempts-per-chunk "$MINING_ATTEMPTS_PER_CHUNK" \
  --max-chunks "$MINING_MAX_CHUNKS"

launch line2_track_b_diagnostic env CUDA_VISIBLE_DEVICES="$LINE2_GPU" "$UV_BIN" run --python "$PYTHON_BIN" python -u -m analysis.track_b_forced_diagnostic \
  --out-dir "$RUN_ROOT/line2_track_b_diagnostic" \
  --checkpoint "$TRACK_B_CHECKPOINT" \
  --device cuda:0 \
  --generation-workers 4 \
  --tensorize-workers 4

launch line3_qwen_d1_decode env CUDA_VISIBLE_DEVICES="$LINE3_GPU" "$UV_BIN" run --python "$PYTHON_BIN" python -u -m analysis.qwen35_cache_push_pop_decode \
  --out-dir "$RUN_ROOT/line3_qwen_d1_decode" \
  --snapshot-path "$QWEN35_SNAPSHOT" \
  --device cuda:0 \
  --dtype bfloat16

launch line4_d3 env CUDA_VISIBLE_DEVICES="$LINE4_GPU" "$UV_BIN" run --python "$PYTHON_BIN" python -u -m analysis.overnight_headline d3 \
  --out-dir "$RUN_ROOT/line4_d3" \
  --target-per-bin "$TARGET_PER_BIN" \
  --workers "$MINING_WORKERS" \
  --attempts-per-chunk "$MINING_ATTEMPTS_PER_CHUNK" \
  --max-chunks "$MINING_MAX_CHUNKS"

launch overnight_monitor "$UV_BIN" run --python "$PYTHON_BIN" python -u -m analysis.monitor_overnight_progress \
  --run-root "$RUN_ROOT" \
  --interval-seconds 60

exit_code=0
for index in "${!PIDS[@]}"; do
  pid=${PIDS[$index]}
  name=${NAMES[$index]}
  if wait "$pid"; then
    echo 0 > "$RUN_ROOT/logs/${name}.status"
  else
    code=$?
    echo "$code" > "$RUN_ROOT/logs/${name}.status"
    exit_code=1
  fi
done

"$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.overnight_headline rollup --run-root "$RUN_ROOT" >"$RUN_ROOT/logs/rollup.log" 2>&1 || exit_code=1
echo "overnight complete: $RUN_ROOT"
exit "$exit_code"