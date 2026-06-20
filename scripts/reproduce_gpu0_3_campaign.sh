#!/usr/bin/env bash
set -euo pipefail

# Sequential GPU0-3 reproduction campaign.
# Re-run safely: stages skip when their final artifacts already exist unless FORCE=1.

RUN_ROOT="${RUN_ROOT:-results/reproduction_gpu0_3_20260620}"
C12_ROOT="${C12_ROOT:-results/c1_2_architecture_restore_characterization/item162_repro_gpu0_3_20260620}"
UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
PY="${PY:-$UV_BIN run --python $PYTHON_BIN python}"
GPU_LIST="${GPU_LIST:-0,1,2,3}"
GPUS="${GPUS:-4}"
SHARDS="${SHARDS:-4}"
DECISION_SHARDS="${DECISION_SHARDS:-$SHARDS}"
GRAPH_SYMBOLIC_SHARDS="${GRAPH_SYMBOLIC_SHARDS:-$SHARDS}"
GRAPH_C1_SHARDS="${GRAPH_C1_SHARDS:-4}"
AC_SHARDS="${AC_SHARDS:-8}"
EXTERNAL_SHARDS="${EXTERNAL_SHARDS:-8}"
DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
RUN_EXTERNAL_FULL="${RUN_EXTERNAL_FULL:-0}"
HB2_BASELINES="${HB2_BASELINES:-lfs,tot_rap,best_of_n}"
HB2_TASKS="${HB2_TASKS:-sudoku,futoshiki,graph_color}"
HB2_BUDGET_SCALES="${HB2_BUDGET_SCALES:-0.25,0.5,1,2,4}"
HB2_INSTANCES="${HB2_INSTANCES:-64}"

DEFAULT_STAGES="env,gpu_check,manifest,exactness,item101_full_checkpoint,decision_probe,c1_2_mamba,ac_primary,graph_color_c1,graph_color_symbolic,external_registry,hb2_external_full,experiment_log"
STAGES="${STAGES:-$DEFAULT_STAGES}"
STATE_DIR="$RUN_ROOT/campaign_state"

