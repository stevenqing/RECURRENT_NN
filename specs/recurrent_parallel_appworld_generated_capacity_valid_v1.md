# AppWorld Generated Tasks — Capacity-Valid Split v1

- Frozen date: 2026-07-12
- Status: frozen before generated-task guard outcomes
- Parent: v2 generation result with 84/90 tasks and eight fully complete generators

The original 90-task cardinality gate remains failed. Before any mutation or guard outcome, derive a capacity-valid pool using the preregistered `minimum_valid_generators=8` boundary:

- include a generator if and only if all variations 1–9 exist and validated;
- exclude incomplete generators entirely;
- do not replace, regenerate, or move tasks between splits;
- retain variation split 1–3 calibration, 4–6 development, 7–9 confirmation.

Expected capacity-valid pool:

- 8 complete generator types;
- 72 tasks total;
- 24 calibration tasks;
- 24 development tasks;
- 24 confirmation tasks.

Partial generators `22cc237` and `d0b1f43` remain recorded as capacity holes and are not used. This split authorizes generated-task method development, not a model or end-to-end claim.
