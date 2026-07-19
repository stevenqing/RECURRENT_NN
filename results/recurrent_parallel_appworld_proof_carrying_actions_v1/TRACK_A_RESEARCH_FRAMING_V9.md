# EBW Track A Research Framing After v8

## Status: **`RPD_EBW_TRACK_A_RESEARCH_FRAMING_V9_READY`**

Date: 2026-07-14

## Why This Is Not Just Engineering

The v3-v8 sequence can look like prompt engineering if each fix is read locally. The research object is different: each failure identifies a missing part of a proof system for safe state mutation.

The pattern is:

```text
LLM proposes proof sketch -> deterministic verifier checks sketch against immutable evidence -> barrier commits only under unique validity
```

The contribution is not that a particular prompt works. The contribution is that LLM proof synthesis is unsafe unless the proof grammar exposes a typed, deterministic evidence frontier that is complete enough to identify the write argument.

## Failure Taxonomy

| Failure class | Observed in | Symptom | Research lesson |
|---|---|---|---|
| Parser/protocol failure | v1-v2 | strict parse 0.0; model emits fenced JSON and prompt continuation | A proof-carrying system cannot use tolerant extraction as its primary safety gate. |
| Role-selection failure | v3-v4 | model picks syntactically valid but semantically wrong obligation | Proof roles must be deterministic commitments, not free-form model choices. |
| Slot/frontier failure | v5-v8 shard | model picks wrong literal span or ordered source | Proof variables must be selected from row-specific evidence frontiers. |
| Under-specified grammar failure | full v8 | 156 unsafe derived-path commits | A grammar that proves only basename is incomplete for destination-path writes. |

This is a research sequence because every repair is a hypothesis about which proof obligation is missing, followed by a safety-gated test on opened data.

## What The Full v8 Failure Shows

The full v8 executable run processed 847 opened rows and failed safety:

| Decision | Count |
|---|---:|
| `commit_live` | 601 |
| `abstain_no_valid` | 90 |
| `unsafe_unique_wrong` | 156 |

All 156 unsafe unique-wrong cases are `derived_path_binding` on `move_file.destination_file_path`.

The unsafe examples are not parser failures and not role failures. The model emits a valid derived-path sketch, and the sketch often matches an allowed source candidate. The problem is that the proof only binds source basename, while the live action also depends on:

- a date prefix from file metadata such as `created_at`;
- a destination directory rule such as current-year files stay in `~/downloads/`, older files move to `~/trash/`;
- the full destination path shape.

Thus basename is a lossy projection. It is insufficient as a proof of `destination_file_path`.

## Research Claim Boundary After v8

Defensible:

> LLM proof sketches require deterministic, typed evidence frontiers and a grammar whose obligations are complete for the write argument. When the grammar is under-specified, the unique-validity barrier can still commit wrong actions even if parse rate is high and the model obeys candidate constraints.

Not defensible:

- v8 is a safe full-opened AppWorld result;
- candidate filtering alone solves EBW;
- basename derivation is a complete proof for destination paths;
- the current full opened-pool run should be a headline result.

## Why v9 Is Not Another Patch

v9 should be framed as a confirmatory test of the under-specified grammar hypothesis:

**Hypothesis:** derived-path unsafe cases arise because Track A's `derived_path_binding` grammar proves only basename, while the target action requires a path-pair transformation.

**Prediction:** adding a `path_pair_transform_binding` proof that binds source path, destination directory, date prefix, and basename should specifically reduce derived-path unsafe cases without changing literal, ordered-role, or prior-effect behavior.

**Falsifier:** if derived-path unsafe remains high after path-pair evidence is required, then the problem is not only grammar incompleteness; it may be model synthesis quality or verifier semantics.

## v9 Confirmatory Test

Run this before any full-opened headline claim:

1. Add a v9 grammar arm for filesystem path-pair transforms.
2. Build deterministic candidate frontiers containing:
   - `source_read_id` and source path field;
   - source basename;
   - metadata date field when the destination name requires a date prefix;
   - destination directory evidence/rule;
   - expected full destination path candidate.
3. Require model sketch fields to match one candidate exactly.
4. Run a filesystem-heavy opened shard containing the failed `68ee2c9_*` rows.
5. Gate on `unsafe_unique_wrong == 0` before any full executable rerun.

## Feasibility Audit

