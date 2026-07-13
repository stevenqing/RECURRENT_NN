# AppWorld 0.2 Generated Typed-Provenance Development v3

- Frozen date: 2026-07-12
- Status: frozen before v3 calibration and development outcomes
- Parent chain: v1 protocol failure → v2 calibration failure

v2 fixed the removed constructor argument and reached the calibration task path, but AppWorld 0.2 left its global `SafetyGuard` patch active. The first post-task immutable-file hash therefore raised a bound `PermissionError` on `pathlib.Path.read_bytes`; calibration acceptance was not computed, and no development or confirmation outcome was opened.

v3 preserves the v2 constructor adapter and adds exactly one lifecycle action: for every locally created world, call its own `safety_guard.disable()` immediately before inherited `AppWorld.close_all()`. This restores functions captured by that world; it does not stop, signal, reconfigure, or inspect any external process.

All tasks, mutation generation, replay, pair selection, candidate order, typed guard, gates, and output restrictions remain unchanged. Validate the full path on the next fixed calibration task `29caf6f_2`. Calibration readiness depends only on baseline success, nonzero live calls and write checkpoints, no harness exception, and successful post-task immutable hash checks. Guard performance is not a calibration acceptance criterion.

Only after calibration readiness may v3 independently hash-lock and execute the same 24 development tasks (variations 4–6). The 24 confirmation tasks (variations 7–9) remain sealed.
