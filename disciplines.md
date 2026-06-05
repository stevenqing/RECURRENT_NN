# Stage D Discipline Checklist

- Backbone frozen; train only register, controller, and verifier heads.
- LoRA on the operator is a recorded deviation, never the default.
- Prompt is a bounded current-node rendering; never append-only.
- Search stack lives only in the structured register `h`.
- Revert uses the register in-loop, causally, not as a post-hoc probe.
- Supervision comes from symbolic oracle traces, never a stronger LLM CoT.
- No-revert ablation is mandatory and must collapse to latent-only floor.
- GRU-register is the labeled negative baseline.
- Verifier is answer-free and must be ablated: oracle, learned, noisy, disabled.
- Win band is pre-registered before D-stage 3.
- Comparisons use matched compute and report mean +/- std over seeds.
- Agentic tier is demo-only, single-agent, and search-before-act over reversible models.
- Sudoku-Bench is an external anchor only, never the controlled depth benchmark.
- Browser/GUI agents with irreversible side effects are out of scope for Stage D.
- Current scaffold metrics must be labeled `oracle_trace_scaffold` until trained model loops replace them.