The first CPU-only feasibility audit is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_feasibility/FEASIBILITY.md`.

Over the 537 derived-path executable rows from full v8:

| Label | Rows |
|---|---:|
| `path_pair_candidate_matches_live` | 120 |
| `path_pair_candidate_mismatch` | 192 |
| `no_path_pair_candidate` | 225 |

For the 156 full-v8 unsafe rows:

| Label | Rows |
|---|---:|
| `path_pair_candidate_matches_live` | 120 |
| `path_pair_candidate_mismatch` | 36 |

This mattered as a staged v9 boundary: the initial parser explained 120/156 unsafe rows and exposed 36 path-pair mismatches. Inspecting those 36 showed a narrower typed residual: the task text parser captured terminal sentence punctuation in paths such as `~/trash/.`, while the live action used the canonical directory `~/trash`.

The next v9 test should therefore be staged:

1. target the 120 rows with matched path-pair candidates and verify unsafe drops there;
2. inspect the 36 mismatches to extend the path-rule grammar;
3. only then rerun a filesystem-heavy shard and, later, full executable opened-pool execution.

## Deterministic v9 Gate

The first staged gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v9_path_pair_gate/GATE.md`.

It targets exactly the 120 full-v8 unsafe rows with matching path-pair candidates:

| Decision after v9 path-pair proof | Rows |
|---|---:|
| `commit_live` | 120 |
| `unsafe_unique_wrong` | 0 |

This supports the hypothesis that a complete path-pair proof can eliminate the directly covered derived-path unsafe class. The remaining 36 then became a parser-normalization residual, not a new proof-family failure.

## Model-Facing v9 Gate

The model-facing target-shard run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v9_target_shard/REPORT.md`.

It uses the same 120 covered rows, but requires Qwen to emit the new `path_pair_transform_binding` sketch:

| Decision | Rows |
|---|---:|
| `commit_live` | 120 |
| `unsafe_unique_wrong` | 0 |

Parse rate is 1.0, and all 120 raw outputs use `path_pair_transform_binding`.

This is the strongest support so far for the text-gradient story: the full-v8 `projection_loss` residual led to a grammar extension, the deterministic frontier exposed exact path-pair candidates, and the model could synthesize the new proof sketch under strict parsing.

## v10 Path-Rule Normalization Gate

The v10 CPU-only gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_path_rule_normalized_gate/GATE.md`.

It canonicalizes directory literals and dot segments before matching path-pair candidates. Under the same deterministic barrier:

| Decision after v10 normalized path-pair proof | Rows |
|---|---:|
| `commit_live` | 156 |
| `unsafe_unique_wrong` | 0 |

This covers all full-v8 derived unsafe rows. A 156-row model-facing prompt manifest was staged at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_prompt_manifest_v10_path_rule_normalized/PROMPT_MANIFEST.md`, with all rows using `path_pair_transform_binding` and matching path-pair candidates.

The v10 model-facing run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v10_path_rule_normalized/REPORT.md`:

| v10 model decision | Rows |
|---|---:|
| `commit_live` | 156 |
| `unsafe_unique_wrong` | 0 |

Parse rate is 1.0, and all 156 raw outputs use `path_pair_transform_binding`.

Research interpretation: v10 is a second typed-residual recurrence. v8 exposed projection loss; v9 repaired proof grammar. v9 then exposed path literal non-canonicalization; v10 repaired the deterministic parser and Qwen synthesized the repaired proof family over the full 156-row target. This is exactly the text-gradient loop the paper should claim.

## Full-Executable Compositional v10 Gate

The full executable opened-pool compositional gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v10_merged/REPORT.md`.

It merges row-independent greedy outputs:

- 691 unchanged rows from the full-v8 executable model run;
- 156 diagnosed derived-path unsafe rows from the v10 normalized path-pair model run.

The merged prompt/raw artifacts are recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v10_full_merged_outputs/MERGE.md`.

CPU rescore over all 847 executable rows gives:

| Decision | Rows |
|---|---:|
| `commit_live` | 757 |
| `abstain_no_valid` | 90 |
| `unsafe_unique_wrong` | 0 |

This is stronger than the 156-row target gate because it preserves the v8 safe subsets while replacing exactly the previously unsafe derived-path class. It is still not a new monolithic GPU full-run; it is a compositional row-level full executable gate justified by independent greedy row generation.

## v11 Residual Taxonomy

