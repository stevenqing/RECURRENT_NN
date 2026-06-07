#!/usr/bin/env bash
set -euo pipefail

UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
DEVICE="${DEVICE:-cuda:0}"
DOWNLOAD_MODELS="${DOWNLOAD_MODELS:-0}"

if [[ ! -x "$UV_BIN" ]]; then
  echo "uv not found at $UV_BIN. Install it with: python -m pip install --user uv" >&2
  exit 2
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  "$UV_BIN" venv .venv --python 3.10
  "$UV_BIN" pip install --python "$PYTHON_BIN" -r requirements.txt huggingface_hub accelerate
fi

"$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.model_readiness

if [[ "$DOWNLOAD_MODELS" == "1" ]]; then
  "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Instruct-2507
  "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Thinking-2507 --output-dir results/model_download/thinking
  "$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.download_qwen --model-id Qwen/Qwen3.5-4B --output-dir results/model_download/qwen3_5_4b
fi

"$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.reconstruct_stage_a_artifacts \
  --output-dir artifacts/stage_a \
  --n-instances 1024 \
  --seed 42 \
  --device "$DEVICE" \
  --operator-steps 300 \
  --bridge-steps 500 \
  --batch-size 256

"$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.stage_a_adapter_wiring --device cpu
"$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.stage_a_banded_gate_refusal
"$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.stage_a_sudoku6_bridge --mode diagnose
"$UV_BIN" run --python "$PYTHON_BIN" python -m experiments.w3_qwen35_probe

set +e
"$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.validate_outputs
VALIDATION_EXIT=$?
set -e

"$UV_BIN" run --python "$PYTHON_BIN" python -m analysis.experiment_log

if [[ "$VALIDATION_EXIT" -ne 0 ]]; then
  echo "Validation is expected to remain nonzero while Stage A G1/L4 and legacy scaffold checks are red." >&2
fi

exit 0
