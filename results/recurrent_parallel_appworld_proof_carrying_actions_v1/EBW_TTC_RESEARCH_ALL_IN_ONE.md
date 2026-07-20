# EBW / Test-Time Compute Research Summary

## Status

This file is the single integrated summary of the EBW Track A / recurrent multi-agent / test-time compute line as of 2026-07-20.

It consolidates:

- the research question;
- the method;
- what was implemented;
- the opened-pool repair sequence;
- prospective held-out TTC results;
- controls and ablations;
- current claim boundary;
- what is still needed for a paper.

## One-Sentence Summary

We built a proof-carrying action system for real AppWorld agent writes where verifier failures become repair state, and we show that frozen structured RepairAgent test-time compute with a deterministic compiler and MetaVerifier can safely close held-out abstentions that one-shot proof agents, best-of-N proof sketches, free-form repair, and compiler-only repair do not close.

## Research Question

The current research question is:

> Can typed verifier residuals make test-time compute useful for multi-agent proof-carrying action systems, by turning failed verifier checks into structured repair decisions that a RepairAgent selects under a fixed compiler and MetaVerifier?

After v38/v42, this should be stated carefully:

> Does frozen structured RepairAgent compute improve safe held-out action coverage, and when are typed residual labels necessary beyond API/field failure metadata?

The second formulation is more precise, because v38 showed that the first held-out literal-path slice can be solved even when explicit typed residual labels are withheld.

## Current Best Answer

We have evidence for three claims:

1. Structured primitive selection plus deterministic compiler plus MetaVerifier can safely improve held-out EBW coverage.
2. Generic extra proof-sketch sampling does not explain the held-out improvement.
3. MetaVerifier is necessary for safety, because compiler-only structured repair accepts bad slot choices.

We do not yet have headline-grade evidence that typed residual labels are always necessary. We have:

- v38: no-typed residual succeeds on an easy literal-path held-out slice.
- v42: typed residual succeeds and no-typed residual fails on an exploratory hard ordered-note pass-subset.

The v42 result supports typed-label usefulness, but it is not headline eligible because the v39 hard held-out protocol was blocked.

## Core Method

The method has five parts.

### 1. Proof-Carrying Actions

The model does not directly justify writes with natural language. It emits strict JSON proof sketches such as:

- `literal_intent_binding`
- `path_pair_transform_binding`
- `title_slug_export_path_binding`
- `directory_basename_archive_path_binding`
- `source_path_identity_binding`
- `ordered_note_title_identity_binding`
- `prior_effect_binding`

### 2. Deterministic Verifier

Each proof sketch is checked against immutable evidence from pre-write reads or prior effects.

### 3. Unique-Validity Barrier

A write commits only if exactly one candidate, the live value, is valid. If no candidate is valid or multiple candidates are valid, the system abstains or recurs. Unsafe unique wrong commits are the main safety failure.

### 4. Typed Residuals

Verifier failures are grouped into residual classes such as:

- `path_pair_transform_binding` missing;
- `title_slug_export_path_binding_missing`;
- `directory_basename_archive_path_binding_missing`;
- `source_path_identity_binding_missing`;
- `literal_export_path_binding_missing`;
- `ordered_note_title_identity_binding_abstain`;
- `prior_effect_playlist_id_binding_abstain`.

### 5. RepairAgent with MetaVerifier

Free-form patch JSON is unsafe or unreliable. The stronger design is:

```text
typed/untyped residual packet
  -> RepairAgent selects primitive IDs from a frozen library
  -> deterministic compiler builds a patch/proposal
  -> MetaVerifier accepts only verifier-safe repairs
  -> proof search or rescore continues under accepted frontiers
```

## Main Development Trajectory

### Initial Safety Failure

The full opened executable v8 model run failed safety:

```text
v8 full executable:
  847 rows
  601 commit_live
  90 abstain_no_valid
  156 unsafe_unique_wrong
```

The unsafe rows were concentrated in derived path writes.

### Deterministic and Model-Assisted Frontier Repairs

The repair sequence then closed unsafe and abstain frontiers under strict verifier gates.

| Stage | Main Repair | Result |
|---|---|---|
| v10 | path-pair transform | 757 commit, 90 abstain, 0 unsafe |
| v11b | title-slug export path | 822 commit, 25 abstain, 0 unsafe |
| v17 | archive path | 831 commit, 16 abstain, 0 unsafe |
| v22 | source-path identity | 836 commit, 11 abstain, 0 unsafe |
| v24 | literal export path | 838 commit, 9 abstain, 0 unsafe |
| v26 | ordered-note title identity | 840 commit, 7 abstain, 0 unsafe |
| v28 | prior-effect playlist | 847 commit, 0 abstain, 0 unsafe |

Important boundary:

