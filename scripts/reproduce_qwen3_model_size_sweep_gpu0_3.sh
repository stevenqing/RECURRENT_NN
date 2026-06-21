#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-results/reproduction_gpu0_3_20260620/qwen3_model_size_sweep}"
MODELS="${MODELS:-Qwen/Qwen3-0.6B,Qwen/Qwen3-1.7B,Qwen/Qwen3-8B}"
STAGES="${STAGES:-manifest,ac_smoke,summary}"
GPUS="${GPUS:-0,1,2,3}"
PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"

EXACTNESS_DEVICE="${EXACTNESS_DEVICE:-cuda}"
EXACTNESS_DTYPE="${EXACTNESS_DTYPE:-bf16}"
EXACTNESS_TOL="${EXACTNESS_TOL:-1e-3}"
EXACTNESS_DEPTH="${EXACTNESS_DEPTH:-16}"
EXACTNESS_CHECKPOINTS="${EXACTNESS_CHECKPOINTS:-2,4,8,12}"
EXACTNESS_PARALLEL="${EXACTNESS_PARALLEL:-1}"

AC_TASKS="${AC_TASKS:-sudoku,futoshiki}"
AC_INSTANCES="${AC_INSTANCES:-8}"
AC_SCAN_LIMIT="${AC_SCAN_LIMIT:-40}"
AC_BUDGET_ANCHORS="${AC_BUDGET_ANCHORS:-sudoku:28070,futoshiki:3206226}"
AC_BUDGET_SCALES="${AC_BUDGET_SCALES:-1}"

OPENAI_BASE_URLS="${OPENAI_BASE_URLS:-http://127.0.0.1:8010/v1,http://127.0.0.1:8011/v1,http://127.0.0.1:8012/v1,http://127.0.0.1:8013/v1}"
VLLM_TASKS="${VLLM_TASKS:-sudoku,futoshiki,graph_color}"
VLLM_BUDGET_SCALES="${VLLM_BUDGET_SCALES:-1}"
VLLM_SMOKE_INSTANCES="${VLLM_SMOKE_INSTANCES:-1}"
VLLM_FULL_INSTANCES="${VLLM_FULL_INSTANCES:-64}"
VLLM_SHARDS="${VLLM_SHARDS:-16}"
REQUEST_WORKERS="${REQUEST_WORKERS:-128}"
VALUE_BATCH_SIZE="${VALUE_BATCH_SIZE:-32}"
ACTIVE_ROWS="${ACTIVE_ROWS:-512}"
STATE_BATCH_SIZE="${STATE_BATCH_SIZE:-256}"

mkdir -p "$ROOT"

IFS=',' read -r -a model_list <<< "$MODELS"
IFS=',' read -r -a gpu_list <<< "$GPUS"

contains_stage() {
  local stage="$1"
  [[ ",$STAGES," == *",$stage,"* ]]
}

model_slug() {
  echo "$1" | sed -E 's#^Qwen/##; s#[^A-Za-z0-9]+#_#g; s#_+$##; s#^_##' | tr '[:upper:]' '[:lower:]'
}

require_single_vllm_model() {
  if [[ "${#model_list[@]}" -ne 1 ]]; then
    echo "vLLM stages require MODELS to contain exactly one served model. Launch servers for that model first." >&2
    exit 2
  fi
}

write_run_env() {
  cat > "$ROOT/run_env.sh" <<EOF
ROOT=$ROOT
MODELS=$MODELS
STAGES=$STAGES
GPUS=$GPUS
PY=$PY
EXACTNESS_DEVICE=$EXACTNESS_DEVICE
EXACTNESS_DTYPE=$EXACTNESS_DTYPE
EXACTNESS_TOL=$EXACTNESS_TOL
EXACTNESS_DEPTH=$EXACTNESS_DEPTH
EXACTNESS_CHECKPOINTS=$EXACTNESS_CHECKPOINTS
EXACTNESS_PARALLEL=$EXACTNESS_PARALLEL
AC_TASKS=$AC_TASKS
AC_INSTANCES=$AC_INSTANCES
AC_SCAN_LIMIT=$AC_SCAN_LIMIT
AC_BUDGET_ANCHORS=$AC_BUDGET_ANCHORS
AC_BUDGET_SCALES=$AC_BUDGET_SCALES
OPENAI_BASE_URLS=$OPENAI_BASE_URLS
VLLM_TASKS=$VLLM_TASKS
VLLM_BUDGET_SCALES=$VLLM_BUDGET_SCALES
VLLM_SMOKE_INSTANCES=$VLLM_SMOKE_INSTANCES
VLLM_FULL_INSTANCES=$VLLM_FULL_INSTANCES
VLLM_SHARDS=$VLLM_SHARDS
REQUEST_WORKERS=$REQUEST_WORKERS
VALUE_BATCH_SIZE=$VALUE_BATCH_SIZE
ACTIVE_ROWS=$ACTIVE_ROWS
STATE_BATCH_SIZE=$STATE_BATCH_SIZE
EOF
}

