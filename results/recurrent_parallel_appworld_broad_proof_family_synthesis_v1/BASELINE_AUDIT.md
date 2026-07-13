# Baseline Audit for Broad Proof-Carrying AppWorld Line

## Status: **`BASELINE_AUDIT_COMPLETE`**

This audit reviews the baselines relevant to the current proof-carrying recurrent multi-agent line before any further model run.

## Main Conclusion

Do not spend GPU/model budget on proof-family name classification alone. The weak field-kind baseline is 22/45, and an API-aware deterministic mapper solves the current 45 schema-level labels at 45/45 because the labels are themselves API/field-family rules. That makes an LLM family selector an engineering/parser result, not a research contribution.

The research path should move to proof-carrying witness synthesis and deterministic verifier competition, where the model must produce bounded proof sketches over immutable read/state references and the barrier commits only under unique verified support.

## Baselines Already Established

| Baseline | Result | Interpretation |
|---|---:|---|
| Qwen binary correction judge | pooled balanced accuracy 0.566; Brier 0.392; ECE 0.381 | Negative anchor. Model confidence/judgment is not a good recurrent control signal. |
| Typed max-tier provenance | 45 correct, 3 wrong over 71 strict pairs | Unsafe forced-commit baseline. Useful because exclusive provenance blocks its errors. |
| Exclusive scalar provenance | 45 correct, 0 wrong over 71 strict pairs | Strong abstention baseline. Any new method must preserve these commits and reduce abstentions without wrong writes. |
| Active-read one-round oracle | 0/26 resolved | More reads do not help under scalar evidence representation. The evidence algebra, not query policy, was the bottleneck. |
| Full-record availability ceiling | 0/26 resolved | Even broad record access fails without value-to-action derivation. |
| Output-bound derivation witness | 26/26 correct, 0 wrong | Gold ceiling showing the missing object is a bound derivation witness. |
| Local-frame bounded DSL | 26/26 correct, 0 wrong | Bounded verifier works, but still gold-local. |
| Read-ref proof DSL | 26/26 correct, 0 wrong | Immutable read-reference proofs work on the opened 26 pairs. |
| Direct read-ref adversarial search | 10 commit-live, 16 ambiguous, 0 unsafe unique-wrong | Direct scalar entity proofs are too weak; ambiguity is correctly surfaced. |
| Relation proof v1 | 19 commit-live, 2 unsafe unique-wrong | Relation predicates without ordered/cursor constraints are unsafe. |
| Relation proof v2 ordered | 22 commit-live, 4 safe abstain, 0 unsafe | Current strongest deterministic proof baseline on the opened ambiguity set. |
| Narrow schema mapper | 26/26 proof-family labels | Saturated on the old five-schema set; not research-worthy as an LLM task. |
| Broad weak field-kind baseline | 22/45 | Parser/evaluator sanity baseline only; not a strong paper baseline. |
| Broad API-aware deterministic mapper | 45/45 | Confirms schema-level proof-family classification is saturated without a model. |
| Broad value-bound occurrence verifier | 880 ambiguous, 386 unsafe unique-wrong over 1266 instances | Negative verifier baseline. Scalar occurrence binding is unsafe and cannot support proof-carrying commits. |
| Broad filesystem path derivation verifier | 75 commit-live, 231 ambiguous, 241 abstain, 0 unsafe over 547 path instances | First positive value-bound derivation baseline. A small path relation constraint recovers commits while preserving safety. |
| Broad literal text derivation verifier | 46 commit-live, 78 abstain, 0 unsafe over 124 literal-text instances | Conservative quoted-literal verifier recovers explicit user text while failing closed on composed text. |
| Broad safe derivation ledger | 121 commit-live, 231 ambiguous, 914 abstain, 0 unsafe over 1266 instances | Current deterministic safe lower bound: path + literal verifiers, state-transition fail-closed. |
| Broad created-playlist state verifier | 18 commit-live, 0 unsafe over 18 target instances | Prior-effect reference: playlist ID produced by `create_playlist` and consumed by `add_song_to_playlist`. |
| Broad safe derivation ledger v2 | 139 commit-live, 231 ambiguous, 896 abstain, 0 unsafe over 1266 instances | Current deterministic safe lower bound after adding one state-transition effect verifier. |
| Broad ordered-entity state verifier | 257 commit-live, 292 abstain, 28 unsafe over 577 remaining state instances | Negative broad state baseline. Ordered same-field entity binding is too coarse as a general verifier. |
| Broad safe derivation ledger v4 | 185 commit-live, 231 ambiguous, 850 abstain, 0 unsafe over 1266 instances | Imports only zero-unsafe schema slices from the failed ordered-entity verifier. |
| Broad like-song state verifier | 149 commit-live, 6 abstain, 0 unsafe over 155 target instances | Queue/search-aware evidence-role verifier for `spotify.like_song.song_id`. |
| Broad safe derivation ledger v5 | 334 commit-live, 231 ambiguous, 701 abstain, 0 unsafe over 1266 instances | Current deterministic safe lower bound after adding the like-song verifier. |
| Broad Venmo-like state verifier | 5 commit-live, 61 abstain, 1 unsafe over 67 target instances | Negative relation/cursor baseline. Contact/date/social-feed order is insufficient in broad data. |

