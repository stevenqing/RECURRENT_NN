# AppWorld 0.2 Generated Typed-Provenance Development v6

- Frozen date: 2026-07-12
- Status: frozen before v6 calibration and development outcomes

v5 established a safely serialized calibration failure. Its redacted error hash exactly equals `'NullWriter' object has no attribute 'fileno'`: AppWorld 0.2 invokes `faulthandler.enable()` while protected runtime output is redirected to the non-retaining sink.

v6 adds only `NullWriter.fileno()`, returning the pre-existing `sys.__stderr__` descriptor. The sink still discards every write and exports no protected runtime text. Constructor mapping, caller-level pristine restoration, tasks, mutation/replay logic, pair ordering, guards, gates, and output scope remain unchanged.

Use the next deterministic unused calibration task `2a163ab_2`. Calibration readiness requires baseline pass, nonzero live calls and write checkpoints, no harness exception, and successful post-task immutable hashes. Guard yield/performance is not used for acceptance.

Only READY authorizes a fresh v6 lock on the same 24 development tasks. The confirmation split remains sealed.