stage_manifest() {
  mkdir -p "$ROOT"
  ROOT="$ROOT" QWEN3_SWEEP_MODELS="$MODELS" $PY - <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

try:
    from huggingface_hub import model_info
except Exception as exc:  # pragma: no cover - diagnostic path
    model_info = None
    import_error = repr(exc)
else:
    import_error = None

models = [item.strip() for item in os.environ["QWEN3_SWEEP_MODELS"].split(",") if item.strip()]
rows = []
for model in models:
    row = {"model": model}
    if model_info is None:
        row.update({"available": None, "error": f"huggingface_hub unavailable: {import_error}"})
    else:
        try:
            info = model_info(model, timeout=30)
            siblings = [s.rfilename for s in info.siblings]
            row.update(
                {
                    "available": True,
                    "sha": info.sha,
                    "safetensors": [name for name in siblings if name.endswith(".safetensors")],
                    "safetensors_count": sum(name.endswith(".safetensors") for name in siblings),
                }
            )
        except Exception as exc:  # pragma: no cover - network/model diagnostic path
            row.update({"available": False, "error": f"{type(exc).__name__}: {exc}"})
    rows.append(row)

payload = {
    "schema_version": "qwen3_model_size_manifest_v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "models": rows,
}
path = Path(os.environ["ROOT"]) / "manifest.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"path": str(path), "models": len(rows)}, sort_keys=True))
PY
}

stage_exactness() {
  if [[ "${#gpu_list[@]}" -lt 1 && "$EXACTNESS_DEVICE" == cuda* ]]; then
    echo "GPUS must contain at least one GPU for cuda exactness" >&2
    exit 2
  fi
  mkdir -p "$ROOT/exactness"
  local active=0
  local idx=0
  for model in "${model_list[@]}"; do
    local slug
    slug="$(model_slug "$model")"
    local out="$ROOT/exactness/${slug}_${EXACTNESS_DTYPE}.json"
    local log="$ROOT/exactness/${slug}_${EXACTNESS_DTYPE}.log"
    local gpu="${gpu_list[$((idx % ${#gpu_list[@]}))]}"
    echo "[exactness] model=$model dtype=$EXACTNESS_DTYPE device=$EXACTNESS_DEVICE out=$out log=$log"
    (
      if [[ "$EXACTNESS_DEVICE" == cuda* ]]; then
        CUDA_VISIBLE_DEVICES="$gpu" $PY -m analysis.kvcache_exactness_gate \
          --model "$model" \
          --depth "$EXACTNESS_DEPTH" \
          --checkpoints "$EXACTNESS_CHECKPOINTS" \
          --tol "$EXACTNESS_TOL" \
          --device cuda \
          --dtype "$EXACTNESS_DTYPE" \
          --out "$out"
      else
        $PY -m analysis.kvcache_exactness_gate \
          --model "$model" \
          --depth "$EXACTNESS_DEPTH" \
          --checkpoints "$EXACTNESS_CHECKPOINTS" \
          --tol "$EXACTNESS_TOL" \
          --device "$EXACTNESS_DEVICE" \
          --dtype "$EXACTNESS_DTYPE" \
          --out "$out"
      fi
    ) > "$log" 2>&1 &
    active=$((active + 1))
    idx=$((idx + 1))
    if (( active >= EXACTNESS_PARALLEL )); then
      wait -n
      active=$((active - 1))
    fi
  done
  wait
}

stage_ac_smoke() {
  mkdir -p "$ROOT/ac_smoke"
  for model in "${model_list[@]}"; do
    local slug
    slug="$(model_slug "$model")"
    local out="$ROOT/ac_smoke/${slug}.json"
    local checkpoint="$ROOT/ac_smoke/${slug}_checkpoint.json"
    local log="$ROOT/ac_smoke/${slug}.log"
    echo "[ac_smoke] model=$model out=$out log=$log"
    $PY -m analysis.kvcache_matched_budget_scaled run-shard \
      --output "$out" \
      --checkpoint-path "$checkpoint" \
      --resume \
      --model "$model" \
      --seed 42 \
      --scan-limit "$AC_SCAN_LIMIT" \
      --n-instances "$AC_INSTANCES" \
      --tasks "$AC_TASKS" \
      --policies symbolic_cbj \
      --node-cap 50000 \
      --futoshiki-size 7 \
      --futoshiki-difficulty 3 \
      --budget-anchors "$AC_BUDGET_ANCHORS" \
      --budget-scales "$AC_BUDGET_SCALES" \
      --shard-index 0 \
      --num-shards 1 > "$log" 2>&1
  done
}

