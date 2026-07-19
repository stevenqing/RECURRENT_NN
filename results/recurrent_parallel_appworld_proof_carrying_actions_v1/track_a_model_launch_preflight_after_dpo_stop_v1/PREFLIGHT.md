# EBW Track A Model Launch Preflight

## Status: **`RPD_EBW_TRACK_A_MODEL_LAUNCH_PREFLIGHT_READY`**

- Freeze tag: `ebw-freeze-A`
- Tag commit: `eba53babec790a9d3b3839fd45f2ee4627228427`
- Model record id: `Qwen/Qwen3-4B-Instruct-2507`
- Eligible GPUs: 2
- Launch authorized: True
- Sealed variations 10-12 opened: No
- Model process started: No

## Blocking Reasons

- none

## Checks

- `contract_frozen`: **PASS**
- `tag_commit`: **PASS**
- `head_at_tag`: **PASS**
- `execution_preflight_ready`: **PASS**
- `execution_lock_binding`: **PASS**
- `runner_smoke_pass`: **PASS**
- `model_id`: **PASS**
- `model_snapshot_exists`: **PASS**
- `gpu_available`: **PASS**
- `run_output_absent`: **PASS**
- `sealed_closed`: **PASS**
- `launch_authorized`: **PASS**
- `no_external_actions`: **PASS**
