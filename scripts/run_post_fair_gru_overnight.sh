#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PY:-$HOME/.local/bin/uv run --python .venv/bin/python python}"
FAIR_DIR="${FAIR_DIR:-results/gru_stack_grid_fair}"
POLL_SEC="${POLL_SEC:-300}"

while [[ ! -f "$FAIR_DIR/results.json" ]]; do
  echo "$(date -Iseconds) waiting for $FAIR_DIR/results.json"
  sleep "$POLL_SEC"
done

$PY -m analysis.merge_gru_grid --input-dir "$FAIR_DIR"
$PY -m analysis.gru_degeneracy_diagnostic \
  --input-dir "$FAIR_DIR" \
  --output-dir results/gru_degeneracy_diagnostic_fair \
  --device cuda:0 \
  --batch-size 2048 \
  --batches 1
$PY -m analysis.gru_vs_structured_closeout --gru-path "$FAIR_DIR/results.json"
$PY -m analysis.validate_outputs || true
$PY -m analysis.experiment_log

PILOT_DIR="${PILOT_DIR:-results/gru_arch_pilot}"
mkdir -p "$PILOT_DIR"

# Representative bounded-state architecture audit. This does not replace the full
# fair grid; it checks whether the fixed replay decoder choice is hiding a better
# bounded decoder on small/large and easy/hard cells.
declare -a SPECS=(
  "0 256 60 2 without_replacement 42"
  "1 256 60 9 with_replacement 137"
  "2 512 256 2 without_replacement 42"
  "3 512 256 9 with_replacement 137"
  "4 1024 60 2 without_replacement 42"
  "5 1024 60 9 with_replacement 137"
  "6 1024 729 2 without_replacement 42"
  "7 1024 729 9 with_replacement 137"
)

for spec in "${SPECS[@]}"; do
  read -r gpu D kvar kval repl seed <<<"$spec"
  cell_dir="$PILOT_DIR/D${D}_Kv${kvar}_Ku${kval}_${repl}_seed${seed}"
  mkdir -p "$cell_dir"
  CUDA_VISIBLE_DEVICES="$gpu" $PY -u -m experiments.train_gru_stack \
    --D "$D" \
    --K-var "$kvar" \
    --K-val "$kval" \
    --replacement "$repl" \
    --max-depth 64 \
    --steps 5000 \
    --batch-size 4096 \
    --eval-every 100 \
    --patience 20 \
    --device cuda:0 \
    --arch-grid gru:mlp:3,gru:replay:2,lstm:mlp:3 \
    --val-depths 1,2,3,4,8,16,32,48,64 \
    --eval-batches 1 \
    --final-eval-batches 2 \
    --output-dir "$cell_dir" \
    > "$cell_dir/run.log" 2>&1 &
done

wait

$PY - <<'PY'
import json
from pathlib import Path
root = Path('results/gru_arch_pilot')
rows = []
for path in sorted(root.glob('*/results.json')):
    data = json.loads(path.read_text())
    rows.append({
        'cell': path.parent.name,
        'frontier_joint_095': data['frontier_joint_095'],
        'best_config': data['best_config'],
        'bounded_state_only': data.get('bounded_state_only'),
    })
(root / 'summary.json').write_text(json.dumps({'module': 'gru_arch_pilot', 'rows': rows}, indent=2, sort_keys=True) + '\n')
print(json.dumps({'results': str(root / 'summary.json'), 'rows': len(rows)}, indent=2, sort_keys=True))
PY

$PY -m analysis.validate_outputs || true
$PY -m analysis.experiment_log