stage_tot_rap_vllm_smoke() {
  require_single_vllm_model
  local model="${model_list[0]}"
  local slug
  slug="$(model_slug "$model")"
  local url="${OPENAI_BASE_URLS%%,*}"
  local dir="$ROOT/tot_rap_vllm_smoke/$slug"
  mkdir -p "$dir"
  echo "[tot_rap_vllm_smoke] model=$model url=$url dir=$dir"
  $PY -m analysis.kvcache_tot_rap_baselines run-shard \
    --output "$dir/result.json" \
    --checkpoint-path "$dir/checkpoint.json" \
    --resume \
    --n-instances "$VLLM_SMOKE_INSTANCES" \
    --scan-limit 20 \
    --tasks "$VLLM_TASKS" \
    --methods tot,rap \
    --budget-anchors sudoku:28070,futoshiki:3206226,graph_color:32895 \
    --budget-scales "$VLLM_BUDGET_SCALES" \
    --max-expansions 16 \
    --mcts-iters 8 \
    --max-depth 4 \
    --n-actions 4 \
    --beam-size 4 \
    --value-batch-size 4 \
    --rollout-depth 1 \
    --rollout-branching 1 \
    --max-new-tokens 96 \
    --backend vllm \
    --openai-base-url "$url" \
    --openai-model "$model" \
    --request-workers 32 \
    --num-shards 1 \
    --shard-index 0 \
    --dtype fp32 \
    --device cuda > "$dir/result.log" 2>&1
}

stage_lfs_vllm_smoke() {
  require_single_vllm_model
  local model="${model_list[0]}"
  local slug
  slug="$(model_slug "$model")"
  local url="${OPENAI_BASE_URLS%%,*}"
  local dir="$ROOT/lfs_vllm_smoke/$slug"
  mkdir -p "$dir"
  echo "[lfs_vllm_smoke] model=$model url=$url dir=$dir"
  $PY -m analysis.kvcache_lfs_multistate_baseline run-shard \
    --output "$dir/result.json" \
    --checkpoint-path "$dir/checkpoint.json" \
    --resume \
    --n-instances "$VLLM_SMOKE_INSTANCES" \
    --scan-limit 20 \
    --tasks "$VLLM_TASKS" \
    --budget-anchors sudoku:28070,futoshiki:3206226,graph_color:32895 \
    --budget-scales "$VLLM_BUDGET_SCALES" \
    --max-expansions 16 \
    --max-new-tokens 96 \
    --active-rows 16 \
    --state-batch-size 16 \
    --backend vllm \
    --openai-base-url "$url" \
    --openai-model "$model" \
    --request-workers 32 \
    --num-shards 1 \
    --shard-index 0 \
    --dtype fp32 \
    --device cuda > "$dir/result.log" 2>&1
}

stage_tot_rap_full_detached() {
  require_single_vllm_model
  local model="${model_list[0]}"
  local slug
  slug="$(model_slug "$model")"
  RUN_ROOT="$ROOT/runs/${slug}_tot_rap_vllm_full" \
  ROOT="$ROOT/hb2_tot_rap/${slug}_full_grid_n${VLLM_FULL_INSTANCES}_vllm_gpu0_3_shards${VLLM_SHARDS}" \
  TASKS="$VLLM_TASKS" \
  METHODS=tot,rap \
  INSTANCES="$VLLM_FULL_INSTANCES" \
  BUDGET_SCALES="0.25,0.5,1,2,4" \
  VALUE_BATCH_SIZE="$VALUE_BATCH_SIZE" \
  REQUEST_WORKERS="$REQUEST_WORKERS" \
  SHARDS="$VLLM_SHARDS" \
  OPENAI_BASE_URLS="$OPENAI_BASE_URLS" \
  OPENAI_MODEL="$model" \
    scripts/launch_hb2_tot_rap_vllm_multi_server_detached.sh
}

