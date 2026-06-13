# Externalization Paper Full Execution v1

This document supersedes `specs/externalization_paper_validation_v0.md` and the Item077/Item078 execution-order addenda. It is the runnable contract for the externalization paper validation line.

No internalization is in scope: no training, distillation, RL, or learned parameter updates. Qwen3.5 is a frozen decision oracle served through vLLM. The paper studies LLM reasoning under external structure, not beating CSP solvers.

## Confirmed State

- Reasoning Gym official `score_answer` is usable for `graph_color`, `zebra_puzzles`, and `sudoku` from Item077.
- vLLM Qwen3.5 is available on `http://127.0.0.1:8001/v1` with model `Qwen/Qwen3.5-4B`; use `gpu_memory_utilization=0.30`, `max_model_len=4096`, and port `8001`.
- AgentsNet formula path is GO through the direct `Coloring.get_score` formula, not the langchain runtime.
- Item078 two-rail gates:
  - `graph_color`: `n_vertices=14`, `edge_probability=0.4`, primary `node_budget=20`; L0-random `0.0`, L0-heuristic `1.0`.
  - `sudoku`: `empty=45`, primary `node_budget=320`; L0-random `0.0`, L0-heuristic `1.0`.
  - `zebra_puzzles`: official scoring is available but structural adapter is pending.
- Calibration used `n=4`; all real LLM shards must use `n>=30`.

## M-Register Contract

The symbolic layer owns the CSP instance, forward checking, conflict detection, and a reversible register of size `R`. The LLM sees only a bounded view: current frontier variable, remaining domain, assigned neighbors/constraints touching that frontier, and the last `R` register entries. Prompt size must remain flat in depth.

The LLM makes two decisions only: branch value and, on dead end, backtrack target. Parse failures are counted and fall back to first legal value for branch or chronological target for backtrack. `R=0` is forward-only and terminates on dead end.

Final scoring is official scoring only. Node budget bounds `nodes_visited`; call cap must exceed expected search length. Censoring statuses are `SOLVED`, `NODE_CAP`, `NO_RECOVERY_TARGET`, and `FORWARD_DEAD_END`.

## Arms

- `L0-symbolic-heuristic`: complete no-LLM MRV/degree chronological search, matched node budget. This is a ceiling reference.
- `L0-symbolic-random`: same engine with random branch value and random bounded culprit target.
- `M-register`: R sweep over `{0,2,4,8,16}` with frozen Qwen3.5 decisions.
- `L1-oneshot-vanilla`: one plain CoT forward pass, official score.
- `L1-oneshot-thinking`: one thinking-mode attempt, official score. This is the strong claim-1 baseline.
- `L1-bestofN`: thinking mode with `N in {5,10}`, report oracle-best and majority vote.
- `L1-selfverify`: generate, self-check, revise up to three rounds.
- `L2-tot`: in-context Tree of Thoughts, equal LLM-call budget, unbounded prompt-memory contrast.
- `L3-llm2solver`: LLM translates to solver code, external solver solves. This is a ceiling/context arm.
- Optional `L3-llm-modulo`: whole-candidate generate/verify/critique loop.

## Bins And Budgets

- R sweep: `{0,2,4,8,16}`.
- Budget sweep: `{20,40,80,160,320}`. Verdict is curve shape, never a single value.
- Ceiling bins are confirmed for `graph_color` and `sudoku` above.
- Middle-band calibration remains a Phase 0b task: find bins with L0-heuristic roughly `0.3..0.9` and L0-random below `0.3`, using `n>=20`.
- Target-source ablation runs at `R in {2,4}` with target source `{llm, oracle, random}`.

## Multi-Agent Contract

Substrate A uses controlled partitions of `graph_color` and `zebra_puzzles`; Substrate B uses AgentsNet graph instances and direct `Coloring.get_score`. No langchain runtime is used. No-LLM mode replicates the Item076 symbolic route. Real-LLM claim 4b is required: per-block frozen-LLM agents for the team and one frozen-LLM monolith, swept by global-trail length relative to a single register rather than conditioning on Item076's symbolic monolith-fail intersection.

## Kill Forks

- `K1`: If L1-thinking solves above `0.3` on hard bins, scope claim 1 to vanilla one-shot.
- `K2`: Claim 2 requires monotonic/saturating R curve on at least two Tier-1 benchmarks.
- `K3a`: M-register must beat L0-random on the ceiling bin.
- `K3b`: M-register must be competitive with L0-heuristic on the middle-band bin; if clearly below, bank the negative.
- `K4`: If ToT/best-of/selfverify match M-register, narrow contribution to bounded-memory efficiency.
- `K5`: CBJ structure dependence is confirmed only on separator/sparse topologies; dense graph_color scoping is already banked.
- `K6`: Real-LLM team-over-monolith capacity gap must open past single-register capacity, or the real-LLM claim 4b is scoped.

## Current Phase Gates

- Phase 0a preflight: complete.
- Phase 0b no-LLM power gates: graph_color and sudoku ceiling bins GO; zebra adapter blocked; middle-band calibration pending.
- Phase 1 graph_color ceiling LLM shard: GO, because vLLM smoke passes and Item078 two-rail gate passes. Must use `n>=30`.
- Phase 1 sudoku ceiling LLM shard: GO after graph_color, also `n>=30`.
- Zebra LLM shard: NO-GO until structural adapter exists.
- Secondary baselines and multi-agent real-LLM phases are downstream of Phase 1 shard readouts and their own anchors.