The v11 CPU-only taxonomy is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_residual_taxonomy/TAXONOMY.md`.

After the v10 full-executable compositional gate, there are no unsafe rows. The remaining 90 abstains are frontier gaps:

| Residual class | Rows |
|---|---:|
| `title_slug_export_path_binding_missing` | 65 |
| `directory_basename_archive_path_binding_missing` | 9 |
| `prior_effect_playlist_membership_binding_abstain` | 7 |
| `source_path_identity_binding_missing` | 5 |
| `literal_export_path_binding_missing` | 2 |
| `ordered_note_identity_binding_abstain` | 2 |

The next research target should be `title_slug_export_path_binding`: it is the largest post-v10 abstain class and requires a new evidence-bound transform from note title to filesystem path. This is a better RepairAgent benchmark than another v10 score run because it tests residual-to-frontier repair on a new proof family.

## v11 Title-Slug Feasibility

The R1 CPU feasibility gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v11_title_slug_feasibility_v2/FEASIBILITY.md`.

The corrected title-slug frontier covers all 65 target rows:

| Decision | Rows |
|---|---:|
| `commit_live` | 65 |
| `unsafe_unique_wrong` | 0 |

The important research signal is the residual discovered by the first attempt: Simple Note content is not unique, so a content-only source binding can attach the wrong title. The accepted frontier must bind to the latest matching pre-write `show_note` read. This is a clean example of typed residuals sharpening the proof frontier rather than merely changing prompt wording.

## v11 Title-Slug Model Gate

The R3 model-facing run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11_title_slug_target/REPORT.md`.

Strict primary result:

| Decision | Rows |
|---|---:|
| `commit_live` | 60 |
| `abstain_no_valid` | 5 |
| `unsafe_unique_wrong` | 0 |

Parse rate is 0.923. The 5 abstains are not verifier mismatches. Four outputs used `required_obligation` instead of the required output key `obligation`; one omitted `obligation`. A CPU diagnostic that repairs only this output-contract key commits all 65 rows with 0 unsafe.

Research interpretation: the title-slug proof family is semantically synthesized, but the prompt contract still leaks the role-constraint name into the output schema. The next repair should be a v11b response-contract prompt fix, not a tolerant parser change.

## v11b Contract Repair And Full Gate

The v11b contract retry is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v11b_contract_retry/REPORT.md`.

It reruns only the 5 strict parse/contract failures with a stronger response contract and the same strict parser:

| v11b retry decision | Rows |
|---|---:|
| `commit_live` | 5 |
| `unsafe_unique_wrong` | 0 |

Merging the original 60 strict-valid v11 outputs with the 5 v11b retries gives a 65-row title-slug target gate with 65 `commit_live`, parse rate 1.0, and 0 unsafe. Merging those title-slug repairs into the full v10 executable compositional gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v11b_merged/REPORT.md`:

| Full executable v11b decision | Rows |
|---|---:|
| `commit_live` | 822 |
| `abstain_no_valid` | 25 |
| `unsafe_unique_wrong` | 0 |

Research interpretation: this is a clean example of a typed residual at the response-contract layer. The correct repair was not to loosen parsing, but to keep the parser fixed and repair the prompt contract. The proof frontier and MetaVerifier barrier remain unchanged.

## v12 MetaVerifier Preflight

The CPU-only MetaVerifier preflight is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v12_repairagent_metaverifier/REPORT.md`.

It turns the v11/v11b repairs into explicit typed residual packets and patch proposals. Positive proposals are accepted only if they reproduce the deterministic gates; negative controls must fail closed.

| Proposal | Accepted | Reason |
|---|---:|---|
| `P_TITLE_SLUG_LATEST_SHOW_NOTE` | True | `accepted_latest_read_frontier` |
| `P_OUTPUT_CONTRACT_OBLIGATION_KEY` | True | `accepted_contract_repair` |
| `C_TITLE_SLUG_CONTENT_ONLY` | False | `rejected_content_only_source_binding` |
| `C_TITLE_SLUG_RESIDUAL_SHUFFLED` | False | `rejected_residual_family_mismatch` |
| `C_OUTPUT_CONTRACT_TOLERANT_PARSER` | False | `rejected_parser_relaxation` |
| `C_PROMPT_ONLY_NO_FRONTIER` | False | `rejected_prompt_only_no_frontier` |

Research interpretation: this is still not autonomous RepairAgent discovery. It is the MetaVerifier substrate for that experiment. The next model/agent run should receive the same residual packets as text and propose patches; the MetaVerifier should remain unchanged.

## v14 Answer-Blinded RepairAgent Attempt

The answer-blinded RepairAgent model run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v14_repairagent_blind/REPORT.md`, and the unchanged MetaVerifier evaluation is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v14_repairagent_blind/REPORT.md`.

