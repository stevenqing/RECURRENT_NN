# RECURRENT_NN Controlled Backtracking Ledger

Generated at: 2026-06-07T10:03:49.264160+00:00

Scope: canonical continuation ledger for `/home/aiscuser/RECURRENT_NN`. This replaces the older Stage D oracle-trace scaffold front page; legacy constructed scaffold gates are archived below.

## Canonical Repo Decision

- Canonical repo: `/home/aiscuser/RECURRENT_NN`
- Legacy path `/home/aiscuser/stage_d_llm`: not present locally; old commands using that path are historical provenance text.
- Module 1 artifacts are referenced from the current repo only; no local duplicate `stage_d_llm/results/` tree exists to de-duplicate.

## Evidence Tiers

### Tier A - Writable Now
- Module 1 capacity law: per-depth ceiling-free K-direction negative; bound_single best K_eff = D_over_ln_product with R2 about 0.99; factored best K_eff = D_over_ln_Kvar/max-factor with R2 about 0.98; capacity is linear in D for the measured construction.
- Ceiling-artifact resolution narrative for low-K frontier artifacts.
- Fair GRU 144-cell grid completed; all cells below structured; max GRU/structured ratio 0.9025; closeout honestly NOT_READY pending in-loop arbiter.
- TTT irreversibility remains real mechanism evidence when its non-scaffold artifact is present; the constructed scaffold gate is archived.
- M2.0 negatives: frozen Qwen operator still needs a fix; invalid qwen_guess rate and spike precision/recall asymmetry block direct loop use.

### Tier B - In Flight, Blocks Core Claim
- Stage A in-loop proof blocks the core claim.
- Banded Sudoku9/6 readiness and fail-closed refusal are materialized in post-026 artifacts, with Sudoku6 data still recorded as continuation-state readiness rather than generated in-repo data.
- Fail-closed preflight is proven for missing/quarantined parent paths; unsafe paths are refused.
- Current blocker: G1 = 0.0 on the Sudoku6 bridge operator.

### Tier C - Not Started
- W3 Qwen3.5 probe: checkpoint and metadata/capacity estimate are implemented; hidden-hook, gating-survival, native-delta, and W3.2 propagation probes are not launched.
- S2 accounting rides on the controlled relaunch.
- TRM defensive depth-ceiling analysis is not started.
- S3.1 integration is not started.

## Current Gate And Blocker Status

| area | status | evidence |
| --- | --- | --- |
| Module 1 capacity law | GREEN | decision=k_direction_negative; open=False; K_eff fits recorded |
| Fair GRU closeout | YELLOW | classification=NOT_READY; max_ratio=0.9025; headline_locked=False |
| M2.0 frozen Qwen operator | RED | verdict=PER_TASK_ROUTING; list_all_recall=0.3771; single_precision=0.4322 |
| Branch policy | YELLOW | qwen_nodes=4.939; mrv_nodes=5.067; qwen_invalid_rate=0.2316 |
| Stage A in-loop proof | RED | n_cells=0; statuses=['PARENT_ADAPTER_REQUIRED']; G1=0.0 |
| W3 Qwen3.5 | YELLOW | integration_grade=do_not_integrate_yet; W3.0=PASS |
| Validation | RED | checks=81; pass=72; fail=9 |

## Artifact Index

| artifact | path | present |
| --- | --- | --- |
| canonical_repo_note | CANONICAL_REPO.md | yes |
| environment_spec | ENV_SPEC.md | yes |
| post_027_continuation_state | results/continuation_state/post_027.json | yes |
| model_readiness | results/model_readiness/readiness.json | yes |
| qwen3_4b_instruct_download | results/model_download/qwen_download.json | yes |
| qwen3_4b_thinking_download | results/model_download/thinking/qwen_download.json | yes |
| qwen3_5_4b_download | results/model_download/qwen3_5_4b/qwen_download.json | yes |
| module1_capacity_perdepth | results/module1_capacity_perdepth_shards/results.json | yes |
| module1_k_direction_corrected | results/module1_capacity_benchmark_full_shards/k_direction_corrected.json | yes |
| module1_capacity_batching | results/module1_capacity_batching_large/results.json | yes |
| gru_stack_smoke | results/gru_stack_smoke/results.json | yes |
| gru_stack_grid_full_legacy | results/gru_stack_grid_full/results.json | yes |
| gru_degeneracy_diagnostic | results/gru_degeneracy_diagnostic/results.json | yes |
| gru_stack_grid_fair | results/gru_stack_grid_fair/results.json | yes |
| gru_vs_structured_closeout | results/gru_vs_structured_closeout/results.json | yes |
| m2_operator_probe | results/m2_operator_probe/report.json | yes |
| m2_operator_fix_rescale | results/m2_operator_probe/report_fix_rescale.json | yes |
| g1_fix_spec | specs/g1_fix_spec.md | yes |
| stage_a_reconstructed_artifacts | artifacts/stage_a/manifest.json | yes |
| stage_a_backtrack | results/stage_a_backtrack/report.json | yes |
| post025_adapter_wiring | results/stage_a_adapter_wiring/results.json | yes |
| post026_banded_gate_refusal | results/stage_a_banded_gate_refusal/results.json | yes |
| post027_sudoku6_bridge | results/stage_a_sudoku6_bridge/results.json | yes |
| w3_qwen35_probe_spec | specs/w3_qwen35_probe_spec.md | yes |
| w3_qwen35_probe | results/w3_qwen35_probe/results.json | yes |
| validation | results/validation/validation.json | yes |

