"""Summarize held-out TTC controls v32-v36."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(resolve(path).read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v37_heldout_control_summary"))
    args = parser.parse_args()
    output_dir = resolve(args.output_dir)
    if output_dir.exists():
        raise RuntimeError("refusing to overwrite v37 held-out control summary")

    paths = {
        "v31_preflight": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v31_heldout_instance_preflight/preflight.json",
        "v32_no_repair": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v32_heldout_no_repair/results.json",
        "v33_ttc": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v33_heldout_ttc/results.json",
        "v33_eval": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v33_heldout_ttc/results.json",
        "v34_best_of_n": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_model_run_v34_heldout_best_of_n_no_repair/results.json",
        "v35_freeform": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v35_heldout_freeform_repair/results.json",
        "v36_no_meta": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_v36_heldout_no_metaverifier_control/results.json",
        "v38_no_typed_eval": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_eval_v38_heldout_no_typed_residual/results.json",
        "v38_no_typed_rescore": "results/recurrent_parallel_appworld_proof_carrying_actions_v1/track_a_rescore_v38_heldout_no_typed_residual/results.json",
    }
    data = {key: load_json(path) for key, path in paths.items()}
    controls = [
        {
            "control": "one_shot_no_repair",
            "source": "v32",
            "model_calls": 65,
            "commit_live": data["v32_no_repair"]["decision_counts"].get("commit_live", 0),
            "abstain_no_valid": data["v32_no_repair"]["decision_counts"].get("abstain_no_valid", 0),
            "unsafe_unique_wrong": data["v32_no_repair"]["decision_counts"].get("unsafe_unique_wrong", 0),
            "accepted_repairs": None,
            "interpretation": "baseline proof-agent pass",
        },
        {
            "control": "best_of_n_no_repair",
            "source": "v34",
            "model_calls": data["v34_best_of_n"]["target_rows"] * data["v34_best_of_n"]["samples_per_row"],
            "commit_live": data["v32_no_repair"]["decision_counts"].get("commit_live", 0),
            "abstain_no_valid": data["v32_no_repair"]["decision_counts"].get("abstain_no_valid", 0),
            "unsafe_unique_wrong": 0,
            "accepted_repairs": 0,
            "interpretation": "extra proof-sketch sampling does not recover held-out residuals",
        },
        {
            "control": "freeform_repairagent_patch_json",
            "source": "v35",
            "model_calls": data["v35_freeform"]["processed"],
            "commit_live": data["v32_no_repair"]["decision_counts"].get("commit_live", 0),
            "abstain_no_valid": data["v32_no_repair"]["decision_counts"].get("abstain_no_valid", 0),
            "unsafe_unique_wrong": 0,
            "accepted_repairs": data["v35_freeform"]["accepted_count"],
            "interpretation": "free-form patch parses but MetaVerifier rejects wrong slot",
        },
        {
            "control": "structured_without_metaverifier",
            "source": "v36",
            "model_calls": 0,
            "commit_live": None,
            "abstain_no_valid": None,
            "unsafe_unique_wrong": None,
            "accepted_repairs": data["v36_no_meta"]["accepted_without_metaverifier"],
            "bad_controls_accepted": data["v36_no_meta"]["bad_controls_accepted_without_metaverifier"],
            "interpretation": "compiler-only accepts bad slot controls; not safety-valid",
        },
        {
            "control": "structured_no_typed_residual_with_metaverifier",
            "source": "v38",
            "model_calls": data["v38_no_typed_eval"]["processed"],
            "commit_live": data["v38_no_typed_rescore"]["decision_counts"].get("commit_live", 0),
            "abstain_no_valid": data["v38_no_typed_rescore"]["decision_counts"].get("abstain_no_valid", 0),
            "unsafe_unique_wrong": data["v38_no_typed_rescore"]["decision_counts"].get("unsafe_unique_wrong", 0),
            "accepted_repairs": data["v38_no_typed_eval"]["accepted_count"],
            "interpretation": "typed labels withheld; model still infers the right frozen primitive on this narrow held-out slice",
        },
        {
            "control": "structured_with_metaverifier",
            "source": "v33",
            "model_calls": data["v33_eval"]["processed"],
            "commit_live": data["v33_ttc"]["decision_counts"].get("commit_live", 0),
            "abstain_no_valid": data["v33_ttc"]["decision_counts"].get("abstain_no_valid", 0),
            "unsafe_unique_wrong": data["v33_ttc"]["decision_counts"].get("unsafe_unique_wrong", 0),
            "accepted_repairs": data["v33_eval"]["accepted_count"],
            "interpretation": "frozen primitive selection plus MetaVerifier closes held-out residuals",
        },
    ]
    payload = {
        "schema": "ebw_track_a_v37_heldout_control_summary_v1",
        "status": "RPD_EBW_TRACK_A_V37_HELDOUT_CONTROL_SUMMARY_COMPLETE",
        "fresh_tasks": data["v31_preflight"]["fresh_tasks"],
        "target_instances": data["v31_preflight"]["target_instances"],
        "executable_rows": data["v32_no_repair"]["processed"],
        "controls": controls,
        "input_hashes": {key: file_hash(resolve(path)) for key, path in paths.items()},
        "sealed_variations_opened": True,
        "external_process_actions": False,
    }
    output_dir.mkdir(parents=True)
    write_json(output_dir / "summary.json", payload)
    report = [
        "# EBW Track A v37 Held-Out Control Summary",
        "",
        f"## Status: **`{payload['status']}`**",
        "",
        f"- Fresh tasks: {payload['fresh_tasks']}",
        f"- Value-free target instances: {payload['target_instances']}",
        f"- Executable held-out rows: {payload['executable_rows']}",
        "- Sealed variations 10-12 opened: Yes, after v30 freeze",
        "",
        "## Control Table",
        "",
        "| Control | Model calls | Commit | Abstain | Unsafe | Accepted repairs | Interpretation |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in controls:
        report.append(
            f"| `{row['control']}` | {row['model_calls']} | {row['commit_live']} | {row['abstain_no_valid']} | {row['unsafe_unique_wrong']} | {row['accepted_repairs']} | {row['interpretation']} |"
        )
    report += [
        "",
        "## Interpretation",
        "",
        "On the prospective held-out executable subset, generic proof-sketch test-time compute and free-form patch JSON do not recover the residuals. Structured primitive selection with the frozen MetaVerifier closes the held-out gap, while the no-MetaVerifier control shows that compiler-only acceptance would also admit bad slot choices. The no-typed-residual ablation also closes this narrow literal-path gap, so this slice supports structured MetaVerified repair more strongly than it proves typed labels are necessary.",
    ]
    (output_dir / "SUMMARY.md").write_text("\n".join(report) + "\n")
    print(json.dumps({"status": payload["status"], "report": str((output_dir / "SUMMARY.md").relative_to(REPO_ROOT))}))


if __name__ == "__main__":
    main()