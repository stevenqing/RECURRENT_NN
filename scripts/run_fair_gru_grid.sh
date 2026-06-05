#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
OUT="${OUT:-results/gru_stack_grid_fair}"
ARCH_GRID="${ARCH_GRID:-gru:replay:2}"
MAX_DEPTH="${MAX_DEPTH:-64}"
STEPS="${STEPS:-5000}"
BATCH_SIZE="${BATCH_SIZE:-4096}"
EVAL_EVERY="${EVAL_EVERY:-100}"
PATIENCE="${PATIENCE:-20}"
NUM_SHARDS="${NUM_SHARDS:-8}"
VAL_DEPTHS="${VAL_DEPTHS:-1,2,3,4,8,16,32,48,64}"
EVAL_BATCHES="${EVAL_BATCHES:-1}"
FINAL_EVAL_BATCHES="${FINAL_EVAL_BATCHES:-2}"

mkdir -p "$OUT"

for i in $(seq 0 $((NUM_SHARDS - 1))); do
  shard_dir="$OUT/shard_$i"
  mkdir -p "$shard_dir"
  CUDA_VISIBLE_DEVICES="$i" $PY -u -m experiments.train_gru_stack_grid \
    --mode full \
    --device cuda:0 \
    --num-shards "$NUM_SHARDS" \
    --shard-index "$i" \
    --max-depth "$MAX_DEPTH" \
    --steps "$STEPS" \
    --batch-size "$BATCH_SIZE" \
    --eval-every "$EVAL_EVERY" \
    --patience "$PATIENCE" \
    --arch-grid "$ARCH_GRID" \
    --val-depths "$VAL_DEPTHS" \
    --eval-batches "$EVAL_BATCHES" \
    --final-eval-batches "$FINAL_EVAL_BATCHES" \
    --output-dir "$shard_dir" \
    > "$shard_dir/run.log" 2>&1 &
done

wait

$PY -m analysis.merge_gru_grid --input-dir "$OUT"
$PY -m analysis.gru_vs_structured_closeout --gru-path "$OUT/results.json"
$PY -m analysis.validate_outputs
$PY -m analysis.experiment_log