The model outputs parseable patch JSON for both residual packets, but the MetaVerifier accepts none:

| Residual | Parse OK | Accepted | Reason |
|---|---:|---:|---|
| `R_TITLE_SLUG_SOURCE_BINDING_AMBIGUITY_V11` | True | False | `rejected_content_only_source_binding` |
| `R_OUTPUT_CONTRACT_OBLIGATION_KEY_V11B` | True | False | `contract_repair_failed_gate` |

This is the right kind of negative result: the MetaVerifier catches the model's shortcut repairs. The current autonomous RepairAgent claim is therefore not established. The next proposal source must be more structured or trained, while the MetaVerifier should remain unchanged.

## v15 Structured Repair Policy

The CPU-only structured policy is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v15_structured_repair_policy/REPORT.md`.

It constrains RepairAgent to a primitive library and deterministic compiler. The policy selects primitives from typed residual packets, compiles patch JSON, and sends the compiled proposals to the unchanged v12 MetaVerifier.

| Proposal | Accepted | Reason |
|---|---:|---|
| `structured_title_slug_latest_show_note` | True | `accepted_latest_read_frontier` |
| `structured_output_contract_obligation_key` | True | `accepted_contract_repair` |
| `control_title_slug_content_only` | False | `rejected_content_only_source_binding` |
| `control_title_slug_residual_shuffled` | False | `rejected_residual_family_mismatch` |
| `control_output_contract_tolerant_parser` | False | `rejected_parser_relaxation` |
| `control_prompt_only_no_frontier` | False | `rejected_prompt_only_no_frontier` |

Research interpretation: v14 showed that free-form patch generation is too unconstrained. v15 gives the right action space: model-in-the-loop repair should be framed as primitive selection plus deterministic compilation, not unconstrained JSON invention.

## v16 Model-In-The-Loop Primitive Selection

The v16 primitive-selection model run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v16_primitive_selection/REPORT.md`, and the first eval is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16_primitive_selection_model/REPORT.md`.

Initial v16 result:

| Residual | Parse OK | Compiled | Accepted | Reason |
|---|---:|---:|---:|---|
| `R_TITLE_SLUG_SOURCE_BINDING_AMBIGUITY_V11` | True | True | True | `accepted_latest_read_frontier` |
| `R_OUTPUT_CONTRACT_OBLIGATION_KEY_V11B` | True | False | False | `compile_error` |

The contract residual missed the required `parser_policy.strict` primitive. v16b retries only that compile failure with an explicit slot-completeness instruction; the retry is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16b_primitive_selection_retry/REPORT.md` and passes. The merged v16b eval is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v16b_primitive_selection_merged/REPORT.md`:

| Residual | Parse OK | Compiled | Accepted | Reason |
|---|---:|---:|---:|---|
| `R_TITLE_SLUG_SOURCE_BINDING_AMBIGUITY_V11` | True | True | True | `accepted_latest_read_frontier` |
| `R_OUTPUT_CONTRACT_OBLIGATION_KEY_V11B` | True | True | True | `accepted_contract_repair` |

Research interpretation: v16b is the first model-in-the-loop RepairAgent success under this protocol. The model does not free-form patch the verifier; it selects primitives, and deterministic compilation plus the unchanged MetaVerifier decide acceptance.

## v17 Archive-Path Feasibility

The v17 CPU-only feasibility gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v17_archive_path_feasibility/FEASIBILITY.md`.

It targets the next post-v11b abstain class, `directory_basename_archive_path_binding_missing`, for vacation-directory compression tasks. The frontier binds source directory evidence from immutable pre-write directory listings, extracts the source directory basename as `<vacation_spot>`, and fills the task literal archive path template and extension.

| Decision | Rows |
|---|---:|
| `commit_live` | 9 |
| `unsafe_unique_wrong` | 0 |

The strict grammar, prompt assets, manifest builder, and runner verifier were then extended to this proof family. The model-facing v17 target run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v17_archive_path_target/REPORT.md`:

| Decision | Rows |
|---|---:|
| `commit_live` | 9 |
| `unsafe_unique_wrong` | 0 |

Parse rate is 1.0, and all 9 raw outputs use `directory_basename_archive_path_binding`.

Merging these archive repairs into the full executable compositional gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_full_opened_v17_merged/REPORT.md`:

| Full executable v17 decision | Rows |
|---|---:|
| `commit_live` | 831 |
| `abstain_no_valid` | 16 |
| `unsafe_unique_wrong` | 0 |

