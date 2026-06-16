# HB-2 External Baseline Acceleration V1

Date: 2026-06-16

## Current State

The formal HB-2 external run is detached under:

```bash
results/kvcache_matched_budget_v0/hb2_external_runs/gpu0_3_x2_batched_formal/
```

It uses GPUs 0-3 with two model processes per GPU. This reaches approximately full GPU utilization during LFS. GPUs 4-7 are reserved for the independent UI-S1/PO workload.

Current bottleneck is not GPU utilization. It is LFS futoshiki: each row can require thousands of sequential LLM calls because each expansion uses a child-value call and an explore-decision call.

## Option A: vLLM Backend

Availability:

- main `.venv`: no `vllm`, `openai`, `requests`, or `aiohttp`
- `.venv-vllm`: has `vllm`, `openai`, `requests`, and `aiohttp`

This makes a vLLM backend feasible, but it must be isolated from the exact KV-cache A/C mechanism runs. It is only appropriate for external no-train baselines.

### Expected Benefit

vLLM continuous batching can batch the many small LFS/ToT/RAP prompts across concurrent rows without duplicating model weights per shard. This should improve throughput for small generation calls.

### Required Engineering

1. Start one vLLM server per GPU, or one tensor-parallel server over GPUs 0-3 when those GPUs are free.
2. Add an OpenAI-compatible JSON generation backend to the external baseline runners.
3. Preserve per-row token accounting by using tokenizer-side counts, not server aggregate usage alone.
4. Record backend provenance in output rows:
   - `backend=vllm_openai_compatible`
   - `base_url`
   - `model`
   - `server_launch_command`

### Safe Pilot

Do not interrupt the current formal run. After it finishes or is intentionally paused, run a small B*-only pilot:

```bash
BASELINES=lfs TASKS=sudoku,graph_color BUDGET_SCALES=1 INSTANCES=4 \
  scripts/launch_hb2_external_full_grid_detached.sh
```

Then compare rows against the direct-Transformers runner for status, token accounting, and solve parity expectations.

## Option B: Multi-State Batched LFS

This keeps direct Transformers and avoids a vLLM server. Instead of one active row per process, a single process maintains many active LFS row states and batches the LLM calls across them.

### Expected Benefit

One model copy per GPU can process many independent LFS states per `generate` call. This is the cleanest way to improve LFS specifically without changing the algorithmic control loop inside each row.

### Required Engineering

Create a separate runner rather than mutating the current runner:

```text
analysis/kvcache_lfs_multistate_baseline.py
```

Core data structure per active row:

- `task`, `source_index`, `budget_B`
- `env`
- `current` state
- `frontier`
- `tokens_used`
- `expansions`
- `parse_fails`
- `best_score`
- `status`

Scheduler loop:

1. Select up to `state_batch_size` unfinished rows.
2. Build child-value prompts for rows whose current state has legal actions.
3. Batch-generate those prompts.
4. Apply per-row parse, frontier update, and token debit.
5. Build explore prompts for rows with nonempty frontiers.
6. Batch-generate explore prompts.
7. Apply per-row current-state update and checkpoint completed rows.

### Token Accounting Discipline

Each row must debit exactly:

```text
input_tokens(prompt_i) + generated_tokens(output_i)
```

Batch padding tokens are not billed to rows, because the shared HB-2 counter is a model-token accounting abstraction, not hardware padding cost accounting. This matches existing best-of-n batch billing discipline.

Rows must stop before a prompt would exceed their own `budget_B`.

### Compatibility Note

Batch generation may not be byte-identical to the current single-row runner because padding and batching can alter low-level decoding behavior. Treat this as a new backend variant:

```text
method=LFS_repo_port_multistate_batch
backend=transformers_batched
```

Do not merge it into existing `LFS_repo_port_budget_exhaustive` results unless explicitly declared as the replacement backend.

## Recommendation

For fastest low-risk progress:

1. Let the current x2 detached run continue.
2. Implement `analysis/kvcache_lfs_multistate_baseline.py` as a separate runner.
3. Validate on `sudoku,graph_color`, `INSTANCES=4`, `BUDGET_SCALES=1`.
4. Only if row-level accounting and outputs look sane, launch a B*-only n=64 interim read.
5. Consider vLLM only after a free GPU window is available, because starting vLLM now would collide with active workloads.

## 2026-06-16 vLLM Micro-Smoke Update

An OpenAI-compatible vLLM backend was added to `analysis/kvcache_lfs_multistate_baseline.py` and a conservative vLLM server launcher was added at `scripts/launch_hb2_vllm_server.sh`.

Server smoke:

```bash
RUN_ROOT=results/kvcache_matched_budget_v0/hb2_vllm_servers/qwen3_4b_gpu4_port8012 \
GPU=4 PORT=8012 GPU_MEMORY_UTILIZATION=0.35 MAX_MODEL_LEN=4096 \
scripts/launch_hb2_vllm_server.sh
```

Micro speed smoke on sudoku n=4, budget scale 0.032:

| runner | backend | wall seconds | speedup vs single |
| --- | --- | ---: | ---: |
| single-state LFS | transformers_single | 79.943 | 1.0x |
| multi-state LFS | transformers_batched | 28.451 | 2.8x |
| multi-state LFS | vllm_openai_compatible | 9.698 | 8.2x |

The vLLM rows stayed within per-row `budget_B=898` using local-tokenizer input/output token debits. This remains a backend speed smoke only. It is not HB-2 solve-rate evidence and must not be merged with direct-Transformers LFS rows without an explicit backend decision.
