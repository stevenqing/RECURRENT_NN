# EBW Track A Model Launch Preflight v2

## Status

`FROZEN_AFTER_EXECUTION_PREFLIGHT_BEFORE_MODEL_LAUNCH`

## Repair Scope

v2 corrects the model download record to `Qwen/Qwen3-4B-Instruct-2507` and records user authorization to use GPU 0/1 by pausing the DPO process if memory is actually available. The preflight itself starts no model.

## Current Blocker

The authorized same-PID DPO pause probe showed that `SIGSTOP` pauses compute but does not release GPU memory. GPU 0/1 remain occupied by PID 3727989 with roughly 78GB allocated per GPU, leaving less than the required free memory for Qwen Track A.

## Boundary

- No model process is started by this preflight.
- No sealed variation access.
- No DPO kill/restart authorization is implied.