log() {
  printf '[gpu0-3-repro] %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

run_cmd() {
  log "RUN $*"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  "$@"
}

run_shell() {
  log "RUN $*"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  bash -c "$*"
}

done_file() {
  [[ "$FORCE" != "1" && -s "$1" ]]
}

json_status_ok() {
  local path="$1"
  shift
  [[ -s "$path" ]] || return 1
  "$PYTHON_BIN" - "$path" "$@" <<'PY'
import json, sys
path = sys.argv[1]
allowed = set(sys.argv[2:])
try:
    payload = json.load(open(path, encoding="utf-8"))
except Exception:
    sys.exit(1)
status = str(payload.get("status", ""))
sys.exit(0 if status in allowed else 1)
PY
}

mark_stage() {
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  mkdir -p "$STATE_DIR"
  printf '{"stage":"%s","completed_at":"%s"}\n' "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATE_DIR/$1.done.json"
}

ensure_env() {
  if [[ ! -x "$UV_BIN" ]]; then
    echo "uv not found at $UV_BIN" >&2
    exit 2
  fi
  if [[ ! -x "$PYTHON_BIN" ]]; then
    run_cmd "$UV_BIN" venv .venv --python 3.10
  fi
  run_cmd "$UV_BIN" pip install --python "$PYTHON_BIN" -r requirements.txt huggingface_hub accelerate
}

stage_gpu_check() {
  mkdir -p "$RUN_ROOT"
  run_shell "nvidia-smi --query-gpu=index,name,memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits -i $GPU_LIST | tee '$RUN_ROOT/gpu0_3_preflight.csv'"
}

stage_manifest() {
  mkdir -p "$RUN_ROOT"
  run_shell "$PY - <<'PY'
import json, re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

run_root = Path('$RUN_ROOT')
rows = []
for item_path in sorted(Path('results/experiment_items').glob('item_*.json')):
    match = re.search(r'item_(\d+)', item_path.name)
    if not match:
        continue
    item = int(match.group(1))
    if item < 100 or item > 166:
        continue
    payload = json.loads(item_path.read_text(encoding='utf-8'))
    commands = payload.get('commands', [])
    real_commands = []
    for command_payload in commands:
        command = command_payload.get('command') if isinstance(command_payload, dict) else str(command_payload)
        command = command or ''
        if command and 'RECOVERED_FROM_RAW' not in command and 'NOT_AVAILABLE' not in command and 'MISSING_CLUSTER' not in command:
            real_commands.append(command)
    if item in {100, 101, 102, 105, 122, 123, 155, 162, 163, 164, 165, 166}:
        campaign_class = 'campaign_core_or_reconstructed'
    elif real_commands:
        campaign_class = 'executable_local_not_in_default_campaign'
    else:
        campaign_class = 'summary_only_or_cluster_missing'
    rows.append({
        'item': item,
        'file': item_path.name,
        'status': payload.get('status'),
        'real_command_count': len(real_commands),
        'campaign_class': campaign_class,
    })
classes = defaultdict(list)
for row in rows:
    classes[row['campaign_class']].append(row['item'])
manifest = {
    'schema_version': 'gpu0_3_reproduction_manifest_v0',
    'status': 'GPU0_3_REPRODUCTION_MANIFEST_COMPLETE',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'run_root': str(run_root),
    'gpu_scope': '0,1,2,3',
    'policy': 'Default campaign automates faithful executable gates and reconstructed core floor-paper reruns. Summary-only or cluster-missing historical items are recorded as blocked for faithful replay.',
    'class_summary': {key: value for key, value in sorted(classes.items())},
    'rows': rows,
}
run_root.mkdir(parents=True, exist_ok=True)
(run_root / 'reproduction_manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps({'path': str(run_root / 'reproduction_manifest.json'), 'status': manifest['status']}))
PY"
}

stage_exactness() {
  local root="$RUN_ROOT/exactness_gates"
  mkdir -p "$root"
  if ! json_status_ok "$root/item102_qwen3_bf16.json" KVCACHE_EXACTNESS_GATE_FAIL KVCACHE_EXACTNESS_GATE_PASS; then
    run_shell "CUDA_VISIBLE_DEVICES=0 $PY -m analysis.kvcache_exactness_gate --model Qwen/Qwen3-4B-Instruct-2507 --depth 16 --checkpoints 2,4,8,12 --tol 1e-3 --device cuda --dtype bf16 --out '$root/item102_qwen3_bf16.json'"
  fi
  if ! json_status_ok "$root/item102_qwen3_fp32_strict.json" KVCACHE_EXACTNESS_GATE_FAIL KVCACHE_EXACTNESS_GATE_PASS; then
    run_shell "CUDA_VISIBLE_DEVICES=0 $PY -m analysis.kvcache_exactness_gate --model Qwen/Qwen3-4B-Instruct-2507 --depth 16 --checkpoints 2,4,8,12 --tol 1e-5 --device cuda --dtype fp32 --out '$root/item102_qwen3_fp32_strict.json'"
  fi
  if ! json_status_ok "$root/item102_qwen3_fp32_tol1e3.json" KVCACHE_EXACTNESS_GATE_PASS; then
    run_shell "CUDA_VISIBLE_DEVICES=0 $PY -m analysis.kvcache_exactness_gate --model Qwen/Qwen3-4B-Instruct-2507 --depth 16 --checkpoints 2,4,8,12 --tol 1e-3 --device cuda --dtype fp32 --out '$root/item102_qwen3_fp32_tol1e3.json'"
  fi
  if ! json_status_ok "$root/item100_qwen35_bf16.json" KVCACHE_EXACTNESS_GATE_FAIL KVCACHE_EXACTNESS_GATE_PASS; then
    run_shell "CUDA_VISIBLE_DEVICES=1 $PY -m analysis.kvcache_exactness_gate --model Qwen/Qwen3.5-4B --depth 16 --checkpoints 2,4,8,12 --tol 1e-3 --device cuda --dtype bf16 --out '$root/item100_qwen35_bf16.json'"
  fi
}

stage_item101_full_checkpoint() {
  local root="$RUN_ROOT/exactness_gates"
  mkdir -p "$root"
  if ! json_status_ok "$root/item101_qwen35_full_checkpoint_bf16.json" KVCACHE_FULL_CHECKPOINT_GATE_FAIL KVCACHE_FULL_CHECKPOINT_GATE_PASS; then
    run_shell "CUDA_VISIBLE_DEVICES=1 $PY -m analysis.kvcache_full_checkpoint_gate --model Qwen/Qwen3.5-4B --depth 16 --checkpoints 2,4,8,12 --tol 1e-3 --device cuda --dtype bf16 --out '$root/item101_qwen35_full_checkpoint_bf16.json'"
  fi
  if ! json_status_ok "$root/item101_qwen35_full_checkpoint_fp32_tol1e3.json" KVCACHE_FULL_CHECKPOINT_GATE_FAIL KVCACHE_FULL_CHECKPOINT_GATE_PASS; then
    run_shell "CUDA_VISIBLE_DEVICES=1 $PY -m analysis.kvcache_full_checkpoint_gate --model Qwen/Qwen3.5-4B --depth 16 --checkpoints 2,4,8,12 --tol 1e-3 --device cuda --dtype fp32 --out '$root/item101_qwen35_full_checkpoint_fp32_tol1e3.json'"
  fi
}

stage_decision_probe() {
  local root="$RUN_ROOT/item105_decision_probe"
  mkdir -p "$root/shards"
  if json_status_ok "$root/merged_decision_probe.json" KVCACHE_DECISION_PROBE_COMPLETE; then
    log "SKIP decision_probe: $root/merged_decision_probe.json complete"
    return 0
  fi
  if ! json_status_ok "$root/points_collect.json" KVCACHE_DECISION_PROBE_POINTS_COMPLETE; then
    run_shell "$PY -m analysis.kvcache_decision_probe --output '$root/points_collect.json' --checkpoint-path '$root/points_collect_checkpoint.json' --points-path '$root/points_cache.json' --collect-only --km3-real-prompt results/kvcache_exactness/km3_real_graph_color_prompt_qwen3_fp32.json --model Qwen/Qwen3-4B-Instruct-2507 --seed 42 --scan-limit 5000 --max-selected-instances 200 --n-per-kind-level 30 --min-backtracks 4 --node-cap 500 --register-window 8 --bins v14_p04:14:0.4,v16_p04:16:0.4,v18_p04:18:0.4 --n-values 0,2,4,8,16,32 --progress-every-scan 100 --progress-every-selected 5 --device cuda --dtype fp32"
  fi
  for shard in $(seq 0 $((DECISION_SHARDS - 1))); do
    if json_status_ok "$root/shards/shard_${shard}.json" KVCACHE_DECISION_PROBE_COMPLETE; then
      continue
    fi
    gpu=$((shard % GPUS))
    run_shell "CUDA_VISIBLE_DEVICES=$gpu $PY -m analysis.kvcache_decision_probe --output '$root/shards/shard_${shard}.json' --checkpoint-path '$root/shards/shard_${shard}_checkpoint.json' --points-path '$root/points_cache.json' --km3-real-prompt results/kvcache_exactness/km3_real_graph_color_prompt_qwen3_fp32.json --model Qwen/Qwen3-4B-Instruct-2507 --seed 42 --scan-limit 5000 --max-selected-instances 200 --n-per-kind-level 30 --min-backtracks 4 --node-cap 500 --register-window 8 --bins v14_p04:14:0.4,v16_p04:16:0.4,v18_p04:18:0.4 --n-values 0,2,4,8,16,32 --batch-size 8 --resume --num-shards '$DECISION_SHARDS' --shard-index '$shard' --device cuda --dtype fp32 > '$root/shards/shard_${shard}.log' 2>&1" &
  done
  wait
  run_shell "$PY -m analysis.kvcache_decision_probe_merge --inputs '$root/shards/shard_*.json' --output '$root/merged_decision_probe.json' --n-values 0,2,4,8,16,32"
}

stage_c1_2_mamba() {
  mkdir -p "$C12_ROOT"
  local complete=1
  for gpu in 0 1 2 3; do
    if ! json_status_ok "$C12_ROOT/gpu${gpu}_real_mamba_depth_sweep.json" C1_2_GPU03_REPRO_LOCKED; then
      complete=0
    fi
  done
  if [[ "$FORCE" != "1" && "$complete" == "1" ]]; then
    log "SKIP c1_2_mamba: all GPU0-3 outputs complete"
    return 0
  fi
  for gpu in 0 1 2 3; do
    if [[ "$FORCE" != "1" ]] && json_status_ok "$C12_ROOT/gpu${gpu}_real_mamba_depth_sweep.json" C1_2_GPU03_REPRO_LOCKED; then
      continue
    fi
    run_shell "CUDA_VISIBLE_DEVICES=$gpu $PY -m analysis.c1_2_reproduce_mamba --device cuda:0 --cuda-visible-devices '$gpu' --output '$C12_ROOT/gpu${gpu}_real_mamba_depth_sweep.json' > '$C12_ROOT/gpu${gpu}.log' 2>&1" &
  done
  wait
}

stage_ac_primary() {
  local root="$RUN_ROOT/ac_primary_scaled_n64"
  if json_status_ok "$root/merged_scaled_primary_n64.json" KVCACHE_MATCHED_BUDGET_SCALED_MERGED; then
    log "SKIP ac_primary: $root/merged_scaled_primary_n64.json complete"
    return 0
  fi
  run_shell "ROOT='$root' SHARDS='$AC_SHARDS' PY='$PY' scripts/launch_matched_budget_scaled_primary.sh"
}

stage_graph_color_c1() {
  local root="$RUN_ROOT/graph_color_c1_budget_n64"
  if json_status_ok "$root/merged_c1_v16_r16_n64.json" KVCACHE_GRAPH_COLOR_C1_BUDGET_COMPLETE; then
    log "SKIP graph_color_c1: $root/merged_c1_v16_r16_n64.json complete"
    return 0
  fi
  run_shell "ROOT='$root' SHARDS='$GRAPH_C1_SHARDS' PY='$PY' scripts/launch_graph_color_c1_budget.sh"
}

stage_graph_color_symbolic() {
  local root="$RUN_ROOT/graph_color_symbolic_n64"
  mkdir -p "$root/shards"
  if json_status_ok "$root/v16_r16_symbolic_budget_curve_n64.json" KVCACHE_GRAPH_COLOR_BUDGET_CURVES_COMPLETE; then
    log "SKIP graph_color_symbolic: budget curve complete"
    return 0
  fi
  for shard in $(seq 0 $((GRAPH_SYMBOLIC_SHARDS - 1))); do
    if json_status_ok "$root/shards/shard_${shard}.json" KVCACHE_GRAPH_COLOR_SEARCH_COMPLETE; then
      continue
    fi
    gpu=$((shard % GPUS))
    run_shell "CUDA_VISIBLE_DEVICES=$gpu $PY -m analysis.kvcache_graph_color_search --output '$root/shards/shard_${shard}.json' --checkpoint-path '$root/shards/shard_${shard}_checkpoint.json' --km3-real-prompt results/kvcache_exactness/km3_real_graph_color_prompt_qwen3_fp32.json --model Qwen/Qwen3-4B-Instruct-2507 --seed 42 --scan-limit 5000 --n-instances 64 --min-backtracks 4 --node-cap 400 --num-vertices 16 --num-colors 3 --edge-probability 0.4 --difficulty-bin-label v16_p04 --order-mode degree_desc --r-values 16 --arms A_cache_oracle_search,C_incontext_oracle_search --call-cap 480 --max-new-tokens 8 --device cuda --dtype fp32 --invalid-branch-mode fail --invalid-backtrack-mode fail --resume --num-shards '$GRAPH_SYMBOLIC_SHARDS' --shard-index '$shard' > '$root/shards/shard_${shard}.log' 2>&1" &
  done
  wait
  run_shell "$PY -m analysis.kvcache_graph_color_merge --inputs '$root'/shards/shard_*.json --output '$root/v16_r16_symbolic_n64.json'"
  run_shell "$PY -m analysis.kvcache_graph_color_budget_curves --input '$root/v16_r16_symbolic_n64.json' --output '$root/v16_r16_symbolic_budget_curve_n64.json' --variant symbolic_cbj --policy oracle_search"
}

stage_external_registry() {
  local out="$RUN_ROOT/external_budget_runner_registry.json"
  if json_status_ok "$out" KVCACHE_EXTERNAL_BUDGET_BASELINE_REGISTRY_COMPLETE; then
    log "SKIP external_registry: $out complete"
    return 0
  fi
  run_shell "$PY -m analysis.kvcache_external_budget_baselines --output '$out'"
}

stage_hb2_external_full() {
  if [[ "$RUN_EXTERNAL_FULL" != "1" ]]; then
    log "SKIP hb2_external_full: set RUN_EXTERNAL_FULL=1 to run long HB-2 baselines"
    return 0
  fi
  run_shell "BASELINES='$HB2_BASELINES' SHARDS='$EXTERNAL_SHARDS' GPUS='$GPUS' INSTANCES='$HB2_INSTANCES' TASKS='$HB2_TASKS' BUDGET_SCALES='$HB2_BUDGET_SCALES' BEST_OF_N_ROOT='$RUN_ROOT/hb2_best_of_n/full_grid_n64_gpu0_3' LFS_ROOT='$RUN_ROOT/hb2_lfs/full_grid_n64_gpu0_3' TOT_RAP_ROOT='$RUN_ROOT/hb2_tot_rap/full_grid_n64_gpu0_3' PY='$PY' scripts/launch_hb2_external_full_grid.sh"
}

stage_experiment_log() {
  run_shell "$PY -m analysis.experiment_log"
}

run_stage() {
  local stage="$1"
  log "STAGE start $stage"
  case "$stage" in
    env) ensure_env ;;
    gpu_check) stage_gpu_check ;;
    manifest) stage_manifest ;;
    exactness) stage_exactness ;;
    item101_full_checkpoint) stage_item101_full_checkpoint ;;
    decision_probe) stage_decision_probe ;;
    c1_2_mamba) stage_c1_2_mamba ;;
    ac_primary) stage_ac_primary ;;
    graph_color_c1) stage_graph_color_c1 ;;
    graph_color_symbolic) stage_graph_color_symbolic ;;
    external_registry) stage_external_registry ;;
    hb2_external_full) stage_hb2_external_full ;;
    experiment_log) stage_experiment_log ;;
    *) echo "unknown stage: $stage" >&2; exit 2 ;;
  esac
  mark_stage "$stage"
  log "STAGE done $stage"
}

main() {
  mkdir -p "$RUN_ROOT" "$STATE_DIR"
  log "campaign root: $RUN_ROOT"
  log "stages: $STAGES"
  IFS=',' read -r -a stage_list <<< "$STAGES"
  for stage in "${stage_list[@]}"; do
    stage="${stage//[[:space:]]/}"
    [[ -n "$stage" ]] || continue
    run_stage "$stage"
  done
  log "campaign complete"
}

main "$@"