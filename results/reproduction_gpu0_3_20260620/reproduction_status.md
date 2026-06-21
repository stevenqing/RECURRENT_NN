# GPU0-3 Reproduction Status

Generated: 2026-06-20

Purpose: track reproducibility of the single-agent floor-paper experiment ledger on GPUs 0-3. Large JSON outputs under `results/reproduction_gpu0_3_20260620/` are local artifacts and may be ignored by git; item JSONs record summaries and paths.

## Reproduction Mode

The current GPU0-3 campaign uses two labels:

- faithful rerun: the original item has executable commands in the local ledger and the rerun uses the same runner/scope or a documented GPU0-3 shard equivalent.
- reconstructed rerun: the original item was recovered from summary-only conversation state or points at absent cluster artifacts, so the rerun is rebuilt from the tracked repo runners, specs, and recorded result schema. These are valid engineering reproductions, but are not claimed as byte-for-byte original command replays.

## Coverage Audit

| item range | local command state | GPU0-3 reproduction state | action |
| --- | --- | --- | --- |
| 100, 102, 105 | executable local commands | completed faithful reruns | keep as locked reference gates |
| 162/163 | reconstructed runner now tracked; executable local commands for rerun | completed reconstructed/fidelity rerun on GPUs 0-3 | keep as C1.2 headline gate |
| 155 / C1.6 primary CSP | tracked runner and launcher available | completed reconstructed rerun for sudoku/futoshiki plus graph_color symbolic/C1 | continue with external baselines |
| 101, 103-133 | executable local commands exist | 101,122,123 completed in this GPU0-3 campaign; other historical items not in default campaign | schedule by risk/cost, one batch at a time |
| 134-141, 148 | no authoritative local item JSON | blocked for faithful replay | pull cluster records or reconstruct from tracked specs/runners |
| 142-162 recovered summaries | summary tables present; most original commands absent | reconstructed reruns only unless commands are recovered | rebuild commands from tracked runners and record as new items |

## Completed

| item(s) | experiment | output root | result |
| --- | --- | --- | --- |
| 100 | Qwen3.5 KM-3 exactness fail-closed | `results/reproduction_gpu0_3_20260620/exactness_gates/` | reproduced fail: `KVCACHE_EXACTNESS_GATE_FAIL`, max delta 6.75, argmax not all equal |
| 102 | pure-KV Qwen3 KM-3 exactness | `results/reproduction_gpu0_3_20260620/exactness_gates/` | reproduced: bf16 fail, fp32 strict fail, fp32 tol=1e-3 pass |
| 105 | decision probe Part 1 | `results/reproduction_gpu0_3_20260620/item105_decision_probe/` | reproduced 1080 rows; DP_1=false, DP_2=false, clean backtrack weak |
| 162/163 | C1.2 real Mamba checkpoint flip | `results/c1_2_architecture_restore_characterization/item162_repro_gpu0_3_20260620/` | reproduced independently on GPUs 0,1,2,3; all LOCKED / TRADE-OFF-FLIPS |
| 155 / C1.6 | A_cache vs C_incontext primary matched budget | `results/reproduction_gpu0_3_20260620/ac_primary_scaled_n64/` | reproduced sudoku gap 0.78125 and futoshiki gap 0.703125 at B* |
| 101 | Qwen3.5 full-cache checkpoint gate | `results/reproduction_gpu0_3_20260620/exactness_gates/` | bf16 fail reproduced; fp32 passes in current environment, recorded as environment-sensitive divergence |
| 122 | graph_color symbolic A/C budget curve | `results/reproduction_gpu0_3_20260620/graph_color_symbolic_n64/` | reproduced n=64: B*=22901, A=1.0, C=0.40625, gap=0.59375 |
| 123 | graph_color C1 A/C budget curve | `results/reproduction_gpu0_3_20260620/graph_color_c1_budget_n64/` | reproduced n=64: B*=32895, A=0.96875, C=0.515625, gap=0.453125 |
| 166 | automated GPU0-3 reproduction campaign | `scripts/reproduce_gpu0_3_campaign.sh` | orchestrator added; manifest, graph_color symbolic/C1, Item101, registry, and log regeneration completed |
| 167 | ToT/RAP corrected reproduction push snapshot | `results/reproduction_gpu0_3_20260620/hb2_tot_rap/` | strict smoke passed; full-grid running, snapshot 39/1920 rows, bad_zero_budget=0, code pushed at `bb64972` |
| 168 | ToT/RAP vLLM backend restore | `analysis/kvcache_tot_rap_baselines.py` and `scripts/launch_hb2_tot_rap_vllm_multi_server*.sh` | backend/launchers restored and smoke-tested with fake OpenAI server; not launched while direct full-grid is running |