## Incremental Run Items

| item | name | status | key result |
| --- | --- | --- | --- |
| 001-018 | legacy scaffold and early Module 1 setup | Archived | Retained in reference archive; not front-page gate evidence. |
| 019-020 | scaffold gates and old validation | Demoted | Constructed-true 2x2/D-stage/verifier gates moved to legacy archive. |
| 021 | M2.0 frozen operator probe | Done | verdict=NEEDS_OPERATOR_FIX; low forced recall/precision blocks direct loop. |
| 022 | M2.0 fix-rescale probe | Done | verdict=PER_TASK_ROUTING; branch_decision=qwen_guess_beats_mrv_reconsider |
| 023 | Module 1 fair GRU closeout | Done, not locked | classification=NOT_READY; max_ratio=0.9025; lock=False |
| 024 | Stage A reconstructed handoff | Blocked | verdict=NEEDS_REVIEW; statuses=['PARENT_ADAPTER_REQUIRED']; n_cells=0 |
| 025 | adapter wiring pass | RECORDED_FROM_RUNBOOK | Adapter wiring pass exists in the post-024 continuation state; source artifact was not found in this workspace scan. |
| 026 | banded Sudoku9 plus gate refusal | RECORDED_FROM_RUNBOOK | Banded Sudoku9/Sudoku6 datasets are treated as ready by the continuation state; fail-closed gate refusal is part of the current truth. |
| 027 | Sudoku6 bridge G1 | BLOCKER | G1=0.0; The Stage A critical blocker is G1 = 0.0 on the Sudoku6 bridge operator. |
| P0 | ledger and validation housekeeping | Updated | validation_checks=81; validation_passed=False |
| W3.0 | Qwen3.5 checkpoint pin | Done | model_id=Qwen/Qwen3.5-4B; total_gib=8.701 |
| P1 | G1 fix spec and diagnostics | Specified | g1_fix_spec plus Stage A adapter/gate/Sudoku6 diagnostic artifacts are present; retraining not launched. |
| P2 | W3 Qwen3.5 probe | do_not_integrate_yet | W3.0=PASS; W3.1/W3.2 heavy probes not launched. |
| P3 | TRM defensive analysis | Not launched | No TRM checkpoint/test-set grading code is present in this repo yet. |
| Module1 law | per-depth capacity | Writable now | decision=k_direction_negative; open=False; shards=8 |

## Validation Summary

| tier | pass | fail |
| --- | --- | --- |
| env | 13 | 0 |
| legacy | 0 | 6 |
| p0 | 2 | 0 |
| tier_a | 35 | 0 |
| tier_b | 17 | 3 |
| tier_c | 5 | 0 |

## P0/P1/P2/P3 Execution Notes

- P0.1: `RECURRENT_NN` is declared canonical in `CANONICAL_REPO.md`; the old `stage_d_llm` path is not present locally.
- P0.2: validation now emits many checks, including explicit red Stage A blockers, rather than one collapsed required-files failure.
- P0.3: the front page now leads with evidence tiers and current blockers; constructed scaffold gates are demoted to the legacy archive.
- P1: `specs/g1_fix_spec.md` plus adapter wiring, gate refusal, and Sudoku6 bridge diagnostic artifacts are present; the actual bridge retrain is not launched and G1 remains 0.0.
- P2: `specs/w3_qwen35_probe_spec.md` and metadata-only W3 probe are present for `Qwen/Qwen3.5-4B`; hidden-hook and heavy propagation probes are still explicit follow-up jobs.
- P3: TRM defensive analysis is not launched; no TRM checkpoint/test-set grading code is present in this repo yet.

## Legacy Scaffold Archive

The older 2x2, D-stage, verifier, and scaffold TTT entries are no longer front-page gate evidence. They were constructed scaffold outputs and are retained only as historical support/provenance. The real TTT irreversibility diagnostic remains Tier A mechanism evidence when its non-scaffold artifact is present.

| legacy artifact | path | present |
| --- | --- | --- |
| preregistration | results/preregistration/preregistration.json | missing |
| oracle_dataset | results/oracle_dataset/summary.json | missing |
| operator_cache | results/operator_cache/summary.json | missing |
| qwen_probe_cache | results/operator_cache/qwen_probe_cache_summary.json | missing |
| qwen_128_cache | results/operator_cache/qwen_128_cache_summary.json | missing |
| learned_wiring_qwen_128 | results/learned_wiring_qwen_128/results.json | missing |
| qwen_balanced_320_cache | results/operator_cache/qwen_balanced_320_cache_summary.json | missing |
| learned_wiring_qwen_balanced_320 | results/learned_wiring_qwen_balanced_320/results.json | missing |
| two_by_two | results/two_by_two/results.json | missing |
| d_stage_0 | results/d_stage_0/results.json | missing |
| d_stage_1 | results/d_stage_1/results.json | missing |
| d_stage_2 | results/d_stage_2/results.json | missing |
| d_stage_3 | results/d_stage_3/results.json | missing |
| verifier | results/verifier/results.json | missing |
| ttt_scaffold | results/ttt/results.json | missing |

## Standing Rules

- Fail-closed preflight.
- Autonomous solve only.
- No gate softening.
- Curriculum is training-only.
- Use TRM recipe only; never load a TRM checkpoint into controlled comparisons.
- kv_snapshot must be a true snapshot-and-truncate control.
- Per-task verdicts required.
- No ordering-only passes.
