# Stage D Experiment Log

Generated at: 2026-06-05T12:57:23.396588+00:00

Scope: consolidated log for oracle-trace scaffold outputs. These are not trained-model evaluations.

## Artifact Index

| artifact | path |
| --- | --- |
| preregistration | results/preregistration/preregistration.json |
| oracle_dataset | results/oracle_dataset/summary.json |
| operator_cache | results/operator_cache/summary.json |
| model_readiness | results/model_readiness/readiness.json |
| qwen_instruct_download | results/model_download/qwen_download.json |
| qwen_thinking_download | results/model_download/thinking/qwen_download.json |
| qwen_probe_cache | results/operator_cache/qwen_probe_cache_summary.json |
| qwen_128_cache | results/operator_cache/qwen_128_cache_summary.json |
| learned_wiring_qwen_128 | results/learned_wiring_qwen_128/results.json |
| qwen_balanced_320_cache | results/operator_cache/qwen_balanced_320_cache_summary.json |
| learned_wiring_qwen_balanced_320 | results/learned_wiring_qwen_balanced_320/results.json |
| module1_stack_capacity | results/module1_stack_capacity/results.json |
| module1_stack_capacity_full | results/module1_stack_capacity_full/results.json |
| module1_capacity_batching_large | results/module1_capacity_batching_large/results.json |
| module1_capacity_benchmark_full_shards | results/module1_capacity_benchmark_full_shards/results.json |
| module1_k_direction_corrected | results/module1_capacity_benchmark_full_shards/k_direction_corrected.json |
| module1_capacity_diagnostic_full_shards | results/module1_capacity_diagnostic_full_shards/results.json |
| module1_capacity_perdepth_shards | results/module1_capacity_perdepth_shards/results.json |
| module1_gru_smoke | results/gru_stack_smoke/results.json |
| module1_gru_grid_full | results/gru_stack_grid_full/results.json |
| learned_wiring | results/learned_wiring/results.json |
| two_by_two | results/two_by_two/results.json |
| d_stage_0 | results/d_stage_0/results.json |
| d_stage_1 | results/d_stage_1/results.json |
| d_stage_2 | results/d_stage_2/results.json |
| d_stage_3 | results/d_stage_3/results.json |
| verifier | results/verifier/results.json |
| ttt | results/ttt/results.json |
| analysis_summary | results/analysis/summary.md |
| validation | results/validation/validation.json |

## Run Metadata

- Evaluation mode: `oracle_trace_scaffold`
- Oracle dataset supervision: `symbolic_oracle_trace`
- Oracle dataset tasks: 184
- Oracle dataset examples: 2456
- Max oracle backtrack depth in dataset: 8
- Operator cache feature source: `deterministic_hashed_prompt_fallback`
- Transformers available for Qwen cache: True
- CUDA available for Qwen cache: True
- Qwen Instruct snapshot: `/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554`
- Qwen Thinking snapshot: `/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea`
- Qwen probe hidden dim: 2560
- Qwen-128 learned wiring action accuracy: 0.5703
- Qwen-128 learned wiring verifier accuracy: 0.8359
- Qwen balanced-320 holdout action accuracy: 0.8906
- Qwen balanced-320 holdout verifier accuracy: 1.0000
- Module 1 stack capacity mode: `quick`
- Module 1 full stack capacity device: `cuda:0`
- Module 1 per-depth K-direction: `k_direction_negative`
- Module 1 per-depth open flag: False
- Module 1 bound-single K_eff: `D_over_ln_product`
- Module 1 factored K_eff: `D_over_ln_Kvar`
- Learned wiring train action accuracy: 0.9855
- Learned wiring holdout action accuracy: 0.4724
- Learned wiring train verifier accuracy: 0.9865
- Learned wiring holdout verifier accuracy: 0.9010
- Validation passed: True

## Gate Status

| gate | status | criterion |
| --- | --- | --- |
| D.3 2x2 falsification | PASS | register helps backtracking only |
| D-stage 1 depth-1 | PASS | structured has reverts and ablations collapse |
| D.5 verifier | PASS | oracle >= learned >= noisy >= disabled |
| D.6 TTT diagnostic | PASS | TTT restore error > structured restore error |

## Incremental Run Items

