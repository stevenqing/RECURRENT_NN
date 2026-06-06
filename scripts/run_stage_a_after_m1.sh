#!/usr/bin/env bash
set -euo pipefail

repo="/home/aiscuser/RECURRENT_NN"
cd "$repo"

log_dir="${STAGE_A_LOG_DIR:-/tmp/stage_a_backtrack}"
mkdir -p "$log_dir"
main_log="$log_dir/run.log"

artifact_dir="${STAGE_A_ARTIFACT_DIR:-artifacts/stage_a}"
operator_ckpt="${STAGE_A_OPERATOR_CKPT:-$artifact_dir/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt}"
bridge_decoder="${STAGE_A_BRIDGE_DECODER:-$artifact_dir/item142_factored_cell_digit_decoder_depth8_D128.pt}"
teacher_trace="${STAGE_A_TEACHER_TRACE:-$artifact_dir/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl}"
output_dir="${STAGE_A_OUTPUT_DIR:-results/stage_a_backtrack}"
expected_m1_cells="${M1_EXPECTED_CELLS:-144}"
reconstruct_missing="${STAGE_A_RECONSTRUCT_MISSING:-1}"

timestamp() { date -Iseconds; }
log() { printf '%s %s\n' "$(timestamp)" "$*" | tee -a "$main_log"; }

count_m1_cells() {
  find results/gru_stack_grid_fair -path '*/cell_*/results.json' 2>/dev/null | wc -l
}

first_match() {
  find /home/aiscuser -path /home/aiscuser/RECURRENT_NN/.venv -prune -o -type f "$@" -print 2>/dev/null | head -n 1
}

resolve_artifacts() {
  if [[ ! -f "$operator_ckpt" ]]; then
    found="$(first_match -name 'recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt')"
    if [[ -n "$found" ]]; then
      operator_ckpt="$found"
    fi
  fi
  if [[ -z "$bridge_decoder" || ! -f "$bridge_decoder" ]]; then
    found="$(first_match '(' -iname '*item*142*decoder*.pt' -o -iname '*bridge*decoder*.pt' -o -iname '*decoder*.pt' ')')"
    if [[ -n "$found" ]]; then
      bridge_decoder="$found"
    fi
  fi
  if [[ ! -f "$teacher_trace" && ! -f "$repo/$teacher_trace" ]]; then
    found="$(first_match -name 'internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl')"
    if [[ -n "$found" ]]; then
      teacher_trace="$found"
    fi
  fi
}

m1_pid="${M1_PID:-}"
if [[ -z "$m1_pid" ]]; then
  m1_pid="$(pgrep -f 'bash /tmp/continue_fair_gru_6gpu_and_commit.sh' | head -n 1 || true)"
fi

log "Stage A deferred launcher armed"
log "operator_ckpt=$operator_ckpt"
log "bridge_decoder=$bridge_decoder"
log "teacher_trace=$teacher_trace"
log "output_dir=$output_dir"
log "artifact_dir=$artifact_dir"
log "current_m1_cells=$(count_m1_cells)/$expected_m1_cells"

if [[ -n "$m1_pid" ]]; then
  log "waiting for M1 supervisor pid=$m1_pid"
  tail --pid="$m1_pid" -f /dev/null || true
  log "M1 supervisor exited"
fi

m1_cells="$(count_m1_cells)"
log "post-wait M1 cells=$m1_cells/$expected_m1_cells"
if [[ "$m1_cells" -lt "$expected_m1_cells" ]]; then
  log "M1 incomplete; refusing to start Stage A"
  exit 10
fi

if [[ "$reconstruct_missing" == "1" && ( ! -f "$operator_ckpt" || ! -f "$bridge_decoder" || ! -f "$teacher_trace" ) ]]; then
  log "reconstructing missing Stage A artifacts"
  reconstruct_device="${STAGE_A_RECONSTRUCT_DEVICE:-cpu}"
  if [[ "$reconstruct_device" == cuda:* ]]; then
    CUDA_VISIBLE_DEVICES="${STAGE_A_RECONSTRUCT_GPU:-6}" ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.reconstruct_stage_a_artifacts \
      --output-dir "$artifact_dir" \
      --n-instances "${STAGE_A_RECONSTRUCT_INSTANCES:-1024}" \
      --operator-steps "${STAGE_A_RECONSTRUCT_OPERATOR_STEPS:-300}" \
      --bridge-steps "${STAGE_A_RECONSTRUCT_BRIDGE_STEPS:-500}" \
      --batch-size "${STAGE_A_RECONSTRUCT_BATCH_SIZE:-256}" \
      --device "$reconstruct_device" >"$log_dir/reconstruct.log" 2>&1
  else
    ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.reconstruct_stage_a_artifacts \
    --output-dir "$artifact_dir" \
    --n-instances "${STAGE_A_RECONSTRUCT_INSTANCES:-1024}" \
    --operator-steps "${STAGE_A_RECONSTRUCT_OPERATOR_STEPS:-300}" \
    --bridge-steps "${STAGE_A_RECONSTRUCT_BRIDGE_STEPS:-500}" \
    --batch-size "${STAGE_A_RECONSTRUCT_BATCH_SIZE:-256}" \
      --device "$reconstruct_device" >"$log_dir/reconstruct.log" 2>&1
  fi
fi

resolve_artifacts
log "resolved_operator_ckpt=$operator_ckpt"
log "resolved_bridge_decoder=$bridge_decoder"
log "resolved_teacher_trace=$teacher_trace"

log "running Stage A preflight"
if ! ~/.local/bin/uv run --python .venv/bin/python python -m experiments.stage_a_backtrack_loop \
  --mode preflight \
  --operator-ckpt "$operator_ckpt" \
  --bridge-decoder "$bridge_decoder" \
  --teacher-trace "$teacher_trace" \
  --output-dir "$output_dir" >"$log_dir/preflight.log" 2>&1; then
  log "Stage A preflight failed; see $log_dir/preflight.log and $output_dir/preflight.json"
  exit 20
fi

log "starting Stage A 8-shard overnight grid"
for i in 0 1 2 3 4 5 6 7; do
  mkdir -p "$output_dir/shard_$i"
  CUDA_VISIBLE_DEVICES="$i" ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.stage_a_backtrack_loop \
    --mode overnight \
    --num-shards 8 \
    --shard-index "$i" \
    --operator-ckpt "$operator_ckpt" \
    --bridge-decoder "$bridge_decoder" \
    --teacher-trace "$teacher_trace" \
    --output-dir "$output_dir/shard_$i" \
    --device cuda:0 >"$log_dir/shard_$i.log" 2>&1 &
done
wait

log "merging Stage A shards"
~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_stage_a --input-dir "$output_dir" >"$log_dir/merge.log" 2>&1
~/.local/bin/uv run --python .venv/bin/python python -m analysis.stage_a_report --output-dir "$output_dir" >"$log_dir/report.log" 2>&1

log "committing Stage A outputs"
git add experiments/stage_a_backtrack_loop.py analysis/merge_stage_a.py analysis/stage_a_report.py scripts/run_stage_a_after_m1.sh "$output_dir" || true
git commit -m "Add Stage A backtracking overnight results" >>"$log_dir/git.log" 2>&1 || true
git push origin main >>"$log_dir/git.log" 2>&1 || true
log "Stage A deferred launcher finished"