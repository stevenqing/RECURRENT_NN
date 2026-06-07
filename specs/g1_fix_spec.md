# G1 Fix Spec

Canonical repo: `/home/aiscuser/RECURRENT_NN`.

Goal: turn the Stage A Sudoku6 bridge from `G1 = 0.0` into a passing depth-1 bridge gate without weakening any downstream gate.

## Red Lines

- Train only on this repo's L1-L2 banded data.
- Do not train on Sudoku-Extreme.
- Do not load a TRM checkpoint into the controlled comparison.
- TRM is recipe guidance only: deep supervision, EMA, augmentation, recursion schedule, and long epoch scale.
- Evaluation is autonomous solve only: no teacher action injection, no prefix-at-eval, no token scratchpad.
- Fail closed: missing, quarantined, or default-unsafe parent artifacts must refuse to run.

## Task A - Diagnosis First

Run before any retraining:

```bash
~/.local/bin/uv run --python .venv/bin/python python -m experiments.stage_a_sudoku6_bridge --mode diagnose --output-dir results/stage_a_sudoku6_bridge
```

Required outputs:

- single-step forced accuracy
- iterative stick-reason histogram
- train/eval encoding byte-diff
- current `G1`
- explicit blocker classification

Decision rule:

- If single-step forced accuracy is low, prioritize bridge/operator supervised alignment.
- If single-step is good but iterative episodes stick, prioritize recurrence/deep-supervision schedule.
- If encoding byte-diff is nonzero, fix encoding before changing training.

## Task B - Retrain Recipe

Use the TRM-derived recipe on repo-local L1-L2 banded data:

- per-step deep supervision at every recursion step
- EMA weights for eval
- digit, band, and row/column-consistent augmentation
- recursion schedule from shallow to deeper loops
- seeds: `102,137,256` on three GPUs
- epoch/step scale controlled by G1 convergence, not a fixed short budget

The previous 1200-step scale is treated as 1-2 orders too short for this bridge.

Expected launch shape once implementation exists:

```bash
for spec in 102:0 137:1 256:2; do
  seed=${spec%%:*}
  gpu=${spec##*:}
  CUDA_VISIBLE_DEVICES=$gpu ~/.local/bin/uv run --python .venv/bin/python \
    python -u -m experiments.stage_a_sudoku6_bridge \
      --mode train \
      --seed "$seed" \
      --device cuda:0 \
      --output-dir "results/stage_a_sudoku6_bridge/seed_$seed" &
done
wait
```

## Gate Contract

G1 passes only when the report records:

- `G1 > 0.0`
- single-step forced accuracy above the registered threshold for the bridge run
- no train/eval encoding byte-diff
- no fail-open preflight path

G2 remains separate and must not be softened. L4 checks must include `reverts_nonzero_on_L4` and `forward_floor_on_L4` as information-bearing checks when they fail.
