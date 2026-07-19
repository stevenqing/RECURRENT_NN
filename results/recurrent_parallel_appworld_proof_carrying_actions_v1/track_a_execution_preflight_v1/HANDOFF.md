# EBW Track A Execution Preflight Handoff

## Status: **`RPD_EBW_TRACK_A_EXECUTION_PREFLIGHT_READY`**

This step locks the opened-pool Track A execution set after the local `ebw-freeze-A` tag. It does not run a model and does not open sealed variations 10-12.

## Completed

- Verified local freeze tag `ebw-freeze-A` points to commit `eba53babec790a9d3b3839fd45f2ee4627228427`.
- Verified current HEAD is the freeze tag commit.
- Verified Track A prompt hash.
- Verified runner budget caps and GA-dev/GA-main asserts.
- Verified parser/test files exist.
- Excluded all 40 frozen dev-slice instances.
- Generated reportable opened-pool evaluation manifest with 1226 instances.
- Wrote execution lock for future Track A model outcomes.

## Evaluation Set

| Proof family | Reportable instances |
|---|---:|
| `filesystem_path_derivation_proof` | 537 |
| `literal_text_derivation_proof` | 114 |
| `state_transition_membership_proof` | 575 |

## Key Artifacts

- Contract: `specs/recurrent_parallel_ebw_track_a_execution_preflight_v1.json`
- Spec: `specs/recurrent_parallel_ebw_track_a_execution_preflight_v1.md`
- Builder: `analysis/ebw_track_a_execution_preflight.py`
- Report: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1/PREFLIGHT.md`
- Preflight JSON: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1/preflight.json`
- Execution lock: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1/execution_lock.json`
- Evaluation manifest: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_execution_preflight_v1/evaluation_manifest.json`

## Boundary

- No model run.
- No GPU/Docker/external process action.
- No sealed variation access.

## Next Step

Run a parser/runner smoke with synthetic outputs before scheduling the Qwen Track A opened-pool model run.