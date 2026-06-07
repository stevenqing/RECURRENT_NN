#!/usr/bin/env bash
set -euo pipefail

UV_BIN=${UV_BIN:-$HOME/.local/bin/uv}
PYTHON_BIN=${PYTHON_BIN:-.venv/bin/python}
OUT_DIR=${OUT_DIR:-results/w3_qwen35_probe}
N_INSTANCES=${N_INSTANCES:-3}
MAX_NODES_PER_TASK=${MAX_NODES_PER_TASK:-2}
SEEDS=${SEEDS:-42}
CAP_NODES=${CAP_NODES:-32}
BATCH_SIZE=${BATCH_SIZE:-2}

mkdir -p "$OUT_DIR/propagation_shards"

CUDA_VISIBLE_DEVICES=0 "$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.w3_qwen35_probe \
  --output-dir "$OUT_DIR" \
  --load-model \
  --device cuda:0 \
  --run-survival \
  --run-native-delta \
  > /tmp/w3_hidden.out &

pids=($!)
tasks=(horn_sat general_sat graph_coloring sudoku_4x4 logic_grid)
gpus=(1 2 3 4 5)

for index in "${!tasks[@]}"; do
  task=${tasks[$index]}
  gpu=${gpus[$index]}
  CUDA_VISIBLE_DEVICES=$gpu "$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.w3_qwen35_probe \
    --output-dir "$OUT_DIR/propagation_shards/$task" \
    --device cuda:0 \
    --run-propagation \
    --propagation-task-types "$task" \
    --propagation-n-instances "$N_INSTANCES" \
    --propagation-max-nodes-per-task "$MAX_NODES_PER_TASK" \
    --propagation-seeds "$SEEDS" \
    --propagation-cap-nodes "$CAP_NODES" \
    --propagation-batch-size "$BATCH_SIZE" \
    > "/tmp/w3_${task}.out" &
  pids+=($!)
done

for pid in "${pids[@]}"; do
  wait "$pid"
done

IFS=,
shard_dirs="${tasks[*]/#/$OUT_DIR/propagation_shards/}"
unset IFS

"$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.w3_qwen35_probe \
  --output-dir "$OUT_DIR" \
  --merge-propagation-shards "$shard_dirs" \
  > /tmp/w3_merge.out
