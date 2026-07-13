# AppWorld 0.2 Generated Typed-Provenance Development v2

- Frozen date: 2026-07-12
- Status: frozen before calibration compatibility and v2 development outcomes
- Parent: v1 immutable protocol failure

v1 stopped before every environment construction: all 24 tasks produced the same `TypeError`, zero live calls, zero mutations, and zero guard outcomes. The error hash exactly binds to AppWorld 0.2 rejecting the removed AppWorld 0.1 argument `null_patch_unsafe_execution`.

The only v2 method change is a constructor adapter:

- require the frozen v1 request `null_patch_unsafe_execution=True`;
- remove that obsolete argument;
- pass AppWorld 0.2 `raise_on_unsafe_execution=True` explicitly;
- preserve every task, mutation, pair-selection, guard, gate, and output rule from v1.

Before opening development again, run the full tracing/replay path on the fixed lowest-ID calibration task `29caf6f_1`. Calibration readiness requires successful baseline execution/evaluation, at least one live call, at least one write checkpoint, and no harness exception. Guard accuracy or yield on this calibration task is not an acceptance criterion.

After calibration readiness, independently hash-lock the unchanged 24 development tasks (variations 4–6). The 24 confirmation tasks (variations 7–9) remain sealed. The original v1 `PROTOCOL_FAIL` is never overwritten or reinterpreted.
