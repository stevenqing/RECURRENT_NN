# Internalization TTT-LoRA Training Design v1

## Purpose

This design revises the internalization route after Items097-098 trace export. The next training work should not be plain SFT-LoRA only. It should include a test-time-training style adapter path, while preserving the definition of internalization: the external controller/register must eventually be removed.

## Core Decision

Use three distinct state carriers instead of overloading one mechanism:

1. Static LoRA (`theta_static`): offline learned policy prior from trace examples.
2. Episode/agent fast LoRA (`delta_theta_ep`): resettable test-time adaptation state.
3. Textual bounded register: the only reversible search stack in internalized evaluation.

The fast LoRA is not the stack. Prior TTT diagnostics show gradient fast weights are not cleanly reversible, so using LoRA updates as the sole push/pop memory would undermine the central claim. Fast LoRA may adapt the policy to the current graph/agent/episode; rollback semantics must be represented in bounded text and checked by transcript consistency.

## LoRA Forms

| form | train/update time | reset scope | role | internalization status |
| --- | --- | --- | --- | --- |
| `static_policy_lora` | offline SFT | persistent checkpoint | learn branch/backtrack/message/final action format and priors | not internalized while external scaffold owns state |
| `fast_ttt_lora` | test time | reset per episode or per agent episode | adapt to current graph topology, block-local vocabulary, boundary pattern, and register serialization | internal state only if update loss uses visible data only |
| `homo_fast_lora` | test time | one shared fast adapter per team episode | shared-agent adaptation control | multi-agent pilot control |
| `hetero_fast_lora` | test time | one fast adapter per agent | per-agent local adaptation and role specialization | main multi-agent candidate |
| `monolith_fast_lora_R` | test time | one monolith adapter with register budget R | monolith control | required control |
| `monolith_fast_lora_KR` | test time | one monolith adapter with register budget K*R | capacity-matched monolith control | required control |

## Allowed Test-Time Losses

At evaluation time, fast LoRA updates may use only labels derived from learner-visible input or the model's own bounded transcript. They may not use oracle `target_action`, official score, hidden full assignment, or external scaffold state not visible to the agent.

Allowed losses:

- `masked_visible_state_reconstruction`: mask parts of `visible_state` such as register entries, boundary assignment values, local assignment entries, or conflict edge fields; reconstruct them.
- `local_constraint_consistency`: classify or generate whether two visible assigned neighboring vertices conflict; labels are computed from visible edges/assignments only.
- `register_serialization_consistency`: reconstruct canonical textual register order from visible bounded register entries.
- `rollback_text_consistency`: given a visible rollback transcript row, reconstruct the declared post-rollback textual register/assignment summary.
- `message_roundtrip_consistency`: reconstruct message recipient/content from visible cross-block conflict row.

Disallowed test-time losses:

- Oracle branch/backtrack labels.
- Official `score_answer` or final solution correctness.
- Full hidden CSP assignment outside the visible state.
- External scaffold rollback target if not rendered in the visible state.

During offline training, supervised `target_action` cross-entropy is allowed for `theta_static`. Meta-training may simulate fast-LoRA adaptation, but reported internalized evaluation must use only the allowed test-time losses above.

## Training Curriculum

### Stage A: Trace-to-SFT Dataset

Convert Items097-098 traces into train/validation/test splits by episode, never by row. Splitting by row leaks the same graph/register trajectory into validation.

Outputs:

- `sft_action_train.jsonl`
- `sft_action_val.jsonl`
- `ttt_aux_train.jsonl`
- `ttt_aux_val.jsonl`
- dataset card with source hashes and split hashes

Gate: all rows parse; no episode appears in more than one split; all action kinds have validation coverage or are explicitly marked rare.

### Stage B: Static Policy LoRA

Train a small LoRA on action prediction only. This is a policy prior, not internalization.

Initial config:

- base: `Qwen/Qwen3.5-4B`
- target modules: attention q/k/v/o and MLP up/down/gate projections if memory permits; otherwise q/v/o only for smoke
- rank: 8 or 16
- alpha: 16 or 32
- dropout: 0.05
- precision: bf16 if available
- max sequence length: keep below trace prompt max plus answer, initially 2048

Gate: validation exact-action accuracy and parseability exceed frozen baseline; external-scaffold solve does not regress.

### Stage C: Auxiliary TTT Pretraining

Train the model to support fast LoRA adaptation by mixing action SFT with visible-state reconstruction tasks. The objective is not to solve at test time directly, but to make few-step adaptation useful.

Training objective:

`L = L_action + lambda_aux * L_visible_reconstruct + lambda_consistency * L_transition_consistency`

Gate: after k inner-loop fast-LoRA updates on validation auxiliary tasks, action accuracy improves over no-update static LoRA.

### Stage D: External-Scaffold TTT-LoRA Eval

Keep the external scaffold for evaluation only, but replace the frozen decision model with static+fast LoRA. This tests policy quality while the scaffold still owns register/state.

Controls:

- frozen Qwen no LoRA
- static LoRA no TTT
- fast TTT LoRA with shuffled aux targets
- fast TTT LoRA with no rollback rows
- oracle-scaffold teacher ceiling

Gate: parseable/valid/action accuracy improves and solve rate under scaffold beats frozen/static controls.

Does not establish internalization.

### Stage E: Register-in-Text Internalization

Remove external register ownership. The model must emit a bounded textual register, assignment summary, action, and after-state. Evaluator parses transcript, checks local consistency, and calls official scoring only at final.

Allowed fast-LoRA update uses visible transcript reconstruction/consistency only.

Gate: closed-loop solve beats one-shot/two-stage baselines; transcript register length remains bounded; rollback consistency passes.

### Stage F: Multi-Agent Internalization

Run the same static+fast LoRA program for team agents and monolith controls.

Controls:

- homo static+fast LoRA team
- hetero fast LoRA team with shared static LoRA
- monolith-R static+fast LoRA
- monolith-KR static+fast LoRA
- static-only versions of all above

Gate: no capacity claim unless n>=30 per K; report pilot separately.

## Item Renumbering After This Design

The Item096 plan is updated by inserting this design as Item099 before the dataset builder:

| item | revised stage |
| --- | --- |
| 099 | TTT-LoRA training design and gates |
| 100 | Trace-to-SFT and TTT auxiliary dataset builder |
| 101 | Static policy LoRA smoke under external scaffold |
| 102 | TTT auxiliary inner-loop smoke under external scaffold |
| 103 | Register-in-text eval harness |
| 104 | Single-agent register-internalized TTT-LoRA pilot |
| 105 | Multi-agent internalized TTT-LoRA pilot |
| 106 | Scale or fail-close |

## Non-Negotiable Controls

- Episode-level splits only.
- No official score in test-time updates.
- No oracle action labels in test-time updates.
- Fast adapters reset per episode or per agent episode.
- Textual register is the reversible stack; LoRA fast weights are adaptive policy state, not stack storage.
- Static-only and no-update ablations must be reported.
- Shuffled auxiliary-target ablation must fail to improve, or the TTT mechanism is suspect.
- External-scaffold eval and register-in-text eval must be labeled separately.

## Next Step

Implement Item100: a dataset builder that emits both action SFT examples and auxiliary TTT examples from Items097-098, with episode-level split hashes and leakage checks.