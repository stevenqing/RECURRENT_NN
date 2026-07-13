# Broad Value-Bound Witness Preflight Handoff

## Status: **`RPD_APPWORLD_BROAD_VALUE_BOUND_WITNESS_PREFLIGHT_READY`**

This step expands the locked broad witness sketches into concrete opened-pool write-field instances without exporting argument values, response values, or value hashes.

## Completed

- Froze the value-bound witness instance preflight contract before verifier outcomes.
- Required the parent witness sketch preflight to be ready.
- Required the grammar-only template baseline to pass.
- Built a value-free instance manifest over the opened broad AppWorld pool.
- Identified 1266 target write-field instances across 70 tasks.
- Confirmed every target instance has at least one pre-write read.
- Preserved sealed fresh variations 10-12.
- Used no model, GPU, Docker, or external-process intervention.
- Made no action-correctness claim.

## Key Artifacts

- Contract: `specs/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1.json`
- Spec: `specs/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1.md`
- Runner: `analysis/appworld_broad_value_bound_witness_preflight.py`
- Preflight report: `results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1/PREFLIGHT.md`
- Preflight JSON: `results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1/preflight.json`
- Instance manifest: `results/recurrent_parallel_appworld_broad_value_bound_witness_preflight_v1/instance_manifest.json`

## Target Instances

| Proof family | Instances |
|---|---:|
| `state_transition_membership_proof` | 595 |
| `filesystem_path_derivation_proof` | 547 |
| `literal_text_derivation_proof` | 124 |

## Read Context

- Instances with no pre-write reads: 0
- Max pre-write reads before target: 290
- Max same-app pre-write reads before target: 290
- Same-app reads are missing for 67 filesystem path instances and 75 literal text instances, which is acceptable because those derivations can be cross-app.

## Output Boundary

The instance manifest includes task IDs, generator IDs, variations, call indices, schema fields, proof family, write ordinal, and pre-read counts. It does not include raw argument values, response values, protected task text, or value hashes.

## Interpretation

This is the first value-bound verifier setup step. It confirms there are enough opened broad instances with pre-write read context to attempt concrete verifier instantiation. It does not yet verify a candidate write argument.

## Next Required Step

Implement `value_bound_template_verifier_v1` over this instance manifest:

1. load each target instance internally from opened data;
2. instantiate a deterministic template proof using immutable pre-write reads;
3. evaluate the live candidate and an adversarial candidate;
4. report only aggregate commit/ambiguous/abstain counts and value-free row metadata;
5. fail closed if a wrong candidate obtains a unique valid witness.

Only after that should any LLM witness synthesis be considered.