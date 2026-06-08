# Track B Faithful Retry Plan

## Purpose

Plan the next learned Track B retry after the item041 P0 profile and item042 batched-ops equivalence guard. This is a launch plan, not a result claim. No optimized run should be reported until the trainer wiring preserves the scalar Sudoku6 semantics checked by `analysis/test_sudoku_engine_gpu.py` and `analysis/test_batched_ops.py`.

## Preconditions

- Keep item041 as the before-optimization baseline: `results/profile_gate/track_b_current_20260608T_p0_single/profile_report.json`.
- Keep item042 equivalence green: `results/batched_ops/equivalence_100.json` with `n_mismatches=0`.
- Future `progress.jsonl` rows must retain `steps_per_sec`, `examples_per_sec`, `gpu_util`, and `gpu_util_snapshot`.
- Do not cancel or modify non-project GPU processes. The latest operator policy allows using GPUs despite external occupancy because free memory is sufficient.

## Required Trainer Capabilities

1. Move training rows into a GPU-resident tensor dataset after tensorization, then sample batch indices on device. Implemented as `--gpu-resident-batches`.
2. Wire `register.batched_ops` into rollout or data-preparation paths only behind equivalence checks. The bridge exists; rollout/data-path integration still requires a before/after timing run.
3. Use `--amp-bf16` for autocast training on CUDA.
4. Use `--torch-compile` as an opt-in single-GPU model compile flag.
5. Use `--require-param-min 5000000 --require-param-max 8000000` to fail before training unless the selected shape is inside the parameter-count gate.
6. Keep one process per seed on one GPU; do not use DataParallel for this model.

## Model Shape

Primary retry shape:

| hidden_dim | nhead | feedforward_dim | recurrence_steps | parameter_count |
| --- | --- | --- | --- | --- |
| 384 | 6 | 8192 | 12 | 6908685 |

Backup shapes that also satisfy the 5-8M gate:

| hidden_dim | nhead | feedforward_dim | recurrence_steps | parameter_count |
| --- | --- | --- | --- | --- |
| 384 | 8 | 8192 | 12 | 6908685 |
| 320 | 5 | 10240 | 12 | 6989453 |
| 320 | 8 | 10240 | 12 | 6989453 |
| 384 | 6 | 6144 | 12 | 5333773 |

## Launch Topology

Use one GPU per seed. Preferred seed/GPU mapping:

| seed | CUDA_VISIBLE_DEVICES | trainer device |
| --- | --- | --- |
| 102 | 0 | cuda:0 |
| 137 | 1 | cuda:0 |
| 256 | 6 | cuda:0 |

GPU 7 remains available for profiling, smoke checks, or a fourth exploratory seed after the three canonical seeds are launched.

## Candidate Commands

These commands are launch candidates after the item044 prelaunch smoke checks. They still require before/after reporting against item041 before any speedup claim.

```bash
CUDA_VISIBLE_DEVICES=0 .venv/bin/python -m experiments.train_trm_operator \
  --output-dir results/track_b_trm_retry_gpu_efficiency/seed102_gpu0 \
  --seed 102 --device cuda:0 --train-instances 4096 --eval-instances 512 --l4-instances 128 \
  --steps 20000 --batch-size 16384 --hidden-dim 384 --nhead 6 --feedforward-dim 8192 \
  --recurrence-steps 12 --lr 3e-4 --generation-workers 8 --episode-workers 8 --tensorize-workers 8 \
  --eval-every 500 --forced-loss focal --fuse-step 100 --fuse-min-loss-drop 0.01 \
  --gpu-resident-batches --amp-bf16 --torch-compile --require-param-min 5000000 --require-param-max 8000000
```

Repeat with `CUDA_VISIBLE_DEVICES=1 --seed 137 --output-dir results/track_b_trm_retry_gpu_efficiency/seed137_gpu1` and `CUDA_VISIBLE_DEVICES=6 --seed 256 --output-dir results/track_b_trm_retry_gpu_efficiency/seed256_gpu6`.

## Acceptance And Reporting

- Compare optimized throughput against item041 P0: total seconds, steps/sec, examples/sec, GPU utilization, and phase timings.
- Report per-seed G1, G2, forced precision, forced recall, stick reasons, and final checkpoints exactly as item040 did.
- A speedup claim requires before/after numbers and unchanged equivalence checks.
- A learned success claim still requires learned `G1 >= 0.95` and non-substituted Track B evidence; Track A symbolic evidence cannot green Track B.