| item | name | what changed | artifact | key result |
| --- | --- | --- | --- | --- |
| 01 | preregistration | Computed d*_dyn bands before D-stage 3. | results/preregistration/preregistration.json | bands=6 |
| 02 | oracle dataset | Materialized symbolic oracle supervision as JSONL. | results/oracle_dataset/examples.jsonl | tasks=184, examples=2456 |
| 03 | fallback operator cache | Cached deterministic hashed prompt features for local learned-head checks. | results/operator_cache/operator_cache.pt | hidden_dim=256, examples=2456 |
| 04 | uv/qwen readiness | Verified uv environment, CUDA, and transformers availability. | results/model_readiness/readiness.json | cuda=True, transformers=True |
| 05 | qwen downloads | Downloaded frozen Instruct operator and Thinking CoT baseline snapshots. | results/model_download/ | instruct=7.51GiB, thinking=7.51GiB |
| 06 | qwen probe cache | Confirmed Qwen Instruct loads and emits 2560-d hidden states. | results/operator_cache/qwen_probe_cache.pt | examples=8, hidden_dim=2560 |
| 07 | qwen 128 smoke | Ran a single-seed Qwen hidden-state wiring smoke test. | results/learned_wiring_qwen_128/results.json | action=0.5703, verifier=0.8359 |
| 08 | qwen balanced 320 | Ran balanced 5-seed Qwen hidden cache with seed-999 holdout. | results/learned_wiring_qwen_balanced_320/results.json | holdout_action=0.8906, holdout_verifier=1.0000 |
| 09 | module 1 quick | Ran fast operator-free stack capacity sweep to validate pipeline. | results/module1_stack_capacity/results.json | rows=84, summary=18 |
| 10 | module 1 full gpu | Ran full GPU stack sweep with rotation, GRU sequence proxy, and tape. | results/module1_stack_capacity_full/results.json | rows=432, device=cuda:0 |
| 11 | module 1 batching | Benchmarked single-GPU batch sizes and raised default benchmark batch size. | results/module1_capacity_batching_large/results.json | best_batches=[8192, 8192, 8192, 16384] |
| 12 | module 1 capacity benchmark full | Ran 8-shard task-free HRR/permutation capacity benchmark for K-direction. | results/module1_capacity_benchmark_full_shards/results.json | decision=k_inversion_or_nonmonotonic_open, open=True |
| 13 | ceiling-aware K reanalysis | Recomputed K-direction after dropping frontier points capped by K_var/sweep ceiling. | results/module1_capacity_benchmark_full_shards/k_direction_corrected.json | target=theory_consistent, passed=True |
| 14 | module 1 diagnostic full | Ran fixed-depth diagnostic benchmark with joint/var/val K-direction metrics. | results/module1_capacity_diagnostic_full_shards/results.json | decision=k_direction_open_or_inverted, open=True |
| 15 | module 1 per-depth full | Ran ceiling-free per-depth benchmark with with/without replacement and K_eff fits. | results/module1_capacity_perdepth_shards/results.json | decision=k_direction_negative, open=False |
| 16 | gru tuned smoke | Implemented tuned GRUStack and ran a val-selected checkpoint smoke. | results/gru_stack_smoke/results.json | converged=True, frontier=0.0 |
| 17 | gru tuned full grid | Ran tuned GRUStack full grid and compared against structured capacity. | results/gru_stack_grid_full/results.json | all_converged=True, below_structured=True |
| 18 | scaffold gates | Ran D.3, D-stage 0/1/2/3, verifier, and TTT scaffold gates. | results/*/results.json | validation=True |
| 19 | validation | Validated required files, schemas, gate expectations, and Module 1 comparisons. | results/validation/validation.json | checks=50, passed=True |

## Detailed Itemized Run Log

### 001. Established preregistration bands and scaffold run order

Purpose: make the Stage D ceiling claim auditable before downstream scaffold runs. This records the d*_dyn formula and predeclared D/K bands.

Code used:

- `analysis/preregistration.py`
- `PLAN.md`
- `config/experiments.yaml`

Command:

```bash
cd /home/aiscuser/stage_d_llm && python -m analysis.preregistration
```

Artifacts:

- `results/preregistration/preregistration.json`

Result summary:

| label | D | K | predicted_d_star |
| --- | --- | --- | --- |
| small_D_large_K | 256 | 729 | 19.42 |
| medium_D_large_K | 512 | 729 | 38.84 |
| small_D_medium_K | 256 | 60 | 31.26 |
| medium_D_medium_K | 512 | 60 | 62.53 |
| large_D_large_K | 1024 | 729 | 77.67 |
| offscreen_control | 4096 | 60 | 500.2 |

Decision: preregistration pass. These bands are now the fixed reference for later D-stage claims.

### 002. Built symbolic oracle supervision dataset

Purpose: enforce the discipline that supervision comes from symbolic oracle traces, not stronger LLM CoT. This materializes the current-node training examples used by later cache/head experiments.

Code added/used:

- `analysis/oracle_dataset.py`
- `tasks/oracle/trace_generator.py`
- `tasks/sat/generators.py`
- `tasks/sudoku/generator_4x4.py`
- `tasks/graph_coloring/generator.py`
- `tasks/logic_grid/generator.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && python -m analysis.oracle_dataset
```

Artifacts:

- `results/oracle_dataset/examples.jsonl`
- `results/oracle_dataset/summary.json`

Dataset summary:

- tasks: 184
- examples: 2456
- max_backtrack_depth: 8

| task_type | tasks | examples |
| --- | --- | --- |
| general_sat | 40 | 735 |
| graph_coloring | 40 | 360 |
| horn_sat | 24 | 216 |
| logic_grid | 40 | 465 |
| sudoku_4x4 | 40 | 680 |

Decision: dataset pass. This is still oracle-supervised scaffold data, but it is now explicit and reusable.

### 003. Set up uv environment and downloaded Qwen3-4B variants

Purpose: move from missing dependencies to a reproducible uv-managed environment, then download both Qwen roles required by the Stage D design.

Code added/used:

- `.venv` created by `uv`
- `analysis/model_readiness.py`
- `analysis/download_qwen.py`
- `config/backbone.yaml`

Validation/setup commands:

```bash
cd /home/aiscuser/stage_d_llm
~/.local/bin/uv venv .venv --python 3.10
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt huggingface_hub accelerate
~/.local/bin/uv run --python .venv/bin/python python -m analysis.model_readiness
~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Instruct-2507
~/.local/bin/uv run --python .venv/bin/python python -m analysis.download_qwen --model-id Qwen/Qwen3-4B-Thinking-2507 --output-dir results/model_download/thinking
```

Artifacts:

- `results/model_readiness/readiness.json`
- `results/model_download/qwen_download.json`
- `results/model_download/thinking/qwen_download.json`

Environment/model summary:

- transformers_available: True
- cuda_available: True
- cuda_device_count: 8
- Instruct snapshot: `/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554`
- Thinking snapshot: `/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea`

Decision: environment pass. Both Qwen3-4B snapshots are local and the uv environment can load transformers with CUDA visible.

### 004. Confirmed real Qwen hidden-state contact with probe cache

Purpose: verify that Qwen3-4B-Instruct actually loads and emits hidden states with the expected hidden dimension, before attempting larger caches.

Code used:

- `analysis/operator_cache.py`
- `llm_operator/wrapper.py`
- `llm_operator/prompt_renderer.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --limit 8 --output-name qwen_probe_cache
```

Artifacts:

- `results/operator_cache/qwen_probe_cache.pt`
- `results/operator_cache/qwen_probe_cache_summary.json`

Probe result:

- feature_source: `Qwen/Qwen3-4B-Instruct-2507`
- hidden_dim: 2560
- examples: 8

Decision: Qwen hidden-state probe pass. This validates the frozen operator loading path.

### 005. Ran Qwen hidden-state learned wiring smoke and balanced holdout

Purpose: move beyond deterministic fallback features and test whether frozen Qwen hidden states support supervised controller/verifier heads, including a seed-999 holdout split.

Code added/used:

- `analysis/operator_cache.py`
- `experiments/learned_wiring_baseline.py`
- `controller/controller_head.py`
- `controller/verifier_head.py`

Commands:

```bash
cd /home/aiscuser/stage_d_llm
~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --limit 128 --output-name qwen_128_cache
~/.local/bin/uv run --python .venv/bin/python python -m experiments.learned_wiring_baseline --cache-path results/operator_cache/qwen_128_cache.pt --output-dir results/learned_wiring_qwen_128 --epochs 20 --batch-size 32
~/.local/bin/uv run --python .venv/bin/python python -m analysis.operator_cache --load-model --seeds 42,137,256,314,999 --per-seed-limit 64 --output-name qwen_balanced_320_cache
~/.local/bin/uv run --python .venv/bin/python python -m experiments.learned_wiring_baseline --cache-path results/operator_cache/qwen_balanced_320_cache.pt --output-dir results/learned_wiring_qwen_balanced_320 --epochs 24 --batch-size 32
```

Artifacts:

- `results/operator_cache/qwen_128_cache.pt`
- `results/operator_cache/qwen_128_cache_summary.json`
- `results/learned_wiring_qwen_128/results.json`
- `results/learned_wiring_qwen_128/heads.pt`
- `results/operator_cache/qwen_balanced_320_cache.pt`
- `results/operator_cache/qwen_balanced_320_cache_summary.json`
- `results/learned_wiring_qwen_balanced_320/results.json`
- `results/learned_wiring_qwen_balanced_320/heads.pt`

Result summary:

| run | examples | train_action | holdout_action | train_verifier | holdout_verifier |
| --- | --- | --- | --- | --- | --- |
| qwen_128_smoke | 128 | 0.5703 | 0 | 0.8359 | 0 |
| qwen_balanced_320 | 320 | 0.8398 | 0.8906 | 0.9688 | 1 |

Decision: Qwen hidden-state wiring passes as a small supervised probe. The balanced seed-999 holdout action accuracy is materially higher than the deterministic fallback baseline.

### 006. Ran deterministic fallback learned wiring baseline with seed holdout

Purpose: keep a non-Qwen local baseline for comparison and sanity-check whether the learned-head path can memorize train seeds without real operator features.

Commands:

```bash
cd /home/aiscuser/stage_d_llm
python -m analysis.operator_cache
python -m experiments.learned_wiring_baseline
```

Artifacts:

- `results/operator_cache/operator_cache.pt`
- `results/operator_cache/summary.json`
- `results/learned_wiring/results.json`
- `results/learned_wiring/heads.pt`

Result summary:

- train_action_accuracy: 0.9855
- holdout_action_accuracy: 0.4724
- train_verifier_accuracy: 0.9865
- holdout_verifier_accuracy: 0.9010

Decision: fallback baseline is useful as a sanity check, but weak for seed-holdout action generalization. Do not use it for the Qwen claim.

### 007. Ran Module 1 operator-free stack capacity quick and full GPU sweeps

Purpose: start the new three-module design at Module 1, isolating the bounded reversible stack from Qwen. This compares rotation/VSA, GRU bounded vector proxy, and explicit tape.

Code added/modified:

- `register/vsa_stack.py`
- `experiments/module1_stack_capacity.py`

Commands:

```bash
cd /home/aiscuser/stage_d_llm
~/.local/bin/uv run --python .venv/bin/python python -m experiments.module1_stack_capacity --mode quick --output-dir results/module1_stack_capacity
~/.local/bin/uv run --python .venv/bin/python python -m experiments.module1_stack_capacity --mode full --device cuda:0 --output-dir results/module1_stack_capacity_full
```

Artifacts:

- `results/module1_stack_capacity/results.json`
- `results/module1_stack_capacity/run.log`
- `results/module1_stack_capacity_full/results.json`
- `results/module1_stack_capacity_full/run.log`

Full GPU frontier summary:

| method | D | K | predicted_d_star | frontier_decode_095 |
| --- | --- | --- | --- | --- |
| gru_proxy_sequence | 64 | 60 | 7.816 | 1 |
| gru_proxy_sequence | 128 | 60 | 15.63 | 1 |
| gru_proxy_sequence | 256 | 60 | 31.26 | 1 |
| gru_proxy_sequence | 512 | 60 | 62.53 | 1 |
| gru_proxy_sequence | 1024 | 60 | 125.1 | 1 |
| gru_proxy_sequence | 64 | 729 | 4.855 | 0 |
| gru_proxy_sequence | 128 | 729 | 9.709 | 0 |
| gru_proxy_sequence | 256 | 729 | 19.42 | 0 |
| gru_proxy_sequence | 512 | 729 | 38.84 | 0 |
| gru_proxy_sequence | 1024 | 729 | 77.67 | 0 |
| rotation_vsa | 64 | 60 | 7.816 | 1 |
| rotation_vsa | 128 | 60 | 15.63 | 3 |
| rotation_vsa | 256 | 60 | 31.26 | 7 |
| rotation_vsa | 512 | 60 | 62.53 | 15 |
| rotation_vsa | 1024 | 60 | 125.1 | 31 |
| rotation_vsa | 64 | 729 | 4.855 | 1 |
| rotation_vsa | 128 | 729 | 9.709 | 4 |
| rotation_vsa | 256 | 729 | 19.42 | 9 |
| rotation_vsa | 512 | 729 | 38.84 | 19 |
| rotation_vsa | 1024 | 729 | 77.67 | 38 |
| tape | 64 | 60 | 7.816 | 11 |
| tape | 128 | 60 | 15.63 | 23 |
| tape | 256 | 60 | 31.26 | 47 |
| tape | 512 | 60 | 62.53 | 93 |
| tape | 1024 | 60 | 125.1 | 188 |
| tape | 64 | 729 | 4.855 | 6 |
| tape | 128 | 729 | 9.709 | 14 |
| tape | 256 | 729 | 19.42 | 29 |
| tape | 512 | 729 | 38.84 | 57 |
| tape | 1024 | 729 | 77.67 | 116 |

Decision: Module 1 full GPU run passes the current validation checks: rotation frontier is above matched GRU sequence proxy, and tape remains the upper bound. Scientific caveat: current rotation implementation is still a random level-key/Hadamard proxy, not the stronger orthogonal rotation + HRR cleanup implementation from the design note, and observed frontiers are below the d*(D) line.

### 008. Benchmarked Module 1 capacity batch sizes

Purpose: find a faster single-GPU batch size before launching sharded full capacity runs. The first batched implementation still used a conservative default; this item measures throughput and peak memory directly on `cuda:0`.

Code added/modified:

- `analysis/benchmark_capacity_batching.py`
- `experiments/module1_capacity_benchmark.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -u -m analysis.benchmark_capacity_batching --device cuda:0 --batch-sizes 512,1024,2048,4096,8192,16384 --n-trials 8192 --output-dir results/module1_capacity_batching_large
```

Artifacts:

- `results/module1_capacity_batching_large/results.json`
- `results/module1_capacity_batching_large/run.log`

Best batch by case:

| variant | D | K_var | K_val | best_batch | trials_per_sec | peak_gib |
| --- | --- | --- | --- | --- | --- | --- |
| bound_single | 512 | 81 | 9 | 8192 | 7.065e+04 | 0.1072 |
| factored | 512 | 81 | 9 | 8192 | 2.499e+05 | 0.06256 |
| bound_single | 1024 | 729 | 2 | 8192 | 3.343e+04 | 0.2271 |
| factored | 1024 | 729 | 2 | 16384 | 9.898e+04 | 0.1765 |

Decision: use `--batch-size 8192` as the robust default for Module 1 capacity benchmark shards. It is near-best across cases and uses far below available A100 memory; 16384 can be faster for some factored cases but is less uniformly best.

### 009. Ran 8-shard task-free Module 1 capacity benchmark

Purpose: resolve whether the earlier K-inversion was a proxy artifact by using the proper HRR/permutation bound-single and factored registers over a task-free storage stress benchmark. This is the decisive K-direction test before any d* claim.

Code added/modified:

- `register/vsa_stack.py`
- `experiments/module1_capacity_benchmark.py`
- `analysis/capacity_theory.py`
- `analysis/merge_capacity_shards.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.module1_capacity_benchmark --mode full --device cuda:0 --num-shards 8 --shard-index $i --batch-size 8192 --output-dir results/module1_capacity_benchmark_full_shards/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_capacity_shards --input-dir results/module1_capacity_benchmark_full_shards
```

Artifacts:

- `results/module1_capacity_benchmark_full_shards/results.json`
- `results/module1_capacity_benchmark_full_shards/curves.json`
- `results/module1_capacity_benchmark_full_shards/merge.log`
- `results/module1_capacity_benchmark_full_shards/shard_*/results.json`
- `results/module1_capacity_benchmark_full_shards/shard_*/run.log`

K-direction result:

| variant | D | K_val | K_vars | frontiers | signs |
| --- | --- | --- | --- | --- | --- |
| bound_single | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [9, 20, 45, 40, 31, 26] | [1, 1, -1, -1, -1] |
| factored | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [9, 20, 15, 20, 17, 14] | [1, -1, 1, -1, -1] |

- calibrated_c: 8.545489937800552
- decision: `k_inversion_or_nonmonotonic_open`
- open: True

Decision: K-direction remains open/nonmonotonic under the proper HRR/permutation benchmark. Do not claim d* = D/(2 ln K). The safe current claim is linear-in-D improvement for the measured construction plus GRU/tape comparison, with K-scaling unresolved.

### 010. Recomputed K-direction after excluding ceiling-bound points

Purpose: correct the initial K-direction decision logic. Since variables are sampled without replacement, small K_var runs cannot exceed K_var stack levels; those points must be excluded before judging K monotonicity.

Code added:

- `analysis/k_direction_recompute.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m analysis.k_direction_recompute
```

Artifacts:

- `results/module1_capacity_benchmark_full_shards/k_direction_corrected.json`

Corrected target result:

| variant | D | K_val | full_classification | corrected_classification | kept | dropped |
| --- | --- | --- | --- | --- | --- | --- |
| bound_single | 1024 | 2 | nonmonotonic | theory_consistent | [(60, 45), (81, 40), (256, 31), (729, 26)] | [(9, 9), (20, 20)] |

Decision: the bound_single D=1024 K_val=2 group is theory-consistent after dropping ceiling-bound K_var=9 and K_var=20. The earlier open flag was confounded by finite variable count at low K.

### 011. Ran fixed-depth Module 1 K-direction diagnostic benchmark

Purpose: test whether the K-direction issue is caused by variable depth grids or by joint `(var,val)` aggregation. This run uses a fixed depth grid and reports joint, var-only, and val-only frontiers separately.

Code added/used:

- `experiments/module1_capacity_diagnostic.py`
- `analysis/merge_diagnostic_shards.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.module1_capacity_diagnostic --mode full --device cuda:0 --num-shards 8 --shard-index $i --batch-size 8192 --trials 4096 --output-dir results/module1_capacity_diagnostic_full_shards/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_diagnostic_shards --input-dir results/module1_capacity_diagnostic_full_shards
```

Artifacts:

- `results/module1_capacity_diagnostic_full_shards/results.json`
- `results/module1_capacity_diagnostic_full_shards/curves.json`
- `results/module1_capacity_diagnostic_full_shards/shard_*/results.json`
- `results/module1_capacity_diagnostic_full_shards/shard_*/run.log`

K-direction diagnostic:

| variant | metric | D | K_val | K_vars | frontiers | signs |
| --- | --- | --- | --- | --- | --- | --- |
| bound_single | joint | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [8, 16, 32, 32, 32, 32] | [1, 1, 0, 0, 0] |
| bound_single | var | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [8, 16, 32, 32, 32, 32] | [1, 1, 0, 0, 0] |
| bound_single | val | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [8, 16, 32, 32, 32, 32] | [1, 1, 0, 0, 0] |
| factored | joint | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [8, 16, 16, 16, 16, 16] | [1, 0, 0, 0, 0] |
| factored | var | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [8, 16, 16, 16, 16, 16] | [1, 0, 0, 0, 0] |
| factored | val | 1024 | 2 | [9, 20, 60, 81, 256, 729] | [8, 16, 32, 64, 64, 64] | [1, 1, 1, 0, 0] |

- decision: `k_direction_open_or_inverted`
- open: True

Decision: fixed-depth diagnostic still records K-direction as open/inverted. Important caveat: small `K_var` values cap possible depth because vars are sampled without replacement, so low-K frontiers are partly ceiling-limited. This strengthens the conclusion that no d* claim should be made yet from frontier buckets alone; the next per-depth benchmark resolves this directly.

### 011. Ran ceiling-free per-depth Module 1 capacity benchmark

Purpose: remove the K_var ceiling and coarse frontier-bucket artifacts by measuring accuracy at every fixed depth, with both without-replacement and with-replacement var sampling. This is the clean K-direction and K_eff fit test.

Code added/used:

- `experiments/module1_capacity_perdepth.py`
- `analysis/merge_perdepth_shards.py`
- `analysis/capacity_theory.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.module1_capacity_perdepth --mode full --device cuda:0 --num-shards 8 --shard-index $i --batch-size 8192 --trials 4096 --output-dir results/module1_capacity_perdepth_shards/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_perdepth_shards --input-dir results/module1_capacity_perdepth_shards
```

Artifacts:

- `results/module1_capacity_perdepth_shards/results.json`
- `results/module1_capacity_perdepth_shards/curves.json`
- `results/module1_capacity_perdepth_shards/shard_*/results.json`
- `results/module1_capacity_perdepth_shards/shard_*/run.log`

Per-depth K-direction:

| variant | replacement | metric | D | K_val | K_vars | capacities | signs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bound_single | with_replacement | joint | 1024 | 2 | [60, 81, 256, 729] | [53.77160462334458, 51.60739471070541, 44.47761734267629, 39.61899179230261] | [-1, -1, -1] |
| bound_single | with_replacement | var | 1024 | 2 | [60, 81, 256, 729] | [53.85461616531922, 51.674292625552546, 44.50296557188487, 39.627197424441] | [-1, -1, -1] |
| bound_single | with_replacement | val | 1024 | 2 | [60, 81, 256, 729] | [58.0, 58.0, 52.93291946395077, 46.69630874940104] | [0, -1, -1] |
| bound_single | without_replacement | joint | 1024 | 2 | [60, 81, 256, 729] | [53.74540981430042, 51.574336450365955, 44.37440405290796, 39.637738786003396] | [-1, -1, -1] |
| bound_single | without_replacement | var | 1024 | 2 | [60, 81, 256, 729] | [53.845107609505796, 51.633912953570054, 44.399201788556596, 39.64665586980725] | [-1, -1, -1] |
| bound_single | without_replacement | val | 1024 | 2 | [60, 81, 256, 729] | [58.0, 58.0, 52.87590617856865, 46.750560732639826] | [0, -1, -1] |
| factored | with_replacement | joint | 1024 | 2 | [60, 81, 256, 729] | [29.309168449817616, 28.898829257094782, 24.681460344196214, 21.787743755793446] | [-1, -1, -1] |
| factored | with_replacement | var | 1024 | 2 | [60, 81, 256, 729] | [30.53729526138416, 28.98605939281616, 24.709605095870263, 21.787743755793446] | [-1, -1, -1] |
| factored | with_replacement | val | 1024 | 2 | [60, 81, 256, 729] | [58.0, 58.0, 58.0, 58.0] | [0, 0, 0] |
| factored | without_replacement | joint | 1024 | 2 | [60, 81, 256, 729] | [29.25273964234934, 29.005177933570298, 24.695724521669185, 21.78257553309042] | [-1, -1, -1] |
| factored | without_replacement | var | 1024 | 2 | [60, 81, 256, 729] | [30.377934342227434, 29.099249896135696, 24.723131145276533, 21.78257553309042] | [-1, -1, -1] |
| factored | without_replacement | val | 1024 | 2 | [60, 81, 256, 729] | [58.0, 58.0, 58.0, 58.0] | [0, 0, 0] |

K_eff fits:

| variant | replacement | metric | best_k_eff | n_points | r2_product | r2_Kvar | r2_max_factor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bound_single | with_replacement | joint | D_over_ln_product | 24 | 0.9888 | 0.9443 | 0.9443 |
| bound_single | without_replacement | joint | D_over_ln_product | 24 | 0.9884 | 0.9448 | 0.9448 |
| factored | with_replacement | joint | D_over_ln_Kvar | 24 | 0.9376 | 0.9775 | 0.9775 |
| factored | without_replacement | joint | D_over_ln_Kvar | 24 | 0.9386 | 0.9774 | 0.9774 |

- decision: `k_direction_negative`
- open: False

Decision: per-depth benchmark resolves the K-direction for the measured construction. With- and without-replacement agree: capacity is non-increasing in K on ceiling-free points. Bound-single is best fit by product codebook size, while factored is best fit by K_var / max-factor scaling. This upgrades the safe claim to linear in D and decreasing in effective codebook size, with a fitted constant rather than the raw D/(2 ln K) constant.

### 012. Implemented tuned GRUStack smoke with val-selected checkpoint

Purpose: start the clean labeled negative baseline required for Module 1 closeout. This smoke verifies the GRUStack interface, val-loss checkpoint selection, convergence metadata, and per-depth eval curve before launching the full GRU grid.

Code added:

- `register/gru_stack.py`
- `experiments/train_gru_stack.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m experiments.train_gru_stack --D 128 --K-var 60 --K-val 2 --replacement without_replacement --max-depth 8 --steps 80 --batch-size 512 --eval-every 20 --patience 3 --device cuda:0 --output-dir results/gru_stack_smoke
```

Artifacts:

- `results/gru_stack_smoke/results.json`
- `results/gru_stack_smoke/gru_stack_best.pt`

Smoke result:

- converged: True
- selection: `val_loss_min`
- frontier_joint_095: 0.0
- best_config: `{'best_val_loss': 3.436839669942856, 'learned_init': True, 'lr': 0.002, 'num_layers': 2}`

Decision: GRU smoke interface pass. This is not yet the closeout GRU grid; the full tuned GRU per-depth grid still needs to run before the GRU negative headline is final.

### 013. Ran tuned GRUStack full grid and structured comparison

Purpose: complete the clean labeled negative baseline. This full grid trains GRUStack cells with val-selected checkpoints and compares each matched D/K/replacement cell against the best structured register capacity from the per-depth benchmark.

Code added/used:

- `register/gru_stack.py`
- `experiments/train_gru_stack.py`
- `experiments/train_gru_stack_grid.py`
- `analysis/merge_gru_grid.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i ~/.local/bin/uv run --python .venv/bin/python python -u -m experiments.train_gru_stack_grid --mode full --device cuda:0 --num-shards 8 --shard-index $i --max-depth 32 --steps 600 --batch-size 1024 --eval-every 50 --patience 6 --output-dir results/gru_stack_grid_full/shard_$i & done; wait; ~/.local/bin/uv run --python .venv/bin/python python -m analysis.merge_gru_grid
```

Artifacts:

- `results/gru_stack_grid_full/results.json`
- `results/gru_stack_grid_full/curves.json`
- `results/gru_stack_grid_full/shard_*/cell_*/results.json`
- `results/gru_stack_grid_full/shard_*/cell_*/gru_stack_best.pt`

Result summary:

- cells: 144
- summary rows: 48
- all_converged: True
- all_gru_below_structured: True

Decision: tuned GRU negative baseline passes closeout checks. At every matched D/K/replacement cell, val-selected GRU capacity is below the best structured register capacity.

### 014. Ran scaffold gates and centralized validation

Purpose: keep the older scaffold gates auditable while the build pivots toward the three-module design. Validation records whether required files, schemas, and comparison checks pass.

Commands:

```bash
cd /home/aiscuser/stage_d_llm
python -m experiments.two_by_two_falsification
python -m experiments.d_stage_0_propagation
python -m experiments.d_stage_1_depth1_gate
python -m experiments.d_stage_2_capacity
python -m experiments.d_stage_3_vs_cot
python -m experiments.verifier_verification
python -m experiments.ttt_reversibility
python -m analysis.validate_outputs
python -m analysis.experiment_log
```

Artifacts:

- `results/two_by_two/results.json`
- `results/d_stage_0/results.json`
- `results/d_stage_1/results.json`
- `results/d_stage_2/results.json`
- `results/d_stage_3/results.json`
- `results/verifier/results.json`
- `results/ttt/results.json`
- `results/validation/validation.md`
- `results/experiment_log/experiment_log.md`

Validation summary:

- checks: 50
- passed: True

Decision: centralized validation pass. Continue using this log as the top-level experiment ledger, but treat scaffold gates as legacy/supporting evidence rather than the new Module 1 core claim.


## Preregistration Bands

| label | D | K | predicted d*_dyn |
| --- | --- | --- | --- |
| small_D_large_K | 256 | 729 | 19.42 |
| medium_D_large_K | 512 | 729 | 38.84 |
| small_D_medium_K | 256 | 60 | 31.26 |
| medium_D_medium_K | 512 | 60 | 62.53 |
| large_D_large_K | 1024 | 729 | 77.67 |
| offscreen_control | 4096 | 60 | 500.2 |

## Oracle Dataset

| task type | tasks | examples |
| --- | --- | --- |
| general_sat | 40 | 735 |
| graph_coloring | 40 | 360 |
| horn_sat | 24 | 216 |
| logic_grid | 40 | 465 |
| sudoku_4x4 | 40 | 680 |

## Operator Cache

| feature_source | hidden_dim | n_examples | cache |
| --- | --- | --- | --- |
| deterministic_hashed_prompt_fallback | 256 | 2456 | results/operator_cache/operator_cache.pt |

## Model Readiness

| field | value |
| --- | --- |
| transformers_available | True |
| cuda_available | True |
| cuda_device_count | 8 |
| recommended_cache_command | python -m analysis.operator_cache --load-model --limit 8 --output-name qwen_probe_cache |

## Model Downloads

| model | snapshot_path | n_files | total_gib |
| --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | /home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554 | 13 | 7.507 |
| Qwen/Qwen3-4B-Thinking-2507 | /home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea | 13 | 7.507 |

## Qwen Probe Cache

| feature_source | hidden_dim | n_examples | cache |
| --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | 2560 | 8 | results/operator_cache/qwen_probe_cache.pt |

## Qwen 128 Cache

| feature_source | hidden_dim | n_examples | cache |
| --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | 2560 | 128 | results/operator_cache/qwen_128_cache.pt |

## Qwen 128 Learned Wiring Smoke Test

| metric | value |
| --- | --- |
| action_accuracy | 0.5703 |
| var_accuracy | 0.3482 |
| val_accuracy | 0.4732 |
| verifier_accuracy | 0.8359 |
| n_examples | 128 |
| feature_source | Qwen/Qwen3-4B-Instruct-2507 |

## Qwen Balanced 320 Cache

| feature_source | hidden_dim | n_examples | seed_counts | cache |
| --- | --- | --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | 2560 | 320 | {'42': 64, '137': 64, '256': 64, '314': 64, '999': 64} | results/operator_cache/qwen_balanced_320_cache.pt |

## Qwen Balanced 320 Learned Wiring

| metric | value |
| --- | --- |
| train_action_accuracy | 0.8398 |
| holdout_action_accuracy | 0.8906 |
| train_var_accuracy | 0.3612 |
| holdout_var_accuracy | 0.2982 |
| train_val_accuracy | 0.652 |
| holdout_val_accuracy | 0.4912 |
| train_verifier_accuracy | 0.9688 |
| holdout_verifier_accuracy | 1 |
| n_train_examples | 256 |
| n_holdout_examples | 64 |
| holdout_seed | 999 |

## Module 1 Stack Capacity Quick

| method | D | K | predicted_d_star | frontier_decode_095 |
| --- | --- | --- | --- | --- |
| gru_proxy_last_pop | 64 | 60 | 7.816 | 0 |
| gru_proxy_last_pop | 128 | 60 | 15.63 | 0 |
| gru_proxy_last_pop | 256 | 60 | 31.26 | 1 |
| gru_proxy_last_pop | 64 | 729 | 4.855 | 0 |
| gru_proxy_last_pop | 128 | 729 | 9.709 | 0 |
| gru_proxy_last_pop | 256 | 729 | 19.42 | 0 |
| rotation_vsa | 64 | 60 | 7.816 | 3 |
| rotation_vsa | 128 | 60 | 15.63 | 3 |
| rotation_vsa | 256 | 60 | 31.26 | 15 |
| rotation_vsa | 64 | 729 | 4.855 | 1 |
| rotation_vsa | 128 | 729 | 9.709 | 4 |
| rotation_vsa | 256 | 729 | 19.42 | 9 |
| tape | 64 | 60 | 7.816 | 11 |
| tape | 128 | 60 | 15.63 | 23 |
| tape | 256 | 60 | 31.26 | 47 |
| tape | 64 | 729 | 4.855 | 6 |
| tape | 128 | 729 | 9.709 | 14 |
| tape | 256 | 729 | 19.42 | 29 |

## Module 1 Stack Capacity Full GPU

| method | D | K | predicted_d_star | frontier_decode_095 |
| --- | --- | --- | --- | --- |
| gru_proxy_sequence | 64 | 60 | 7.816 | 1 |
| gru_proxy_sequence | 128 | 60 | 15.63 | 1 |
| gru_proxy_sequence | 256 | 60 | 31.26 | 1 |
| gru_proxy_sequence | 512 | 60 | 62.53 | 1 |
| gru_proxy_sequence | 1024 | 60 | 125.1 | 1 |
| gru_proxy_sequence | 64 | 729 | 4.855 | 0 |
| gru_proxy_sequence | 128 | 729 | 9.709 | 0 |
| gru_proxy_sequence | 256 | 729 | 19.42 | 0 |
| gru_proxy_sequence | 512 | 729 | 38.84 | 0 |
| gru_proxy_sequence | 1024 | 729 | 77.67 | 0 |
| rotation_vsa | 64 | 60 | 7.816 | 1 |
| rotation_vsa | 128 | 60 | 15.63 | 3 |
| rotation_vsa | 256 | 60 | 31.26 | 7 |
| rotation_vsa | 512 | 60 | 62.53 | 15 |
| rotation_vsa | 1024 | 60 | 125.1 | 31 |
| rotation_vsa | 64 | 729 | 4.855 | 1 |
| rotation_vsa | 128 | 729 | 9.709 | 4 |
| rotation_vsa | 256 | 729 | 19.42 | 9 |
| rotation_vsa | 512 | 729 | 38.84 | 19 |
| rotation_vsa | 1024 | 729 | 77.67 | 38 |
| tape | 64 | 60 | 7.816 | 11 |
| tape | 128 | 60 | 15.63 | 23 |
| tape | 256 | 60 | 31.26 | 47 |
| tape | 512 | 60 | 62.53 | 93 |
| tape | 1024 | 60 | 125.1 | 188 |
| tape | 64 | 729 | 4.855 | 6 |
| tape | 128 | 729 | 9.709 | 14 |
| tape | 256 | 729 | 19.42 | 29 |
| tape | 512 | 729 | 38.84 | 57 |
| tape | 1024 | 729 | 77.67 | 116 |

Module 1 full notes: GRU is a lightweight trained full-sequence decoder from the bounded final state, not an exact inverse and not fully hyperparameter-tuned.


## Learned Wiring Baseline

| metric | value |
| --- | --- |
| train_action_accuracy | 0.9855 |
| holdout_action_accuracy | 0.4724 |
| train_var_accuracy | 0.373 |
| holdout_var_accuracy | 0.09247 |
| train_val_accuracy | 0.4536 |
| holdout_val_accuracy | 0.2065 |
| train_verifier_accuracy | 0.9865 |
| holdout_verifier_accuracy | 0.901 |
| holdout_seed | 999 |
| feature_source | deterministic_hashed_prompt_fallback |

## D.3 2x2 Falsification

| method | column | n_tasks | solve_rate | applied_reverts | max_required_depth |
| --- | --- | --- | --- | --- | --- |
| latent_only | propagation_only | 8 | 1 | 0 | 0 |
| latent_only | backtracking_required | 15 | 0 | 0 | 5 |
| latent_plus_structured_register | propagation_only | 8 | 1 | 0 | 0 |
| latent_plus_structured_register | backtracking_required | 15 | 1 | 31 | 5 |

## D-stage 0 Propagation

| depth | task_kind | solve_rate |
| --- | --- | --- |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |
| 0 | horn_sat | 1 |

## D-stage 1 Depth-1 Gate

| method | n_tasks | solve_rate | applied_reverts | max_required_depth |
| --- | --- | --- | --- | --- |
| latent_only | 10 | 0 | 0 | 1 |
| structured_register | 10 | 1 | 10 | 1 |
| gru_register | 10 | 0 | 0 | 1 |
| no_revert_ablation | 10 | 0 | 0 | 1 |

## D-stage 2 Capacity Frontier

| register | D | K | predicted_d_star | observed_frontier |
| --- | --- | --- | --- | --- |
| structured | 64 | 60 | 7.816 | 7 |
| structured | 64 | 729 | 4.855 | 4 |
| structured | 128 | 60 | 15.63 | 15 |
| structured | 128 | 729 | 9.709 | 9 |
| structured | 256 | 60 | 31.26 | 31 |
| structured | 256 | 729 | 19.42 | 19 |
| structured | 512 | 60 | 62.53 | 62 |
| structured | 512 | 729 | 38.84 | 38 |
| structured | 1024 | 60 | 125.1 | 125 |
| structured | 1024 | 729 | 77.67 | 77 |
| gru | 64 | 60 | None | 2 |
| gru | 64 | 729 | None | 2 |
| gru | 128 | 60 | None | 3 |
| gru | 128 | 729 | None | 3 |
| gru | 256 | 60 | None | 5 |
| gru | 256 | 729 | None | 4 |
| gru | 512 | 60 | None | 7 |
| gru | 512 | 729 | None | 6 |
| gru | 1024 | 60 | None | 11 |
| gru | 1024 | 729 | None | 8 |

## D-stage 3 Vs CoT

| D | K | method | predicted_d_star | last_solved_depth | matched_compute |
| --- | --- | --- | --- | --- | --- |
| 256 | 60 | latent_structured | 31.26 | 31 | True |
| 256 | 60 | qwen_thinking_cot | 31.26 | 15 | True |
| 256 | 60 | naive_pass_scaling | 31.26 | 1 | True |
| 4096 | 60 | latent_structured | 500.2 | 500 | True |
| 4096 | 60 | qwen_thinking_cot | 500.2 | 250 | True |
| 4096 | 60 | naive_pass_scaling | 500.2 | 1 | True |

## D.5 Verifier Verification

| mode | n_tasks | solve_rate | false_positive_reverts | false_negative_misses |
| --- | --- | --- | --- | --- |
| oracle | 20 | 1 | 0 | 0 |
| learned | 20 | 0.7 | 1 | 6 |
| noisy | 20 | 0.3 | 3 | 14 |
| disabled | 20 | 0 | 0 | 54 |

## D.6 TTT Reversibility

| structured_restore_error | ttt_restore_error | ratio |
| --- | --- | --- |
| 2.992e-06 | 0.0995 | 3.326e+04 |

## Analysis Summary

# Stage D Scaffold Analysis

These figures summarize oracle-trace scaffold outputs, not trained-model evaluations.

## Gates

- 2x2 falsification backtracking column: latent-only solve rate 0.00, structured-register solve rate 1.00.
- D-stage 1 depth-1 gate: structured-register solve rate 1.00 with 10 applied reverts.
- Verifier ablation: oracle solve rate 1.00, disabled solve rate 0.00.
- TTT diagnostic: restore-error ratio 33260.48.


## Validation Checks

| check | status | detail |
| --- | --- | --- |
| required_files_present | PASS | missing=[] |
| oracle_dataset_line_count | PASS | jsonl=2456, summary=2456 |
| oracle_dataset_actions_valid | PASS | invalid={} |
| oracle_dataset_has_all_actions | PASS | counts={'propagate': 1392, 'done': 184, 'branch': 680, 'revert': 200} |
| oracle_dataset_supervision | PASS | supervision=symbolic_oracle_trace |
| operator_cache_example_count | PASS | cache=2456, dataset=2456 |
| operator_cache_file_exists | PASS | results/operator_cache/operator_cache.pt |
| model_readiness_recorded | PASS | transformers_available=True, cuda_available=True |
| uv_transformers_available | PASS | transformers available in uv environment |
| qwen_instruct_downloaded | PASS | path=/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507/snapshots/cdbee75f17c01a7cc42f958dc650907174af0554 |
| qwen_thinking_downloaded | PASS | path=/home/aiscuser/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Thinking-2507/snapshots/768f209d9ea81521153ed38c47d515654e938aea |
| qwen_probe_cache_valid | PASS | hidden_dim=2560, n_examples=8 |
| qwen_128_cache_valid | PASS | hidden_dim=2560, n_examples=128 |
| qwen_128_learned_wiring_recorded | PASS | action_accuracy=0.5703, verifier_accuracy=0.8359 |
| qwen_balanced_320_cache_valid | PASS | seed_counts={'42': 64, '137': 64, '256': 64, '314': 64, '999': 64} |
| qwen_balanced_320_holdout_action | PASS | holdout_action_accuracy=0.8906 |
| module1_quick_result_present | PASS | rows=84, summary=18 |
| module1_rotation_nonzero_frontier | PASS | frontiers=[3, 3, 15, 1, 4, 9] |
| module1_rotation_beats_gru_proxy | PASS | rotation frontier >= matched GRU proxy frontier |
| module1_tape_upper_bound | PASS | tape frontier >= rotation frontier |
| module1_full_gpu_result_present | PASS | rows=432, summary=30, seeds=[42, 137, 256] |
| module1_full_rotation_beats_gru_proxy | PASS | rotation frontier >= matched GRU proxy frontier |
| module1_full_tape_upper_bound | PASS | tape frontier >= rotation frontier |
| module1_capacity_benchmark_full_sharded_present | PASS | rows=1476, summary=100 |
| module1_constant_calibrated | PASS | c=8.545489937800552 |
| module1_k_direction_recorded | PASS | decision=k_inversion_or_nonmonotonic_open, open=True |
| module1_k_direction_ceiling_corrected | PASS | target=theory_consistent, dropped=[(9, 9), (20, 20)] |
| module1_diagnostic_full_sharded_present | PASS | rows=648, summary=36 |
| module1_diagnostic_k_direction_recorded | PASS | decision=k_direction_open_or_inverted, open=True |
| module1_perdepth_k_direction_negative | PASS | decision=k_direction_negative, open=False |
| module1_perdepth_with_without_agree | PASS | all joint/var/val directions are non-increasing for with/without replacement |
| module1_perdepth_keff_fit_recorded | PASS | best={('bound_single', 'with_replacement'): 'D_over_ln_product', ('bound_single', 'without_replacement'): 'D_over_ln_product', ('factored', 'with_replacement'): 'D_over_ln_Kvar', ('factored', 'without_replacement'): 'D_over_ln_Kvar'} |
| module1_batching_recorded | PASS | best_batches=[8192, 8192, 8192, 16384] |
| module1_gru_smoke_converged | PASS | frontier=0.0, checkpoint=results/gru_stack_smoke/gru_stack_best.pt |
| module1_gru_converged | PASS | cells=144, summary=48 |
| module1_gru_below_structured | PASS | GRU capacity below best structured capacity at every matched cell |
| learned_wiring_example_count | PASS | learned=2456, cache=2456 |
| learned_wiring_model_exists | PASS | results/learned_wiring/heads.pt |
| learned_wiring_action_accuracy | PASS | action_accuracy=0.9855 |
| learned_wiring_verifier_accuracy | PASS | verifier_accuracy=0.9865 |
| two_by_two_schema | PASS | required metric fields non-null |
| d_stage_1_schema | PASS | required metric fields non-null |
| d_stage_2_schema | PASS | required metric fields non-null |
| d_stage_3_schema | PASS | required metric fields non-null |
| verifier_schema | PASS | required metric fields non-null |
| d3_two_by_two_gate | PASS | structured helps only backtracking column |
| d_stage_1_gate | PASS | structured reverts; GRU/no-revert collapse |
| d_stage_3_ordering | PASS | latent_structured >= CoT >= naive last solved depth |
| d5_verifier_monotonic | PASS | oracle >= learned >= noisy >= disabled |
| d6_ttt_reversibility | PASS | TTT restore error greater than structured |
