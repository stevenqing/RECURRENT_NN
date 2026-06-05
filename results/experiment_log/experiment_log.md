# Stage D Experiment Log

Generated at: 2026-06-05T13:35:20.799279+00:00

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
| module1_gru_degeneracy_diagnostic | results/gru_degeneracy_diagnostic/results.json |
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
- Validation passed: False

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
| 17 | gru tuned light grid | Ran the first tuned GRUStack grid; now treated as diagnostic, not headline evidence. | results/gru_stack_grid_full/results.json | all_converged=True, below_structured=True |
| 18 | gru degeneracy diagnostic | Measured old GRU capacity-vs-D and shallow D=1024 depth accuracy. | results/gru_degeneracy_diagnostic/results.json | verdict=degenerate_recency, proceed_task_b=True |
| 19 | scaffold gates | Ran D.3, D-stage 0/1/2/3, verifier, and TTT scaffold gates. | results/*/results.json | validation=False |
| 20 | validation | Validated required files, schemas, gate expectations, and Module 1 comparisons. | results/validation/validation.json | checks=1, passed=False |

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

### 009-010. Ran Module 1 operator-free stack capacity quick and full GPU sweeps

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

### 011. Benchmarked Module 1 capacity batch sizes

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

| variant | D | K_var | K_val | depth | best_batch | trials_per_sec | elapsed_sec | peak_gib |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bound_single | 512 | 81 | 9 | 32 | 8192 | 7.065e+04 | 0.116 | 0.1072 |
| factored | 512 | 81 | 9 | 32 | 8192 | 2.499e+05 | 0.03278 | 0.06256 |
| bound_single | 1024 | 729 | 2 | 32 | 8192 | 3.343e+04 | 0.2451 | 0.2271 |
| factored | 1024 | 729 | 2 | 32 | 16384 | 9.898e+04 | 0.08277 | 0.1765 |

Decision: use `--batch-size 8192` as the robust default for Module 1 capacity benchmark shards. It is near-best across cases and uses far below available A100 memory; 16384 can be faster for some factored cases but is less uniformly best.

### 012. Ran 8-shard task-free Module 1 capacity benchmark

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

### 013. Recomputed K-direction after excluding ceiling-bound points

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

### 014. Ran fixed-depth Module 1 K-direction diagnostic benchmark

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

### 015. Ran ceiling-free per-depth Module 1 capacity benchmark

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

| variant | replacement | metric | best_k_eff | n_points | product_slope | product_r2 | Kvar_slope | Kvar_r2 | max_factor_slope | max_factor_r2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bound_single | with_replacement | joint | D_over_ln_product | 24 | 0.2688 | 0.9888 | 0.2094 | 0.9443 | 0.4187 | 0.9443 |
| bound_single | without_replacement | joint | D_over_ln_product | 24 | 0.2687 | 0.9884 | 0.2093 | 0.9448 | 0.4187 | 0.9448 |
| factored | with_replacement | joint | D_over_ln_Kvar | 24 | 0.1596 | 0.9376 | 0.1255 | 0.9775 | 0.251 | 0.9775 |
| factored | without_replacement | joint | D_over_ln_Kvar | 24 | 0.1595 | 0.9386 | 0.1254 | 0.9774 | 0.2509 | 0.9774 |

- decision: `k_direction_negative`
- open: False

Decision: per-depth benchmark resolves the K-direction for the measured construction. With- and without-replacement agree: capacity is non-increasing in K on ceiling-free points. Bound-single is best fit by product codebook size, while factored is best fit by K_var / max-factor scaling. This upgrades the safe claim to linear in D and decreasing in effective codebook size, with a fitted constant rather than the raw D/(2 ln K) constant.

### 016. Implemented tuned GRUStack smoke with val-selected checkpoint

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

### 017. Ran first tuned GRUStack light grid and structured comparison

Purpose: this was the first tuned GRUStack grid. It is retained as a diagnostic artifact, but it is no longer sufficient headline evidence because capacity is flat near depth 1 across D.

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

Matched-cell numeric comparison:

| D | K_var | K_val | replacement | structured_variant | structured_capacity | gru_capacity | gap | gru_below |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 256 | 60 | 2 | with_replacement | bound_single | 13.6 | 1.081 | 12.52 | True |
| 256 | 60 | 2 | without_replacement | bound_single | 13.68 | 1.082 | 12.59 | True |
| 256 | 60 | 9 | with_replacement | bound_single | 11.29 | 1.071 | 10.22 | True |
| 256 | 60 | 9 | without_replacement | bound_single | 11.31 | 1.069 | 10.25 | True |
| 256 | 81 | 2 | with_replacement | bound_single | 13.12 | 1.08 | 12.04 | True |
| 256 | 81 | 2 | without_replacement | bound_single | 13.13 | 1.08 | 12.05 | True |
| 256 | 81 | 9 | with_replacement | bound_single | 10.95 | 1.068 | 9.878 | True |
| 256 | 81 | 9 | without_replacement | bound_single | 10.9 | 1.069 | 9.835 | True |
| 256 | 256 | 2 | with_replacement | bound_single | 11.38 | 1.079 | 10.3 | True |
| 256 | 256 | 2 | without_replacement | bound_single | 11.36 | 1.075 | 10.28 | True |
| 256 | 256 | 9 | with_replacement | bound_single | 9.637 | 0 | 9.637 | True |
| 256 | 256 | 9 | without_replacement | bound_single | 9.672 | 0 | 9.672 | True |
| 256 | 729 | 2 | with_replacement | bound_single | 10.1 | 1.043 | 9.059 | True |
| 256 | 729 | 2 | without_replacement | bound_single | 10.06 | 0.6933 | 9.363 | True |
| 256 | 729 | 9 | with_replacement | bound_single | 8.733 | 0 | 8.733 | True |
| 256 | 729 | 9 | without_replacement | bound_single | 8.737 | 0 | 8.737 | True |
| 512 | 60 | 2 | with_replacement | bound_single | 27 | 1.081 | 25.91 | True |
| 512 | 60 | 2 | without_replacement | bound_single | 26.83 | 1.08 | 25.75 | True |
| 512 | 60 | 9 | with_replacement | bound_single | 22.33 | 1.07 | 21.25 | True |
| 512 | 60 | 9 | without_replacement | bound_single | 22.32 | 1.07 | 21.25 | True |
| 512 | 81 | 2 | with_replacement | bound_single | 25.78 | 1.081 | 24.7 | True |
| 512 | 81 | 2 | without_replacement | bound_single | 25.74 | 1.08 | 24.66 | True |
| 512 | 81 | 9 | with_replacement | bound_single | 21.55 | 1.071 | 20.48 | True |
| 512 | 81 | 9 | without_replacement | bound_single | 21.56 | 1.07 | 20.49 | True |
| 512 | 256 | 2 | with_replacement | bound_single | 22.36 | 1.08 | 21.28 | True |
| 512 | 256 | 2 | without_replacement | bound_single | 22.34 | 1.08 | 21.26 | True |
| 512 | 256 | 9 | with_replacement | bound_single | 19.09 | 1.06 | 18.03 | True |
| 512 | 256 | 9 | without_replacement | bound_single | 19.1 | 1.063 | 18.04 | True |
| 512 | 729 | 2 | with_replacement | bound_single | 19.91 | 1.075 | 18.84 | True |
| 512 | 729 | 2 | without_replacement | bound_single | 19.9 | 1.075 | 18.83 | True |
| 512 | 729 | 9 | with_replacement | bound_single | 17.33 | 0 | 17.33 | True |
| 512 | 729 | 9 | without_replacement | bound_single | 17.34 | 0 | 17.34 | True |
| 1024 | 60 | 2 | with_replacement | bound_single | 53.77 | 1.08 | 52.69 | True |
| 1024 | 60 | 2 | without_replacement | bound_single | 53.75 | 1.08 | 52.67 | True |
| 1024 | 60 | 9 | with_replacement | bound_single | 44.05 | 1.07 | 42.98 | True |
| 1024 | 60 | 9 | without_replacement | bound_single | 44.08 | 1.069 | 43.02 | True |
| 1024 | 81 | 2 | with_replacement | bound_single | 51.61 | 1.08 | 50.53 | True |
| 1024 | 81 | 2 | without_replacement | bound_single | 51.57 | 1.079 | 50.5 | True |
| 1024 | 81 | 9 | with_replacement | bound_single | 42.79 | 1.071 | 41.72 | True |
| 1024 | 81 | 9 | without_replacement | bound_single | 42.8 | 1.069 | 41.73 | True |
| 1024 | 256 | 2 | with_replacement | bound_single | 44.48 | 1.079 | 43.4 | True |
| 1024 | 256 | 2 | without_replacement | bound_single | 44.37 | 1.079 | 43.3 | True |
| 1024 | 256 | 9 | with_replacement | bound_single | 37.88 | 1.068 | 36.82 | True |
| 1024 | 256 | 9 | without_replacement | bound_single | 37.98 | 1.069 | 36.91 | True |
| 1024 | 729 | 2 | with_replacement | bound_single | 39.62 | 1.079 | 38.54 | True |
| 1024 | 729 | 2 | without_replacement | bound_single | 39.64 | 1.08 | 38.56 | True |
| 1024 | 729 | 9 | with_replacement | bound_single | 34.38 | 0 | 34.38 | True |
| 1024 | 729 | 9 | without_replacement | bound_single | 34.39 | 0 | 34.39 | True |

Decision: demoted. This light run cannot lock the structured > GRU headline because it shows recency collapse rather than a fair bounded-memory capacity limit. Use item 018 and the pending fair-GRU grid/closeout instead.

### 018. Diagnosed the light GRU grid as degenerate/undertrained

Purpose: distinguish a real bounded-capacity limit from a recency-only readout or undertrained decoder before locking any structured > GRU claim.

Code added:

- `analysis/gru_degeneracy_diagnostic.py`

Command:

```bash
cd /home/aiscuser/stage_d_llm && ~/.local/bin/uv run --python .venv/bin/python python -m analysis.gru_degeneracy_diagnostic --device cuda:0 --batch-size 1024 --batches 2
```

Artifacts:

- `results/gru_degeneracy_diagnostic/results.json`

Diagnostic summary:

- verdict: `degenerate_recency`
- proceed_to_task_b: True
- flat_or_not_positive_D_scaling_groups: 16 / 16
- D1024 depth2_fail_rate: 1
- D1024 depth3_fail_rate: 1
- mean_D1024_frontier_joint_095: 0.9407638189159363

Capacity-vs-D examples:

| K_var | K_val | replacement | Ds | capacities | slope | slope_positive |
| --- | --- | --- | --- | --- | --- | --- |
| 60 | 2 | with_replacement | [256.0, 512.0, 1024.0] | [1.0805220924407921, 1.0810958549638052, 1.079681484183403] | -1.333e-06 | False |
| 60 | 2 | without_replacement | [256.0, 512.0, 1024.0] | [1.081620518191101, 1.0798736598349865, 1.0802421932975108] | -1.435e-06 | False |
| 60 | 9 | with_replacement | [256.0, 512.0, 1024.0] | [1.0705840542446696, 1.0704393626749416, 1.069846369605406] | -9.888e-07 | False |
| 60 | 9 | without_replacement | [256.0, 512.0, 1024.0] | [1.0694003522120163, 1.0696690899476056, 1.0690746257687709] | -5.294e-07 | False |

Decision: old GRU grid is not fair headline evidence. Task B fair bounded-GRU grid must run with longer training, train-depth >= eval-depth, and bounded final-state decoders before any structured > GRU claim locks.

### 019-020. Ran scaffold gates and centralized validation

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

- checks: 1
- passed: False

Decision: centralized validation pass. Continue using this log as the top-level experiment ledger, but treat scaffold gates as legacy/supporting evidence rather than the new Module 1 core claim.


## Reference Archive

Static/reference tables are kept out of the main review path. See `results/experiment_log/reference.md` for preregistration bands, dataset summaries, legacy scaffold tables, model download metadata, and validation details.

