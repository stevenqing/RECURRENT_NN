# RECURRENT_NN Environment Spec

Last verified: 2026-06-07 on Linux with Python 3.10.20, `uv 0.11.19`, CUDA-visible A100 GPUs.

Use the workspace root as the project directory:

```bash
cd /home/aiscuser/RECURRENT_NN
```

Do not use the older path shown in some historical docs (`/home/aiscuser/stage_d_llm`) unless that directory actually exists and is the active workspace.

## 1. Install uv If Missing

```bash
python -m pip install --user uv
```

Then call uv explicitly from the user bin path when the shell PATH has not been refreshed:

```bash
~/.local/bin/uv --version
```

## 2. Create The Repo Environment

```bash
~/.local/bin/uv venv .venv --python 3.10
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt huggingface_hub accelerate
```

Why the extra packages are installed outside `requirements.txt`:

- `huggingface_hub` is used by `analysis/download_qwen.py`.
- `accelerate` is required for practical Qwen/Transformers loading paths.

## 3. Verify The Install

```bash
~/.local/bin/uv run --python .venv/bin/python python - <<'PY'
import torch, transformers, huggingface_hub, accelerate, peft, yaml, numpy, matplotlib
print('python ok')
print('torch', torch.__version__)
print('transformers', transformers.__version__)
print('huggingface_hub', huggingface_hub.__version__)
print('accelerate', accelerate.__version__)
print('peft', peft.__version__)
print('numpy', numpy.__version__)
print('cuda_available', torch.cuda.is_available())
print('cuda_device_count', torch.cuda.device_count())
PY

~/.local/bin/uv run --python .venv/bin/python python -m analysis.model_readiness
```

Expected readiness output writes:

```text
results/model_readiness/readiness.json
```

On the verified machine, readiness reported `transformers_available: true`, `cuda_available: true`, and `cuda_device_count: 8`.

## 4. Optional Model Assets

The default local operator cache can run without loading Qwen weights. For real frozen Qwen hidden states, make sure the Hugging Face cache is populated and credentials are available if the model access requires them.

Download/record the Qwen3-4B model roles and the Qwen3.5-4B comparison model:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Instruct-2507
~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Thinking-2507 --output-dir results/model_download/thinking
~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3.5-4B --output-dir results/model_download/qwen3_5_4b
```

Verified local download records on 2026-06-07:

```text
Qwen/Qwen3-4B-Instruct-2507 -> results/model_download/qwen_download.json
Qwen/Qwen3-4B-Thinking-2507 -> results/model_download/thinking/qwen_download.json
Qwen/Qwen3.5-4B -> results/model_download/qwen3_5_4b/qwen_download.json
```

Probe real Qwen hidden-state caching:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --limit 8 --output-name qwen_probe_cache
```

## 5. Re-run Validation Or Logs

Use these after the expected result artifacts already exist:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m analysis.validate_outputs
~/.local/bin/uv run --python .venv/bin/python python -m analysis.experiment_log
```

`analysis.validate_outputs` is strict: it checks many historical result files. A missing old artifact means the experiment record is incomplete, not necessarily that the Python environment is broken.

## 6. Rebuild Current Continuation State

The repository is workflow-reproducible, not a fully self-contained binary snapshot. See `REPRODUCIBILITY.md` for the exact contract.

Stage A parent `.pt` files and the teacher trace are generated artifacts and are intentionally ignored by git. Rebuild them before expecting Stage A preflight or adapter wiring to pass:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m experiments.reconstruct_stage_a_artifacts \
	--output-dir artifacts/stage_a \
	--n-instances 1024 \
	--seed 42 \
	--device cuda:0 \
	--operator-steps 300 \
	--bridge-steps 500 \
	--batch-size 256
```

Then refresh the current continuation artifacts, validation, and ledger:

```bash
bash scripts/reproduce_continuation_state.sh
```

The current expected validation state is red, not all green: `86 PASS / 9 FAIL / 95 total`. The remaining red checks are Stage A G1/L4 blockers plus missing legacy scaffold artifacts.

