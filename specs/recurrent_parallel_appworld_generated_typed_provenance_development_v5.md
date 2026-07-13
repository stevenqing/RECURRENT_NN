# AppWorld 0.2 Generated Typed-Provenance Development v5

- Frozen date: 2026-07-12
- Status: frozen before v5 calibration and development outcomes

An isolated unit test proved that a pristine `SafetyGuard.disable()` restores the global function table. v4 still reached the post-task hash with `pathlib` patched, so adapter `close_all()` dispatch is not a sufficient restoration boundary, especially when construction or internal cleanup fails.

v5 wraps the unchanged frozen `process_task` call in an unconditional caller-level `try/finally` and invokes the pristine restore primitive in that `finally`. This executes before shard serialization or immutable-file checks regardless of world construction, replay, or close outcome. Constructor and adapter fixes remain; no task, mutation, selection, guard, gate, or output rule changes.

Use the next deterministic unused calibration task `2a163ab_1`. Calibration readiness requires baseline pass, nonzero live calls and write checkpoints, no harness exception, and successful post-task immutable hashes. Guard performance is not used for calibration acceptance.

Only READY authorizes an independently locked v5 run on the same 24 development tasks. All 24 confirmation tasks remain sealed.
