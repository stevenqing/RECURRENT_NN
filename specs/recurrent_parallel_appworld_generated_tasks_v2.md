# AppWorld 0.2 Fresh Multi-App Task Generation v2

- Frozen date: 2026-07-12
- Status: frozen before complete generated-task outcomes
- Supersedes: v1 process-PATH plumbing only

v1 prelocked generation failed while saving the first task of every generator because `ruff`, although installed in the source uv environment, was not on the child PATH. No validation outcome was produced.

v2 preserves the exact source commit, data-0.2 base DB, ten generator IDs, nine tasks per generator, random/hash seeds, compiled environment validation, and variation split. It only prepends the source uv `bin` directory to PATH and removes partial task directories in the isolated generated root before execution.

Frozen split remains:

- variations 1–3 calibration;
- variations 4–6 development;
- variations 7–9 confirmation.

No task may move based on generation yield or later guard outcomes.