Research interpretation: archive-path is now a third proof family repaired by the same loop. It tests a new transform family: directory evidence to archive destination path. The next step is to add it to structured RepairAgent primitive selection, not to keep hand-instantiating repairs.

## v18 Archive Structured Repair Policy

The CPU-only structured archive policy is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v18_archive_structured_repair_policy/REPORT.md`.

It turns the archive residual into a primitive-selection problem. The accepted structured proposal selects:

- `source_binding.immutable_directory_list_entry`
- `basename_transform.directory_basename`
- `destination_template.task_literal_vacation_spot_archive_template`
- `extension_policy.task_template_extension`
- `parser_policy.strict`

MetaVerifier accepts this proposal and rejects six controls: generic basename projection, wrong destination template, wrong basename transform, wrong extension policy, parser relaxation, and prompt-only repair.

Research interpretation: archive-path now fits the same structured RepairAgent action space as title-slug and output-contract repair. The next model step should be primitive selection for this single archive residual packet, not free-form patch generation.

## v19 Archive Model-In-The-Loop Selection

The v19 archive primitive-selection model run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v19_archive_selection/REPORT.md`, and the unchanged archive MetaVerifier evaluation is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v19_archive_selection_model/REPORT.md`.

Qwen selects the complete archive primitive set:

- `source_binding.immutable_directory_list_entry`
- `basename_transform.directory_basename`
- `destination_template.task_literal_vacation_spot_archive_template`
- `extension_policy.task_template_extension`
- `parser_policy.strict`

The deterministic compiler and unchanged MetaVerifier accept the proposal:

| Residual | Parse OK | Compiled | Accepted | Reason |
|---|---:|---:|---:|---|
| `R_ARCHIVE_PATH_DIRECTORY_BASENAME_V17` | True | True | True | `accepted_archive_directory_basename_frontier` |

Research interpretation: v19 extends the model-in-the-loop primitive selection result beyond title-slug/output-contract to a third proof family. The next step should be residual taxonomy over the remaining 16 safe abstentions, not another model run on an already solved family.

## v20 Residual Taxonomy

The v20 CPU-only taxonomy is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v20_residual_taxonomy/TAXONOMY.md`.

After the v17 full executable compositional gate, 16 safe abstentions remain:

| Residual class | Rows |
|---|---:|
| `prior_effect_playlist_id_binding_abstain` | 7 |
| `source_path_identity_binding_missing` | 5 |
| `literal_export_path_binding_missing` | 2 |
| `ordered_note_title_identity_binding_abstain` | 2 |

The next CPU-first target should be `source_path_identity_binding`: it directly complements the path-pair destination proof by proving `move_file.source_file_path` from immutable source path evidence. The larger prior-effect playlist residual should wait until simpler identity/literal frontiers are exhausted.

## v21 Source-Path Identity Feasibility

The v21 CPU-only feasibility gate is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v21_source_path_identity_feasibility/FEASIBILITY.md`.

Result:

```text
target_rows: 5
source_path_identity_candidate_matches_live: 5
commit_live: 5
unsafe_unique_wrong: 0
```

Research interpretation: this is a new proof-family frontier, not a prompt patch. The source path write argument can be proven from immutable pre-write `response.path` evidence by exact identity, while sibling source paths, destination paths, and mutated path-shaped alternatives fail the barrier. The next step is strict parser/prompt/runner integration and CPU compositional rescore before any Qwen run.

## v22-v28 Deterministic Frontier Closure

The post-v21 deterministic repair sequence is CPU-only and does not claim new Qwen synthesis. It tests whether typed residuals can drive proof-frontier expansion until the opened executable scope is closed under the strict parser and barrier.

| Gate | Target | Rows Repaired | Full Executable Result |
|---|---|---:|---|
| v22 | `source_path_identity_binding` | 5 | 836 commit, 11 abstain, 0 unsafe |
| v24 | quoted literal export path via `literal_intent_binding` | 2 | 838 commit, 9 abstain, 0 unsafe |
| v26 | `ordered_note_title_identity_binding` | 2 | 840 commit, 7 abstain, 0 unsafe |
| v28 | prior-effect playlist `create_playlist.playlist_id` | 7 | 847 commit, 0 abstain, 0 unsafe |

Research interpretation: after v20 exposed typed residual classes, each remaining class admitted a deterministic proof-frontier repair with adversarial uniqueness checks. The strongest opened executable result is now v28: all 847 executable opened rows commit under the strict barrier with 0 unsafe. The model-in-the-loop claim remains separate: v16b/v19 show primitive selection under an unchanged compiler/MetaVerifier, while v21-v28 provide the deterministic target frontier that the next RepairAgent model gates should learn to select.

## v29/v29b Frontier RepairAgent Selection

The v29 CPU structured policy is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v29_frontier_closure_repair_policy/REPORT.md`. It converts the v21-v28 deterministic closure into four typed residual packets and primitive selections.

