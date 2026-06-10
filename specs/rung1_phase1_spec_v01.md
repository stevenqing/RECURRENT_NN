# Rung-1 Phase 1 Spec v0.1

Status: accepted planning revision after Item053.

Item053 changed the Phase 1 framing. On the RG-native natural hard pool, solve-rate separation is weak at depth 7 and 8: chronological solves 0.958, CBJ solves 1.0, and McNemar p=0.25. The solve gap is significant only in the 9+ tail. The robust result across hard depths is the paired efficiency gap: CBJ reduces communication tokens and total retractions at every hard depth.

## Claim Order

Primary claim: conflict-directed backjumping on natural RG-hard distributed graph coloring reduces inter-agent communication and retractions by about half, paired per instance and reported by depth.

Primary metrics:

- `comm_tokens`
- `total_retractions`

Secondary claim: solve-rate gain is budget-contingent. It must be reported as a solve-vs-budget curve and not as a single headline solve-rate gap.

Pool roles:

- Headline pool: Item053 RG-native natural hard pool, extended with RG-native depth 4, 5, 6, and exact 9 lead-in bins before Phase 1.
- Stress isolation pool: Item052 chain-planted fixed-size pool. It can show adversarial structured solve-gap amplification, but it is not the headline distribution and must not be mixed with Item053.

Figure order:

1. Efficiency gap vs depth.
2. Solve rate vs node budget.

## Node-Cap Policy

Single-point solve at `node_cap=120` is retained only as a declared reference budget. The main solve analysis sweeps:

`node_cap in {60, 120, 240, 480, 960}`

For each arm and depth, record:

- solve rate
- node-cap exhaustion count
- `budget@95%_solve`: the smallest node cap with solve rate >= 0.95, or `not_reached` if none reaches 0.95

Interpretation: efficiency is the budget-free primary result; solve-vs-budget shows how lower recovery cost converts into solve success under finite budget. Expected shape: CBJ saturates early; chronological budget needed to reach 95% grows with depth and may fail to reach 95% at 9+ within the sweep.

## Qwen One-Shot Anchor

The `rg_greedy_one_shot` baseline is removed from headline reporting. It is circular on the reverse-greedy pool because those instances are retained only when greedy fails. It may be mentioned only as a pool-construction footnote.

Add a `qwen_one_shot` difficulty anchor on the same RG-native instances, using the original RG question format and RG `score_answer`/equivalent verifier.

Model and decoding:

- model: Qwen3.5-4B
- temperature: 0
- variants: direct-answer and with-CoT

Metrics:

- `oneshot_llm_solve_rate` by depth and variant
- invalid answer rate by depth and variant

This baseline is non-agentic and non-recovery. It anchors task hardness only and does not participate in efficiency metrics. If Qwen one-shot solves a large fraction of the pool, Phase 1 pauses and switches to a harder substrate before measuring agentic recovery.

## Natural Pool Lead-In

Before Phase 1, extend the RG-native reverse-greedy pool with natural depth bins 4, 5, 6, and exact 9. Do not borrow Item052 low or middle bins, because that would mix distributions.

Generation constraints:

- use `reasoning_gym.algorithmic.graph_color.generate_random_graph`
- use reverse-greedy filtering
- keep `n=16`, `k=4`, `n_agents=4`
- verify satisfiability and any reported coloring with the RG verifier
- preserve Item053 bins 7, 8, and 9+ as the natural headline pool tail

The middle exact-depth bins may require expensive rejection sampling, but the symbolic solver is fast enough for this to be an acceptable pre-Phase-1 cost.

## Operator Ladder

P1a, P1b, and P1c keep the operator ladder, prompts, nogood format, register, recovery rules, and symbolic loop boundaries frozen. Only the operator becomes fallible.

The first new Phase 1 quantity changes from solve crossover depth shift to efficiency-gap survival or erosion:

- Does CBJ still reduce `comm_tokens` and `total_retractions` under a fallible Qwen operator?
- Do false positives, false negatives, or spurious backjumps erase the symbolic efficiency advantage?

The remaining attribution quantities stay in scope:

- CBJ cost deviation from the symbolic integer line.
- False-positive/false-negative rate and spurious-backjump fraction.

Solve crossover is secondary and must be reported through the node-cap sweep.

## Run Order

1. Extend the RG-native natural pool with depth 4, 5, 6, and exact 9.
2. Run `qwen_one_shot` direct-answer and with-CoT. If one-shot solves a large fraction, stop and move to a harder substrate.
3. Run Phase 0 symbolic confirmation on the extended natural pool: efficiency-gap primary curve and solve-vs-budget secondary curve.
4. Enter Phase 1 in order: P1a, P1b, then P1c. Primary report is efficiency-gap survival under the fallible operator.

## Non-Goals

- Do not use Item052 chain-planted solve gaps as the headline figure.
- Do not mix chain-planted and RG-native rows in one curve.
- Do not headline reverse-greedy-filtered RG greedy one-shot solve rate.
- Do not report solve-rate separation without its node-cap budget context.