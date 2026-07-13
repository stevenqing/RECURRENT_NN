# AppWorld A5 — Deterministic Provenance Confirmation v2

- Frozen date: 2026-07-12
- Status: frozen before any provenance guard outcome
- Supersedes v1 replay plumbing only

v1 was pre-locked but failed on the first dev baseline before any mutation or guard outcome because a historical raw JWT was replayed directly. v2 preserves task selection, mutation generation, strict labels, provenance extraction, candidate ordering, abstention rule, and all V0–V5 gates.

The sole repair is runtime-token rebinding:

1. when the current replay executes a login and receives an access token, store it by app;
2. replace `access_token` in later calls with that current token;
3. save the token map alongside each mutation checkpoint and restore it for every branch.

All other semantics and gates are identical to v1:

- at least 10 strict pairs over at least five dev types;
- coverage at least 0.50;
- zero incorrect covered choices;
- covered accuracy at least 0.80;
- one-sided exact binomial $p<0.05$ against 0.50;
- dev only, no test/model/GPU/Docker or protected exports.

A pass supports a selective deterministic provenance guard, not end-to-end task-completion improvement.