The first GPU model run is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v29_frontier_selection/REPORT.md` and evaluated at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29_frontier_selection_model/REPORT.md`:

```text
processed: 4
parse_rate: 0.750
accepted: 3/4
miss: source-path identity used parser_policy.strict_json_no_regex_repair instead of parser_policy.strict
```

The targeted v29b retry is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v29b_frontier_selection_merged/REPORT.md`:

```text
processed: 4
parse_rate: 1.000
compile_rate: 1.000
accepted: 4/4
```

Research interpretation: v29b is the model-in-the-loop RepairAgent result for the full post-v20 residual closure. The model does not generate patch JSON; it selects primitive IDs from a fixed library. The deterministic compiler and unchanged MetaVerifier accept all four frontier repairs after a single slot-completeness retry, matching the earlier v16b pattern but now over four residual families.

## v30 Test-Time Compute Freeze

The test-time compute protocol is now frozen at `specs/recurrent_parallel_ebw_test_time_compute_v1.md`, with artifact hashes recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_freeze/FREEZE.md`.

The v30 retrospective replay is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v30_test_time_compute_replay/REPLAY.md`:

```text
round0 no repair: 831 commit, 16 abstain, 0 unsafe
round1 parallel v29b repair: 847 commit, 0 abstain, 0 unsafe
repair model calls: 5
```

Research interpretation: this starts the test-time-compute line by freezing the allowed actions and replaying the loop mechanics. It is not a held-out result, because the proof frontiers were discovered on opened data. The actual TTC claim requires a prospective held-out split after this freeze.

## v31-v33 Prospective Held-Out TTC

The prospective held-out TTC stage starts after the v30 freeze.

| Stage | Scope | Result |
|---|---|---|
| v31 | value-free held-out instance preflight | 24 fresh tasks, 169 target field instances |
| v32 | held-out no-repair proof-agent baseline | 65 executable rows, 62 commit, 3 abstain, 0 unsafe |
| v33 | frozen RepairAgent primitive selection + MetaVerifier | 1 residual packet, 1 model repair call, 65 commit, 0 abstain, 0 unsafe |

The v33 residual packet is `literal_export_path_binding_missing`: the three held-out abstains are Spotify CSV `create_file.file_path` rows where the file path is a quoted task literal. Qwen selects the frozen primitives `span_source.quoted_task_path_exact`, `target_arg.file_path`, and `parser_policy.strict`; the held-out MetaVerifier accepts all 3 target rows, and CPU rescore closes the held-out executable subset.

Research interpretation: unlike v30, v31-v33 are prospective held-out evidence under the frozen protocol. It is still a narrow held-out slice and needs the required baselines, but it directly addresses the test-time-compute concern: extra RepairAgent compute after an initial proof-agent pass converts safe abstentions into safe commits without changing the proof library.

## v34 Held-Out Best-of-N No-Repair Control

The v34 control is recorded at `results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v34_heldout_best_of_n_no_repair/REPORT.md`.

It reruns only the three v32 held-out abstain rows with eight sampled proof sketches per row and no RepairAgent. Result:

```text
target_rows: 3
samples_per_row: 8
sample_decision_counts: 24 abstain_no_valid
row_decision_counts: 3 abstain_no_valid
sample_parse_rate: 0.125
unsafe_unique_wrong: 0
```

Research interpretation: v34 is the first held-out negative control for the TTC claim. Extra proof-sketch sampling alone does not recover the literal export path residuals; v33 succeeds because the residual is converted into a frozen primitive-selection repair accepted by MetaVerifier.

## Multi-Agent Interpretation

This remains a multi-agent/free-lunch result if we keep the division of labor clean:

- agents propose proof sketches for different obligations in parallel;
- deterministic frontiers constrain the variables each role may bind;
- the barrier commits only under unique proof validity;
- recurrence updates the proof grammar/frontier after typed failure classes, not after vague model uncertainty.

The free lunch is not that more agents vote better. It is that parallel agents can search distinct proof obligations while a deterministic proof barrier prevents unsafe writes and converts failures into typed recurrent state.
