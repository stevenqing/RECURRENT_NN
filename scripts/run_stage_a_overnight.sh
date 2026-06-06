#!/usr/bin/env bash
set -euo pipefail

repo="/home/aiscuser/RECURRENT_NN"
cd "$repo"

log_dir="${STAGE_A_LOG_DIR:-/tmp/stage_a_backtrack}"
artifact_dir="${STAGE_A_ARTIFACT_DIR:-artifacts/stage_a}"
output_dir="${STAGE_A_OUTPUT_DIR:-results/stage_a_backtrack}"
mkdir -p "$log_dir" "$artifact_dir" "$output_dir"

main_log="$log_dir/overnight.log"
lock_dir="$log_dir/overnight.lock"
operator_ckpt="${STAGE_A_OPERATOR_CKPT:-$artifact_dir/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt}"
bridge_decoder="${STAGE_A_BRIDGE_DECODER:-$artifact_dir/item142_factored_cell_digit_decoder_depth8_D128.pt}"
teacher_trace="${STAGE_A_TEACHER_TRACE:-$artifact_dir/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl}"

timestamp() { date -Iseconds; }
log() { printf '%s %s\n' "$(timestamp)" "$*" | tee -a "$main_log"; }

if ! mkdir "$lock_dir" 2>/dev/null; then
  log "another Stage A overnight pipeline appears to be running: $lock_dir"
  exit 9
fi
trap 'rmdir "$lock_dir" 2>/dev/null || true' EXIT

artifact_ready() {
  [[ -s "$operator_ckpt" && -s "$bridge_decoder" && -s "$teacher_trace" && -s "$artifact_dir/manifest.json" ]]
}

log "Stage A overnight pipeline started"
log "artifact_dir=$artifact_dir"
log "output_dir=$output_dir"
log "operator_ckpt=$operator_ckpt"
log "bridge_decoder=$bridge_decoder"
log "teacher_trace=$teacher_trace"

if artifact_ready; then
  log "Stage A reconstructed artifacts already present; skipping reconstruction"
else
  log "Stage A artifacts incomplete; reconstructing now"
  reconstruct_device="${STAGE_A_RECONSTRUCT_DEVICE:-cpu}"
  reconstruct_cmd=(~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.reconstruct_stage_a_artifacts
    --output-dir "$artifact_dir"
    --n-instances "${STAGE_A_RECONSTRUCT_INSTANCES:-1024}"
    --operator-steps "${STAGE_A_RECONSTRUCT_OPERATOR_STEPS:-300}"
    --bridge-steps "${STAGE_A_RECONSTRUCT_BRIDGE_STEPS:-500}"
    --batch-size "${STAGE_A_RECONSTRUCT_BATCH_SIZE:-256}"
    --device "$reconstruct_device")
  if [[ "$reconstruct_device" == cuda:* ]]; then
    CUDA_VISIBLE_DEVICES="${STAGE_A_RECONSTRUCT_GPU:-6}" "${reconstruct_cmd[@]}" >"$log_dir/reconstruct.log" 2>&1
  else
    "${reconstruct_cmd[@]}" >"$log_dir/reconstruct.log" 2>&1
  fi
  log "Stage A reconstruction command finished"
fi

if ! artifact_ready; then
  log "Stage A artifacts still incomplete after reconstruction"
  ls -lh "$artifact_dir" | tee -a "$main_log" || true
  exit 20
fi

log "Stage A artifacts ready; running preflight"
~/.local/bin/uv run --python .venv/bin/python python -m experiments.stage_a_backtrack_loop \
  --mode preflight \
  --operator-ckpt "$operator_ckpt" \
  --bridge-decoder "$bridge_decoder" \
  --teacher-trace "$teacher_trace" \
  --output-dir "$output_dir" >"$log_dir/preflight_before_m1.log" 2>&1

log "preflight passed; handing off to post-M1 Stage A launcher"
STAGE_A_ARTIFACT_DIR="$artifact_dir" \
STAGE_A_OPERATOR_CKPT="$operator_ckpt" \
STAGE_A_BRIDGE_DECODER="$bridge_decoder" \
STAGE_A_TEACHER_TRACE="$teacher_trace" \
STAGE_A_OUTPUT_DIR="$output_dir" \
STAGE_A_RECONSTRUCT_MISSING=0 \
STAGE_A_LOG_DIR="$log_dir" \
bash scripts/run_stage_a_after_m1.sh

log "Stage A overnight pipeline finished"