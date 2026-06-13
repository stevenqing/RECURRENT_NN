# Multi-Agent Real-LLM, Program Reweight, and Internalization Program v1

## Program Reweight

The non-LLM scaffolding is frozen. Existing L0 symbolic baselines, calibration, ceiling, middle-band, power gates, and token logging are reference controls. Do not expand L0 or generate new no-LLM calibration results. New compute is routed to LLM axes in this order:

1. Multi-agent real-LLM capacity sweep.
2. K1 thinking closeout with anti-truncation guard.
3. Larger-model single-agent graph_color reruns.
4. Solve-vs-total-token scaling curves.

LLM results are the narrative spine. MRV, Z3, and L0 arms are controls or appendix context, not co-headliners. Externalization is the frozen-LLM precursor to internalization; failures are acceptable scope results.

## Part 1: Multi-Agent Real-LLM

Execute first. The headline is claim 4b: a bounded team of frozen LLM agents may solve capacity-stressed instances that a single bounded-register LLM monolith cannot. Claim 3 remains secondary and structure-dependent.

Substrate A is a controlled partition of Reasoning Gym `graph_color`. Vertices are partitioned into `K` blocks, one agent per block, with per-agent register `R`. The symbolic controller owns propagation, conflict detection, cross-block routing, and official `dataset.score_answer` validation.

Substrate B is AgentsNet graph coloring using direct `Coloring.get_score` formula, not langchain runtime. It is a second venue after Substrate A.

Team contract: each per-block agent sees the block frontier, local constraints, boundary assignments, and a bounded register of size `R`. It makes branch and local backtrack decisions. The symbolic controller handles cross-block conflicts and undo.

Monolith controls:

- `monolith-R`: one frozen LLM with register size `R` over the full instance.
- `monolith-KR`: one frozen LLM with register size `K*R`, matching total team register capacity.

Token accounting is total input plus output tokens across all agents and calls. Record `cache_effective` when available; otherwise record that vLLM OpenAI usage does not expose it.

Claim 4b sweep: fix per-agent `R=8`, choose block size so each block local trail fits in `R`, sweep `K in {2,3,4,6}`, and use at least 30 instances per `K`. Do not use the Item076 monolith-fail/team-feasible intersection for selection.

K6 read:

- Capacity positive if team solve stays high while `monolith-R` drops as `K` grows.
- Decomposition beyond raw capacity if team matches or beats `monolith-KR`.
- If team matches `monolith-KR` within noise, report cooperation-through-partition capacity.
- If team is below `monolith-KR`, report capacity partition without locality advantage.
- If `monolith-R` does not drop, raise `K` or block size before reading the claim.

Claim 3 separator sweep is secondary. Reproduce known CBJ/chrono anchors before trusting comparisons. Tripwire: `cbj_work > chrono_work` on the anchor is a bug.

## Queued LLM Axes

K1 thinking, larger-model single-agent reruns, and token curves remain queued after or alongside Part 1 as GPU allows.

## Guards

Use official scoring only. Thinking reads require finish_reason stop. Token accounting is total tokens, never completion only. Use vLLM with conservative memory and parseable smoke gates. LLM claim shards require `n>=30`. Reproduce anchors before trusting comparisons. Bank two-way results without goalpost movement.

## Internalization Destination

Part 4 is the long-horizon LoRA internalization program. Externalized bounded-CBJ traces from Part 1 become gold traces. Internalization means the external register and controller are removed: LoRA agents must emit cooperative bounded backtracking search in token-space while maintaining a bounded textual working register. Stage I is single-agent register-free LoRA internalization. Stage II is multi-agent internalization with homo versus hetero LoRA controls. No internalization run counts while the external scaffold remains present.