stage_lfs_full_detached() {
  require_single_vllm_model
  local model="${model_list[0]}"
  local slug
  slug="$(model_slug "$model")"
  RUN_ROOT="$ROOT/runs/${slug}_lfs_vllm_full" \
  ROOT="$ROOT/hb2_lfs/${slug}_full_grid_n${VLLM_FULL_INSTANCES}_vllm_gpu0_3_shards${VLLM_SHARDS}" \
  TASKS="$VLLM_TASKS" \
  INSTANCES="$VLLM_FULL_INSTANCES" \
  BUDGET_SCALES="0.25,0.5,1,2,4" \
  ACTIVE_ROWS="$ACTIVE_ROWS" \
  STATE_BATCH_SIZE="$STATE_BATCH_SIZE" \
  REQUEST_WORKERS="$REQUEST_WORKERS" \
  SHARDS="$VLLM_SHARDS" \
  OPENAI_BASE_URLS="$OPENAI_BASE_URLS" \
  OPENAI_MODEL="$model" \
    scripts/launch_hb2_lfs_multistate_vllm_multi_server_detached.sh
}

stage_summary() {
  ROOT="$ROOT" QWEN3_SWEEP_MODELS="$MODELS" $PY - <<'PY'
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

root = Path(os.environ["ROOT"])
models = [item.strip() for item in os.environ["QWEN3_SWEEP_MODELS"].split(",") if item.strip()]

def slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", model.removeprefix("Qwen/")).strip("_").lower()

rows = []
for model in models:
    model_slug = slug(model)
    row = {"model": model, "slug": model_slug}
    exactness_paths = sorted((root / "exactness").glob(f"{model_slug}_*.json"))
    row["exactness"] = []
    for path in exactness_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        row["exactness"].append(
            {
                "path": str(path),
                "status": payload.get("status"),
                "dtype": payload.get("dtype"),
                "overall_pass": payload.get("overall_pass"),
                "max_abs_logit_delta": payload.get("max_abs_logit_delta"),
            }
        )
    ac_path = root / "ac_smoke" / f"{model_slug}.json"
    if ac_path.exists():
        payload = json.loads(ac_path.read_text(encoding="utf-8"))
        budget_rows = payload.get("budget_rows", [])
        row["ac_smoke"] = {
            "path": str(ac_path),
            "status": payload.get("status"),
            "budget_rows": len(budget_rows),
            "solved_by_method": dict(Counter(str(item.get("method")) for item in budget_rows if item.get("solved"))),
        }
    for key, rel in {
        "tot_rap_vllm_smoke": Path("tot_rap_vllm_smoke") / model_slug / "result.json",
        "lfs_vllm_smoke": Path("lfs_vllm_smoke") / model_slug / "result.json",
    }.items():
        path = root / rel
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            result_rows = payload.get("rows", [])
            row[key] = {
                "path": str(path),
                "status": payload.get("status"),
                "rows": len(result_rows),
                "statuses": dict(Counter(str(item.get("status")) for item in result_rows)),
            }
    rows.append(row)

payload = {
    "schema_version": "qwen3_model_size_sweep_summary_v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "root": str(root),
    "models": rows,
}
summary_path = root / "summary.json"
summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

lines = ["# Qwen3 Model Size Sweep Status", "", f"Generated: {payload['generated_at']}", "", f"Root: `{root}`", ""]
lines.append("| model | exactness | A/C smoke | vLLM smoke |")
lines.append("| --- | --- | --- | --- |")
for row in rows:
    exactness = "; ".join(f"{item.get('dtype')} {item.get('status')} max_delta={item.get('max_abs_logit_delta')}" for item in row.get("exactness", [])) or "pending"
    ac = row.get("ac_smoke")
    ac_text = f"{ac['status']} rows={ac['budget_rows']} solved={ac['solved_by_method']}" if ac else "pending"
    vllm_bits = []
    for key in ["tot_rap_vllm_smoke", "lfs_vllm_smoke"]:
        value = row.get(key)
        if value:
            vllm_bits.append(f"{key}: {value['status']} rows={value['rows']} statuses={value['statuses']}")
    lines.append(f"| `{row['model']}` | {exactness} | {ac_text} | {'; '.join(vllm_bits) if vllm_bits else 'pending'} |")
status_path = root / "status.md"
status_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps({"summary": str(summary_path), "status": str(status_path)}, sort_keys=True))
PY
}

write_run_env
contains_stage manifest && stage_manifest
contains_stage exactness && stage_exactness
contains_stage ac_smoke && stage_ac_smoke
contains_stage tot_rap_vllm_smoke && stage_tot_rap_vllm_smoke
contains_stage lfs_vllm_smoke && stage_lfs_vllm_smoke
contains_stage tot_rap_full_detached && stage_tot_rap_full_detached
contains_stage lfs_full_detached && stage_lfs_full_detached
contains_stage summary && stage_summary

echo "qwen3 model-size sweep stages complete: $STAGES"