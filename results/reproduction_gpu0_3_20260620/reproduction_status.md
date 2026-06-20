# GPU0-3 Reproduction Status

Generated: 2026-06-20

Purpose: track reproducibility of the single-agent floor-paper experiment ledger on GPUs 0-3. Large JSON outputs under `results/reproduction_gpu0_3_20260620/` are local artifacts and may be ignored by git; item JSONs record summaries and paths.

## Completed

| item(s) | experiment | output root | result |
| --- | --- | --- | --- |
| 100 | Qwen3.5 KM-3 exactness fail-closed | `results/reproduction_gpu0_3_20260620/exactness_gates/` | reproduced fail: `KVCACHE_EXACTNESS_GATE_FAIL`, max delta 6.75, argmax not all equal |
| 102 | pure-KV Qwen3 KM-3 exactness | `results/reproduction_gpu0_3_20260620/exactness_gates/` | reproduced: bf16 fail, fp32 strict fail, fp32 tol=1e-3 pass |
| 105 | decision probe Part 1 | `results/reproduction_gpu0_3_20260620/item105_decision_probe/` | reproduced 1080 rows; DP_1=false, DP_2=false, clean backtrack weak |
| 162/163 | C1.2 real Mamba checkpoint flip | `results/c1_2_architecture_restore_characterization/item162_repro_gpu0_3_20260620/` | reproduced independently on GPUs 0,1,2,3; all LOCKED / TRADE-OFF-FLIPS |
| 155 / C1.6 | A_cache vs C_incontext primary matched budget | `results/reproduction_gpu0_3_20260620/ac_primary_scaled_n64/` | reproduced sudoku gap 0.78125 and futoshiki gap 0.703125 at B* |

## Running / Next

| target | planned root | note |
| --- | --- | --- |
| graph_color C1 budget / targeting if needed | `results/reproduction_gpu0_3_20260620/graph_color_c1_budget/` | can be restricted to SHARDS=4 on GPU0-3 |
| HB-2 external LFS/ToT/RAP/best-of-n | TBD | executable launchers exist, but full runs are long and should be scheduled one baseline at a time |

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