- v21-v28 are deterministic proof-frontier closure, not Qwen proof synthesis.
- v28 is the strongest opened-scope deterministic closure result.

### RepairAgent Results Before Held-Out TTC

| Stage | RepairAgent Mode | Result |
|---|---|---|
| v14 | free-form patch JSON | 0/2 accepted |
| v16b | primitive selection for title-slug and contract repair | 2/2 accepted after targeted retry |
| v19 | archive primitive selection | 1/1 accepted |
| v29b | primitive selection over v21-v28 closure packets | 4/4 accepted after targeted retry |

These results support structured primitive selection under a fixed compiler and MetaVerifier.

## Test-Time Compute Line

### v30: Freeze and Retrospective Replay

v30 froze the TTC protocol:

- parser;
- verifier;
- rescorer;
- v29 primitive library;
- deterministic compiler;
- MetaVerifier;
- RepairAgent primitive-selection response contract.

Retrospective opened-data replay:

```text
round0 no repair:            831 commit / 16 abstain / 0 unsafe
round1 parallel v29b repair: 847 commit / 0 abstain / 0 unsafe
repair model calls:          5
```

Claim boundary:

- v30 validates mechanics only.
- It is not held-out test-time compute evidence.

## Prospective Held-Out TTC: v31-v38

### Held-Out Setup

Fresh AppWorld variations 10-12 were opened after v30 freeze.

```text
v31 held-out preflight:
  24 fresh tasks
  169 value-free target instances
  65 executable EBW prompts
```

### Main Held-Out Result

| Stage | Method | Result |
|---|---|---|
| v32 | one-shot proof agents, no repair | 62 commit, 3 abstain, 0 unsafe |
| v33 | structured RepairAgent + MetaVerifier | 65 commit, 0 abstain, 0 unsafe |

The v33 repair was one residual packet:

```text
literal_export_path_binding_missing
target rows: 3
selected primitives:
  span_source.quoted_task_path_exact
  target_arg.file_path
  parser_policy.strict
```

### Held-Out Controls

| Control | Model Calls | Commit | Abstain | Unsafe | Accepted Repairs | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| one-shot no repair | 65 | 62 | 3 | 0 | n/a | baseline proof-agent pass |
| best-of-N no repair | 24 | 62 | 3 | 0 | 0 | extra proof-sketch sampling does not recover residuals |
| free-form RepairAgent patch JSON | 1 | 62 | 3 | 0 | 0 | patch parses but MetaVerifier rejects wrong slot |
| structured without MetaVerifier | 0 | n/a | n/a | n/a | 3 | compiler-only accepts bad slot controls |
| structured no typed residual + MetaVerifier | 1 | 65 | 0 | 0 | 1 | succeeds on narrow literal-path slice |
| structured with typed residual + MetaVerifier | 1 | 65 | 0 | 0 | 1 | succeeds on same slice |

### Interpretation of v31-v38

The first held-out slice supports:

- structured primitive selection is better than generic proof-sketch sampling;
- free-form patch JSON is not reliable;
- MetaVerifier is necessary;
- the frozen library and field metadata can be enough for simple literal-path residuals.

It does not prove that typed residual labels are necessary.

## Hard Residual Probe: v39-v42

### v39 Formal Hard-Heldout Protocol

Targeted hard generator families:

| Generator | Target Residual Family |
|---|---|
| `68ee2c9` | source-path identity |
| `cf6abd2` | ordered-note title/content identity |
| `6171bbc` | prior-effect playlist |
| `e3d6c94` | prior-effect playlist |

v39 was blocked:

- `6171bbc` failed to generate variations 10-12;
- audit variations 1-2 did not semantically match the broad-schema parent.

Therefore v39 is not headline-eligible.

### v40-v42 Exploratory Pass-Subset

The generated pass-subset contains:

```text
v40:
  9 fresh tasks
  467 value-free target instances
  generators: 68ee2c9, cf6abd2, e3d6c94

v41 hard target:
  15 rows
  source-path identity: 6
  ordered-note identity: 3
  prior-effect playlist: 6

v41 no repair:
  12 commit / 3 abstain / 0 unsafe
  all 3 abstains are ordered-note identity
```

Typed vs untyped RepairAgent on those 3 ordered-note abstains:

| Condition | Selection | Accepted | Rescore |
|---|---|---:|---|
| typed residual | `content_binding.quoted_task_item_in_prewrite_content` | yes | 15 commit, 0 abstain |
| untyped residual | `content_binding.output_content_contains_item` | no | 12 commit, 3 abstain |

Interpretation:

- v42 gives exploratory evidence that typed residual text can matter on harder relation-like residuals.
- It is not headline held-out evidence because v39 was blocked.

## Current Claim Boundary

The strongest defensible claim is:

> Under a frozen proof/repair substrate, structured RepairAgent test-time compute with deterministic compilation and MetaVerifier can close prospective held-out safe abstentions that one-shot proof agents, best-of-N proof sketches, free-form repair, and compiler-only repair do not safely close.

With the caveat:

> Typed residual labels are useful and can matter on harder exploratory residuals, but their necessity is not yet established by a clean headline held-out benchmark.

Do not claim:

- fully open-ended autonomous repair;
- that v21-v28 are Qwen synthesis;
- that v30 retrospective replay is held-out TTC;
- that v42 is headline held-out evidence;
- that typed residual labels are universally necessary.

## Paper Contributions

The paper contribution should be framed as:

1. Evidence-Bound Writes / Proof-Carrying Actions for real agent writes.
2. A strict verifier barrier that turns unsafe writes into safe abstentions and residual state.
3. A structured RepairAgent action space: primitive selection, deterministic compilation, and MetaVerifier acceptance.
4. Prospective held-out TTC evidence that structured MetaVerified repair improves safe coverage where best-of-N and free-form repair fail.
5. An exploratory hard-residual probe showing typed residual labels can matter for ordered-note identity, with a clear non-headline boundary.

## Paper-Ready Tables

### Table A: Opened-Scope Repair Trajectory

| Stage | Commit | Abstain | Unsafe |
|---|---:|---:|---:|
| v8 full executable | 601 | 90 | 156 |
| v10 path-pair | 757 | 90 | 0 |
| v11b title-slug | 822 | 25 | 0 |
| v17 archive | 831 | 16 | 0 |
| v28 deterministic closure | 847 | 0 | 0 |

### Table B: Prospective Held-Out TTC

| Method | Commit | Abstain | Unsafe | Note |
|---|---:|---:|---:|---|
| one-shot no repair | 62 | 3 | 0 | v32 |
| best-of-N no repair | 62 | 3 | 0 | v34, 8 samples on failed rows |
| free-form RepairAgent | 62 | 3 | 0 | v35, patch rejected |
| structured + MetaVerifier | 65 | 0 | 0 | v33 |

### Table C: MetaVerifier Necessity

| Variant | Accepted Repairs | Safety Interpretation |
|---|---:|---|
| structured with MetaVerifier | 1/1 | closes held-out gap safely |
| structured without MetaVerifier | 3/3 | accepts 2 bad controls |

### Table D: Typed Residual Label Probe

| Slice | Typed | Untyped | Interpretation |
|---|---|---|---|
| literal export held-out | pass | pass | typed labels not necessary here |
| ordered-note hard pass-subset | pass | fail | typed labels help here, exploratory only |

## What Is Still Needed for a Paper

### 1. Clean Hard Held-Out Benchmark

The biggest missing piece is a clean preregistered hard held-out split that passes generation and semantic audit. It should include source-path, ordered-note, and prior-effect residuals.

### 2. Larger Held-Out Scale

The first held-out TTC result is narrow:

```text
65 executable prompts
3 repaired abstains
1 residual family
```

This is a proof-of-mechanism, not a broad benchmark.

### 3. Robustness

Run the frozen protocol across:

- additional held-out generators;
- multiple seeds or model variants;
- harder residual mixtures;
- fixed budget curves.

### 4. Formal Method Section

Define:

```text
proof sketch p
evidence E
candidate action a
verifier V(p, E, a)
barrier B
residual r
primitive selection s
compiler C(s)
MetaVerifier M(C(s), r)
```

### 5. Clear Claim Language

Recommended headline phrasing:

> Structured test-time repair under a deterministic proof barrier improves safe held-out action coverage, while controls show that generic sampling, free-form patching, and compiler-only repair do not provide the same safety-preserving improvement.

Avoid claiming more than the data supports.

## Key Artifact Index

| Topic | Artifact |
|---|---|
| Main closeout | `TRACK_A_V4_SMOKE_CLOSEOUT.md` |
| Research framing | `TRACK_A_RESEARCH_FRAMING_V9.md` |
| Raw JSON index | `TRACK_A_RAW_JSON_INDEX_AND_ANALYSIS.md` |
| RepairAgent benchmark spec | `specs/recurrent_parallel_ebw_repairagent_benchmark_v11.md` |
| TTC protocol | `specs/recurrent_parallel_ebw_test_time_compute_v1.md` |
| Held-out TTC protocol | `specs/recurrent_parallel_ebw_test_time_compute_heldout_v1.md` |
| Hard residual protocol | `specs/recurrent_parallel_ebw_hard_residual_heldout_v1.md` |
| Held-out control summary | `track_a_v37_heldout_control_summary/SUMMARY.md` |
| Hard typed/untyped report | `track_a_eval_v42_hard_typed_vs_untyped/REPORT.md` |