## Running / Next

| target | planned root | note |
| --- | --- | --- |
| HB-2 external LFS/ToT/RAP/best-of-n | `results/reproduction_gpu0_3_20260620/hb2_*` when enabled | executable launchers exist; run with `RUN_EXTERNAL_FULL=1 scripts/reproduce_gpu0_3_campaign.sh` |
| non-default historical executable items | per-item roots | Items 103-133 outside campaign core remain schedulable by cost/relevance |

## Current Running Jobs

| target | root | command | snapshot |
| --- | --- | --- | --- |
| ToT/RAP full-grid n64 | `results/reproduction_gpu0_3_20260620/hb2_tot_rap/full_grid_n64_gpu0_3/` | `RUN_EXTERNAL_FULL=1 HB2_BASELINES=tot_rap STAGES=hb2_external_full EXTERNAL_SHARDS=8 GPUS=4 HB2_INSTANCES=64 HB2_TASKS=sudoku,futoshiki,graph_color HB2_BUDGET_SCALES=0.25,0.5,1,2,4 scripts/reproduce_gpu0_3_campaign.sh` | running on GPU0-3; snapshot at Item167: 39/1920 rows, statuses `NO_FRONTIER=30; SOLVED=2; BUDGET_EXHAUSTED=7`, `bad_zero_budget=0` |

The ToT/RAP run is deliberately separated from LFS and best-of-n so any baseline-specific issue remains easy to isolate. Valid `BUDGET_EXHAUSTED` rows may occur after real search work; the quarantined bug is the zero-work premature exhaustion path.

ToT/RAP vLLM support is now restored for a separate future backend root. Do not mix direct Transformers checkpoints with vLLM checkpoints; launch vLLM only under a distinct root after the current direct run is complete or explicitly retired.

## Automation

Use the sequential GPU0-3 orchestrator:

```bash
scripts/reproduce_gpu0_3_campaign.sh
```

The script checks the environment, writes a reproduction manifest, then runs each stage in order with checkpoint/resume and artifact-based skip checks. By default it runs the core faithful/reconstructed campaign through graph_color symbolic and the external registry, but skips the long HB-2 full grid unless explicitly enabled. Re-running it now skips completed artifacts and continues only missing stages:

```bash
RUN_EXTERNAL_FULL=1 scripts/reproduce_gpu0_3_campaign.sh
```

Useful controls: `DRY_RUN=1`, `FORCE=1`, `STAGES=graph_color_symbolic,external_registry`, `RUN_ROOT=...`, `SHARDS=4`, `DECISION_SHARDS=4`, `GRAPH_SYMBOLIC_SHARDS=4`, `GRAPH_C1_SHARDS=4`, `AC_SHARDS=8`, and `EXTERNAL_SHARDS=8`.

## Active Reconstructed Runs

| target | root | command | state |
| --- | --- | --- | --- |
| Item123 graph_color C1 matched-budget n64 | `results/reproduction_gpu0_3_20260620/graph_color_c1_budget_n64/` | `ROOT=results/reproduction_gpu0_3_20260620/graph_color_c1_budget_n64 SHARDS=4 scripts/launch_graph_color_c1_budget.sh` | completed: 64 traces, B*=32895, A=0.96875, C=0.515625, gap=0.453125, promotion=true |
| Item122 graph_color symbolic matched-budget n64 | `results/reproduction_gpu0_3_20260620/graph_color_symbolic_n64/` | `STAGES=graph_color_symbolic scripts/reproduce_gpu0_3_campaign.sh` | completed: B*=22901, A=1.0, C=0.40625, gap=0.59375, promotion=true |

## Blocked Without Cluster Pull

| item(s) | blocker | required action |
| --- | --- | --- |
| 134-141, 148 | authoritative item JSONs absent locally | pull `results/experiment_items/item_*.json` from cluster |
| 142-162 recovered summaries | most recovered JSONs contain summary tables but no original executable commands | pull authoritative cluster JSONs/scripts or preregister reconstructed rerun commands |
| 139-140 | formal blocks not recovered locally | pull original R1 attention-readout items from cluster |

## Policy

- Use GPU0-3 only for reproduction unless explicitly redirected.
- Do not kill or preempt external vLLM, training, or ablation processes.
- Record every completed reproduction batch as a new experiment item.
