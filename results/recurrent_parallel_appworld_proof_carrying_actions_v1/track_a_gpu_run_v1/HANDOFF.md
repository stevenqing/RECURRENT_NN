# EBW Track A GPU Smoke Handoff

## Status: **`QWEN_SMOKE_COMPLETE_DPO_RESTARTED`**

This step used the user-authorized GPU0/1 takeover by stopping the synthetic DPO workload, ran a small EBW Track A Qwen smoke, and restarted an equivalent DPO workload afterward.

## DPO Handling

- Original PID: `3727989`
- Original command: `/opt/conda/envs/ptca/bin/python -u /home/aiscuser/yifeisun/project_1128/DPO_train.py --gpu 0,1`
- Original workload type: synthetic random ResNet GPU load, no checkpoint/resume state.
- Stop action: SIGTERM, then SIGKILL because the process remained present during the wait.
- GPU0/1 memory released after stop: Yes.
- Restarted equivalent workload: Yes.
- New Python PID: `167916`
- New command: `/opt/conda/envs/ptca/bin/python -u /home/aiscuser/yifeisun/project_1128/DPO_train.py --gpu 0,1`
- New log: `/home/aiscuser/yifeisun/project_1128/logs/DPO_train_gpu01_restarted_after_ebw_20260714_040352.log`
- Equivalent state note: this is an equivalent synthetic GPU load restart, not a bitwise training-state resume.

## Qwen Smoke

- Model: `Qwen/Qwen3-4B-Instruct-2507`
- Smoke instances: 4
- GPU: physical GPU0 exposed as `cuda:0`
- Result: `RPD_EBW_TRACK_A_MODEL_RUN_COMPLETE`
- Decision counts: `{'abstain_no_valid': 4}`
- Parse rate: 0.000
- Safe commit recovery: 0.000
- GA-main pass: False
- Sealed variations 10-12 opened: No

## Interpretation

The two-stage runner works far enough to build prompt contexts, load the frozen Qwen model, generate outputs, and write results. However, the first prompt design is not viable under the strict parser: Qwen emitted fenced JSON plus explanation/repeated text, so all four smoke cases failed parsing and abstained.

This means a full 1226-instance Track A run should not be launched with the current prompt shape. The next fix should be prompt/parser-protocol work on the frozen dev slice only, not opened-pool outcome tuning.

## Artifacts

- DPO stop audit: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_gpu_run_v1/dpo_stop_audit.json`
- DPO restart audit: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_gpu_run_v1/dpo_restart_audit.json`
- Prompt-manifest smoke: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_smoke_v1/PROMPT_MANIFEST.md`
- Qwen smoke report: `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_smoke_v1/REPORT.md`

## Next Route

Revise the Track A prompt protocol on the frozen dev slice so that the model emits one bare JSON object without Markdown fences or prose. Do not run the opened-pool full Track A model job until a new dev-slice parser smoke reaches the GA-dev parse gate.