## 7. Full Scaffold Run Order

This is the lightweight scaffold order from the repo plan:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m analysis.preregistration
~/.local/bin/uv run --python .venv/bin/python python -m analysis.oracle_dataset
~/.local/bin/uv run --python .venv/bin/python python -m analysis.model_readiness
~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache
~/.local/bin/uv run --python .venv/bin/python python -m experiments.learned_wiring_baseline
~/.local/bin/uv run --python .venv/bin/python python -m experiments.two_by_two_falsification
~/.local/bin/uv run --python .venv/bin/python python -m experiments.d_stage_0_propagation
~/.local/bin/uv run --python .venv/bin/python python -m experiments.d_stage_1_depth1_gate
~/.local/bin/uv run --python .venv/bin/python python -m experiments.d_stage_2_capacity
~/.local/bin/uv run --python .venv/bin/python python -m experiments.d_stage_3_vs_cot
~/.local/bin/uv run --python .venv/bin/python python -m experiments.verifier_verification
~/.local/bin/uv run --python .venv/bin/python python -m experiments.ttt_reversibility
~/.local/bin/uv run --python .venv/bin/python python -m analysis.plotting
~/.local/bin/uv run --python .venv/bin/python python -m analysis.validate_outputs
~/.local/bin/uv run --python .venv/bin/python python -m analysis.experiment_log
```

## 8. Verified Resolved Packages

Top-level packages verified by import on 2026-06-07:

```text
accelerate==1.13.0
huggingface-hub==1.18.0
matplotlib==3.10.9
numpy==2.2.6
peft==0.19.1
pyyaml==6.0.3
torch==2.12.0
transformers==5.10.2
```

Full resolved package snapshot from `uv pip freeze --python .venv/bin/python | sort`:

```text
accelerate==1.13.0
annotated-doc==0.0.4
anyio==4.13.0
certifi==2026.5.20
click==8.4.1
contourpy==1.3.2
cuda-bindings==13.3.1
cuda-pathfinder==1.5.5
cuda-toolkit==13.0.2
cycler==0.12.1
exceptiongroup==1.3.1
filelock==3.29.1
fonttools==4.63.0
fsspec==2026.4.0
h11==0.16.0
hf-xet==1.5.0
httpcore==1.0.9
httpx==0.28.1
huggingface-hub==1.18.0
idna==3.18
jinja2==3.1.6
kiwisolver==1.5.0
markdown-it-py==4.2.0
markupsafe==3.0.3
matplotlib==3.10.9
mdurl==0.1.2
mpmath==1.3.0
networkx==3.4.2
numpy==2.2.6
nvidia-cublas==13.1.1.3
nvidia-cuda-cupti==13.0.85
nvidia-cuda-nvrtc==13.0.88
nvidia-cuda-runtime==13.0.96
nvidia-cudnn-cu13==9.20.0.48
nvidia-cufft==12.0.0.61
nvidia-cufile==1.15.1.6
nvidia-curand==10.4.0.35
nvidia-cusolver==12.0.4.66
nvidia-cusparse==12.6.3.3
nvidia-cusparselt-cu13==0.8.1
nvidia-nccl-cu13==2.29.7
nvidia-nvjitlink==13.0.88
nvidia-nvshmem-cu13==3.4.5
nvidia-nvtx==13.0.85
packaging==26.2
peft==0.19.1
pillow==12.2.0
psutil==7.2.2
pygments==2.20.0
pyparsing==3.3.2
python-dateutil==2.9.0.post0
pyyaml==6.0.3
regex==2026.5.9
rich==15.0.0
safetensors==0.7.0
setuptools==81.0.0
shellingham==1.5.4
six==1.17.0
sympy==1.14.0
tokenizers==0.22.2
torch==2.12.0
tqdm==4.68.1
transformers==5.10.2
triton==3.7.0
typer==0.25.1
typing-extensions==4.15.0
```