## Missing Baselines Before a Model Claim

| Missing baseline | Why it matters | Required before |
|---|---|---|
| Hand-coded template witness synthesizer | Shows how far deterministic rules get once proof sketches, not labels, are required. | Any proof-synthesis claim. |
| Direct action without proof | Measures ordinary tool-use/write behavior without proof carrying. | Any end-to-end AppWorld claim. |
| Citation/provenance-count commit | Tests whether counting evidence beats proof binding. | Any commit-safety claim. |
| Best-of-N self-consistency under matched token budget | Controls for spending extra model calls without verifier semantics. | Any LLM synthesis comparison. |
| Sequential single-agent matched-budget planner | Controls for parallelism versus total compute. | Any multi-agent/free-lunch claim. |
| Random valid proof-family / random valid witness template | Floor for prompt/parser and verifier acceptance. | Any model proof-family or witness run. |

## What This Means For the Next Step

The next strong experiment should not be `LLM chooses proof_family`. It should be:

1. freeze a broad proof-sketch grammar for at least three families:
   - `state_transition_membership_proof`;
   - `filesystem_path_derivation_proof`;
   - `literal_text_derivation_proof`;
2. implement deterministic verifiers for those sketches;
3. add deterministic template synthesizer baselines;
4. run adversarial alternate-witness search;
5. only then consider LLM witness synthesis under matched-budget baselines.

## Current Claim Boundary

The defensible claim right now is not that an LLM can choose proof families. It is that the baseline ladder has isolated the real contribution target:

> In stateful tool-use workflows, safe recurrent commit requires verifiable action-bound derivations, not confidence scores, evidence counts, or scalar provenance. Parallel agents are useful only if their proposals enter a deterministic proof barrier that can abstain on ambiguity.

The current broad prompt/eval artifacts are useful infrastructure, but the API-aware mapper baseline confirms they are not sufficient for a research claim until witness-level baselines and adversarial proof search are in place.

The first value-bound occurrence verifier baseline further sharpened the target: merely finding a candidate value in pre-write reads is unsafe. The filesystem path derivation verifier then showed the intended direction: encode how the write argument is derived and why that derivation is exclusive for the candidate. Even a narrow basename-preserving move-file rule recovered 75 safe commits with zero unsafe unique-wrong. The literal text verifier adds a second safe derivation pattern: exact quoted instruction literals recover 46 commits with zero unsafe unique-wrong.

The combined safe derivation ledger v1 gave a broad deterministic lower bound: 121 safe commits and zero unsafe unique-wrong across 1266 opened witness instances, with all 595 state-transition instances failed closed pending effect/cursor verification. Ledger v2 adds the first state-transition effect proof and raises the lower bound to 139 safe commits with zero unsafe unique-wrong. The broad ordered-entity verifier is unsafe as a general state rule, but ledger v4 safely imports its zero-unsafe schema slices and raises the lower bound to 185 safe commits with zero unsafe unique-wrong. The like-song verifier then adds evidence-role semantics for queue/search traces and raises the current lower bound to 334 safe commits with zero unsafe unique-wrong. The Venmo-like verifier shows the danger of overgeneralizing the old relation-v2 rule: contact/date/social-feed order is not sufficient in the broader pool, so it remains excluded from the safe ledger.