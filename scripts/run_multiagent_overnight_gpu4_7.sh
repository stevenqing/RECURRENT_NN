#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/aiscuser/RECURRENT_NN
cd "$ROOT"
ENDPOINTS="http://127.0.0.1:8104/v1,http://127.0.0.1:8105/v1,http://127.0.0.1:8106/v1,http://127.0.0.1:8107/v1"
OUT="$ROOT/results/multiagent_overnight_gpu4_7"
mkdir -p "$OUT/logs"

for port in 8104 8105 8106 8107; do
  curl -fsS --max-time 10 "http://127.0.0.1:${port}/v1/models" >/dev/null
  echo "endpoint ${port} healthy"
done

.venv/bin/python -m analysis.multiagent_real_qwen_decision_gate \
  --manifest results/multiagent_core_2x2_preflight/instance_manifest.json \
  --output results/multiagent_real_qwen_decision_gate/evaluation_v2.json \
  --samples-per-cell-event 8 \
  --register 8 \
  --evaluate \
  --base-urls "$ENDPOINTS" \
  --model Qwen/Qwen3.5-4B \
  --workers 16 \
  2>&1 | tee "$OUT/logs/decision_gate.log"

.venv/bin/python - <<'PY'
import json
p=json.load(open('results/multiagent_real_qwen_decision_gate/evaluation_v2.json'))
if p.get('status')!='MULTIAGENT_REAL_QWEN_DECISION_GATE_PASS' or not p.get('gates',{}).get('go_end_to_end_dev'):
    raise SystemExit('decision gate failed; end-to-end stage blocked')
print('decision gate PASS; starting end-to-end dev')
PY

.venv/bin/python -m analysis.multiagent_real_qwen_end_to_end \
  --manifest results/multiagent_core_2x2_preflight/instance_manifest.json \
  --decision-gate results/multiagent_real_qwen_decision_gate/evaluation_v2.json \
  --output results/multiagent_real_qwen_end_to_end/dev_results.json \
  --checkpoint results/multiagent_real_qwen_end_to_end/checkpoint.json \
  --instances-per-cell 2 \
  --register 8 \
  --node-cap 1500 \
  --call-cap 160 \
  --token-cap 80000 \
  --max-new-tokens 96 \
  --base-urls "$ENDPOINTS" \
  --model Qwen/Qwen3.5-4B \
  --workers 16 \
  --resume \
  2>&1 | tee "$OUT/logs/end_to_end_dev.log"

.venv/bin/python -m analysis.multiagent_overnight_summary \
  --output-dir results/multiagent_overnight_gpu4_7
