# Proof-Carrying Actions: Research Contribution v1

## One-Line Idea

Parallel tool-using agents should not commit writes because they are confident, because they vote, or because a value appears in context. They should commit only when exactly one candidate action carries a deterministic proof that binds immutable evidence to the proposed write arguments.

## Why This Is Not Just Engineering

The engineering objects in this repository are verifiers, DSLs, traces, and AppWorld adapters. The research object is the **commit protocol**:

1. agents propose actions and proof sketches in parallel;
2. all proofs are checked against the same immutable pre-write snapshot;
3. the barrier commits only under unique proof validity;
4. ambiguous or missing proofs become recurrent state;
5. extra compute is spent only on proof failures, not on every action.

The verifier code is measurement apparatus. The idea is that write safety in stateful agent systems depends on proof obligations, not persuasion signals.

## Failure Modes That Forced The Idea

| Attempt | Result | Lesson |
|---|---:|---|
| Qwen binary correction judge | pooled balanced accuracy 0.566; calibration failed | LLM confidence is not a reliable recurrent control signal. |
| Typed max-tier provenance | 45 correct / 3 wrong | Evidence strength can still commit wrong writes. |
| Exclusive scalar provenance | 45 correct / 0 wrong | Abstaining on competing evidence is safer than ranking it. |
| Active-read / full-record ceilings | 0/26 resolved | More reads do not help if evidence algebra cannot bind values to actions. |
| API-aware proof-family mapper | 45/45 | Naming the proof family is too easy; it is not a research target. |
| Occurrence verifier | 386 unsafe unique-wrong | Value occurrence is not proof. |

These failures are the contribution's spine: they rule out confidence, voting, scalar provenance, more reads, and proof-family classification.

## Positive Evidence So Far

The broad opened AppWorld pool gives 1266 value-bound witness instances over 31 write APIs and 45 argument-field schemas. The current deterministic safe lower bound is safe derivation ledger v5:

| Decision | Count |
|---|---:|
| `commit_live` | 334 |
| `ambiguous_both_valid` | 231 |
| `abstain_no_valid` | 701 |
| `unsafe_unique_wrong` | 0 |

Safe commits come from proof obligations with role-specific semantics:

| Obligation Pattern | Example | Safe Commit Signal |
|---|---|---:|
| `derived_path_binding` | destination path derived from source path basename | 75 path commits |
| `literal_intent_binding` | quoted user text becomes message/title/comment | 46 text commits |
| `prior_effect_binding` | playlist ID created by `create_playlist` is consumed later | 18 state commits |
| `ordered_role_binding` | queue order vs search-result order for `like_song` | 149 state commits |
| filtered zero-unsafe ordered slices | schema slices from a failed broad ordered verifier | safe ledger contribution |

The important part is not that these are AppWorld APIs. The important part is that each safe verifier names an **evidence role**. The same scalar can be unsafe unless the verifier knows why that scalar is the write argument.

## Formal Commit Rule

For snapshot `S`, candidate action `a`, and proof sketch `pi`:

```text
V(S, a, pi) = deterministic verifier result in {valid, invalid}
```

For candidate actions `A` and `B`:

```text
commit(A, B) =
  A      if V(A)=valid and V(B)=invalid
  B      if V(A)=invalid and V(B)=valid
  recur  otherwise
```

The recurrent state is not uncertainty. It is a typed proof failure: missing proof, invalid proof, competing valid proofs, missing read, missing prior effect, or role mismatch.

## Where Multi-Agent Matters

The multi-agent component is not majority vote. It is parallel proof search:

| Agent Role | Proposal Type |
|---|---|
| Literal agent | proof that a write comes from explicit user text |
| Path agent | proof that a path is derived from file structure/source path |
| Effect agent | proof that a write argument comes from a prior tool effect |
| Relation agent | proof that an entity is connected by contact/ownership/membership |
| State-delta agent | proof that the write creates the required before/after state change |

The barrier is deliberately non-agentic. It verifies all proposals and serializes a write only under unique proof validity.

## The Free Lunch

The free lunch is selective recurrence under deterministic safety:

- easy writes can commit in one round once their proof is valid;
- ambiguous writes do not become wrong writes;
- extra compute is spent only on missing or competing proofs;
- parallel agents search different proof obligations at the same time;
- the controller never trusts the agents' confidence as a commit condition.

This differs from self-consistency and debate. More agent outputs do not vote the answer into existence; they increase the chance that one valid proof obligation is found.

## Claim Boundary Today

Defensible now:

> Proof-carrying action proposals are a better recurrent control object than confidence, voting, scalar provenance, or value occurrence for stateful tool-use writes. In opened AppWorld data, role-aware deterministic proof obligations recover nontrivial safe commits while unsafe occurrence baselines fail.

Not defensible yet:

- an LLM can synthesize these proofs reliably;
- this is a sealed benchmark result;
- hand-written verifier coverage is the final method;
- AppWorld-specific rules are the contribution.

## Next Experiment That Actually Tests The Research Idea

The next meaningful model experiment is **LLM proof-sketch synthesis**, not LLM judgment and not proof-family classification.

Protocol:

1. Freeze proof-sketch grammar and output parser.
2. Give the model protected-clean action context plus allowed proof obligations.
3. Model emits a bounded proof sketch, not a final decision.
4. Deterministic verifier checks the sketch against immutable reads/effects.
5. Barrier commits only under unique valid proof.
6. Compare against direct action, self-consistency, occurrence verifier, API-aware mapper, hand-coded templates, and sequential matched-budget synthesis.

Safety gate:

```text
unsafe_unique_wrong == 0
```

Coverage metric:

```text
safe_commit_recovery over exclusive-abstain / fail-closed baseline
```

Fresh variations 10-12 remain sealed until the prompt, parser, budget, verifier grammar, and adversarial witness search are frozen.

## Summary

The research idea is not to hand-code AppWorld. The research idea is to make state mutation conditional on verifiable proof obligations, and to use recurrence as proof repair rather than answer reconsideration. Broad AppWorld is the stress test because writes are stateful, cross-app, and unsafe when scalar evidence is mistaken for derivation.