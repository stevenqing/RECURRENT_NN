# EBW Track A Model Launch Preflight Handoff

## Status: **`RPD_EBW_TRACK_A_MODEL_LAUNCH_PREFLIGHT_BLOCKED`**

The Track A model-launch preflight was run after user authorization to use GPU 0/1 by pausing the DPO process. No model process was started.

## Result

- Freeze tag: `ebw-freeze-A`
- Tag commit: `eba53babec790a9d3b3839fd45f2ee4627228427`
- Model record: `Qwen/Qwen3-4B-Instruct-2507`
- Model snapshot exists: Yes
- Launch authorized: Yes
- Eligible GPUs by free-memory threshold: 0
- Blocking reason: `gpu_available`

## DPO Pause Probe

- Target PID: 3727989
- Expected start ticks: 223344517
- Identity matched: Yes
- Pre-pause state: `R`
- Stopped state: `T`
- Post-resume state: `R`
- GPU memory released by SIGSTOP: No

GPU 0 and 1 remained at roughly 78GB allocated each after SIGSTOP. Since Qwen3-4B-Instruct-2507 needs more free memory than the roughly 2.4GB available on either GPU, launching would likely fail with OOM. The DPO process was resumed immediately.

## Boundary

- No model run.
- No sealed variation 10-12 access.
- No DPO kill/restart.
- No push to remote.

## Next Options

1. Wait for GPU 0/1 to become genuinely free, then rerun this preflight.
2. Explicitly authorize stopping/restarting the DPO workload rather than pausing it.
3. Explicitly authorize a different free GPU set if available and compatible with other jobs.

Until one of those happens, Track A model execution remains blocked.