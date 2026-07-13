# AppWorld 0.2 Generated Typed-Provenance Development v4

- Frozen date: 2026-07-12
- Status: frozen before v4 calibration and development outcomes
- Parent chain: v1 protocol failure → v2/v3 calibration lifecycle failures

v3 confirmed that restoring the world-local `SafetyGuard` is insufficient after AppWorld 0.2 checkpoint loading invokes base-class global cleanup. The same process-global `pathlib.Path.read_bytes` patch remained active at the post-task hash check.

v4 adds one deterministic compatibility action: instantiate a pristine `SafetyGuard` before any world exists and invoke its `disable()` in a `finally` block after inherited local cleanup. This restores only Python functions captured before the run. It performs no external-process action.

The constructor adapter, local cleanup, tasks, mutation generation, replay, pair selection, guard logic, gates, and output scope are unchanged. Validate the full path on the next fixed calibration task `29caf6f_3`. Calibration acceptance ignores guard yield/performance and requires baseline success, nonzero calls/checkpoints, no harness exception, and successful post-task immutable hashes.

Only a calibration READY result permits a new pre-outcome lock of the same 24 development tasks. Confirmation variations 7–9 remain sealed.
