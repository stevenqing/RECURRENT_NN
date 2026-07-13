# AppWorld Multi-App Census v2 — Verifier Parser Repair

- Frozen date: 2026-07-12
- Status: frozen before model outcomes
- Supersedes v1 verifier-log parsing only

The v1 candidate census was correct (51 episodes, 17 task types, all census and leakage gates passed), but its captured-log parser required terminal-only prose: `138 passed` and `Passed 147/147 tasks.`. In non-TTY subprocess capture, AppWorld emitted complete progress and returned code zero but omitted those final prose strings. Consequently v1 returned `RPD_APPWORLD_A1_PREFLIGHT_FAIL` despite successful official verification.

v2 preserves the v1 artifact and every candidate/adjudication row exactly. It changes only the v2 wrapper schema/status, reruns verification, and defines success as:

- app tests: process return code zero and `1553 passed`;
- package tests: process return code zero, `collected 138 items`, final package test at `[100%]`, and no failure/error summary;
- train/dev task validation: process return code zero and terminal progress reaches `147/147`.

No selection threshold, task metadata, protected-content rule, split policy, or model outcome changes.
