# RECURRENT_NN Reproducibility Contract

Last audited: 2026-06-07 at commit `229b61a`.

This repository is reproducible as a workflow, not as a fully self-contained binary snapshot.

## What Is Git-Contained

The following are tracked and should exist immediately after checkout:

- environment/setup instructions in `ENV_SPEC.md`
- canonical repo note in `CANONICAL_REPO.md`
- validation and ledger code in `analysis/validate_outputs.py` and `analysis/experiment_log.py`
- Stage A fill-in entrypoints in `experiments/stage_a_adapter_wiring.py`, `experiments/stage_a_banded_gate_refusal.py`, and `experiments/stage_a_sudoku6_bridge.py`
- W3 Qwen3.5 metadata probe in `experiments/w3_qwen35_probe.py`
- specs in `specs/g1_fix_spec.md` and `specs/w3_qwen35_probe_spec.md`
- small JSON/markdown ledger records under `results/`

## External Or Regenerated Assets

These are not stored in git and must be regenerated or downloaded:

- Python environment under `.venv/`
- Hugging Face model cache for `Qwen/Qwen3-4B-Instruct-2507`, `Qwen/Qwen3-4B-Thinking-2507`, and `Qwen/Qwen3.5-4B`
- Stage A reconstructed binaries:
  - `artifacts/stage_a/recurrent_solver_b1a_clean_l2_tied_p96_e300_seed102.pt`
  - `artifacts/stage_a/item142_factored_cell_digit_decoder_depth8_D128.pt`
  - `artifacts/stage_a/internalize_teacher_train1024_maxconf_b128_solved.trace.jsonl`

Those Stage A files are intentionally ignored because they are generated binary/trace artifacts. Recreate them with:

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

## One-Command Continuation Refresh

After environment creation, run:

```bash
bash scripts/reproduce_continuation_state.sh
```

By default this does not redownload Qwen weights. To redownload/refresh model records too:

```bash
DOWNLOAD_MODELS=1 bash scripts/reproduce_continuation_state.sh
```

Expected current-state validation after refresh is not all green:

```text
72 PASS / 9 FAIL / 81 total
```

The remaining failures are expected until later work:

- `stage_a_sudoku6_g1_pass`
- `stage_a_reverts_nonzero_on_L4`
- `stage_a_forward_floor_on_L4`
- six missing legacy scaffold artifacts

## Bitwise Caveats

Exact byte-for-byte reproduction is not guaranteed for every generated file.

- `requirements.txt` uses lower bounds, not a lockfile. `ENV_SPEC.md` records the verified package snapshot, but `uv pip install -r requirements.txt` may resolve newer packages in the future.
- GPU training/reconstruction can be nondeterministic across CUDA/PyTorch versions. The manifest hashes record the local reconstructed artifacts, not a guaranteed future bitwise target.
- JSON files with `generated_at` timestamps will naturally differ between runs.
- Hugging Face cache paths can differ by machine. The model ids and snapshot records are the reproducibility anchors.

## Honest Claim

The current claim is:

- environment setup is documented and verified on this machine;
- model assets are externally downloadable and records exist;
- Stage A parent artifacts are regenerable from repo code;
- continuation validation/ledger can be refreshed from tracked scripts;
- the scientific status is still red at Stage A G1/L4, not silently passing.

The current claim is not:

- a fully self-contained checkout with all binaries committed;
- a bitwise deterministic artifact bundle;
- a completed P1/P2/P3 experiment run.
