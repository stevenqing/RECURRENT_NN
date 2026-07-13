# AppWorld 0.2 Fresh Multi-App Task Generation v1

- Frozen date: 2026-07-12
- Status: frozen before generated task and guard outcomes
- Source commit: `a072b7a86e7c1d5b1d7175659d750ebb9b79f10a`
- Data version: 0.2.0
- Root: isolated generated root; released 0.1 data remain unchanged

Generate nine tasks for each of the ten multi-app scenario generators:

`22cc237,29caf6f,2a163ab,3c13f5a,60d0b5b,6104387,6ea6792,afc0fce,b0a8eae,d0b1f43`

Use `PYTHONHASHSEED=0`, random seed 100, environment execution, and compiled validation solutions.

## Frozen split

- variations 1–3: generation/calibration only;
- variations 4–6: typed-provenance development;
- variations 7–9: frozen confirmation.

No variation may move between splits based on mutation yield or guard performance. All generated validation solutions and evaluators must pass before a task is eligible. Confirmation prompts/results remain hidden until the typed method is frozen on variations 4–6.

## Generation integrity

- build data 0.2 with the safe wrapper that omits upstream process-killing code;
- no system package, Docker, GPU, or external-process action;
- hash source commit, base DB, task directories, split IDs, generator code, and generation logs;
- do not export protected task content.

A generation pass authorizes new typed-provenance development; it is not a model or multi-agent result.
