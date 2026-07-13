"""Develop exclusive causal provenance from public AppWorld tier summaries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from experiments.appworld_exclusive_provenance import exclusive_choice_from_tiers

REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def metric(rows: list[dict[str, Any]], choice_key: str) -> dict[str, float | int]:
    covered = [row for row in rows if row[choice_key] is not None]
    correct = sum(row[choice_key] == row["preferred"] for row in covered)
    return {
        "coverage": len(covered) / len(rows) if rows else 0.0,
        "covered": len(covered),
        "correct": correct,
        "wrong": len(covered) - correct,
        "accuracy": correct / len(covered) if covered else 0.0,
    }


def evaluate(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, float | int]]:
    output = []
    for row in rows:
        choice = exclusive_choice_from_tiers(row["typed_tier_A"], row["typed_tier_B"])
        output.append(
            {
                "pair_id": row["pair_id"],
                "task_id": row["task_id"],
                "task_type": row.get("task_type") or row.get("generator_id"),
                "preferred": row["preferred"],
                "tier_A": row["typed_tier_A"],
                "tier_B": row["typed_tier_B"],
                "typed_choice": row["typed_choice"],
                "exclusive_choice": choice,
                "exclusive_covered": choice is not None,
                "exclusive_correct": choice == row["preferred"] if choice else None,
            }
        )
    return output, metric(output, "exclusive_choice")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("specs/recurrent_parallel_appworld_exclusive_provenance_development_v1.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/recurrent_parallel_appworld_exclusive_provenance_development_v1"),
    )
    args = parser.parse_args()
    contract_path = resolve(args.contract)
    contract = load_json(contract_path)
    generated_path = resolve(contract["generated_results"])
    generated_binding_path = resolve(contract["generated_binding"])
    certification_path = resolve(contract["generated_certification"])
    historical_path = resolve(contract["historical_results"])
    generated = load_json(generated_path)
    generated_binding = load_json(generated_binding_path)
    certification = load_json(certification_path)
    historical = load_json(historical_path)

    generated_rows, generated_exclusive = evaluate(generated["rows"])
    historical_rows, historical_exclusive = evaluate(historical["rows"])
    d0 = (
        generated["status"] == contract["generated_required_status"]
        and certification["status"]
        == "RPD_APPWORLD_GENERATED_TYPED_PROVENANCE_V6_RESULT_CERTIFIED"
        and certification["results_sha256"] == file_hash(generated_path)
        and generated_binding["results_sha256"] == file_hash(generated_path)
    )
    gates = {
        "D0_certified_inputs": d0,
        "D1_generated_coverage": generated_exclusive["coverage"] >= 0.50,
        "D2_generated_safety": generated_exclusive["wrong"] == 0,
        "D3_no_correct_commit_loss": generated_exclusive["correct"]
        >= generated["typed_guard"]["correct"],
        "D4_historical_safety": historical_exclusive["wrong"] == 0,
        "D5_scope": (
            contract["confirmation_outcomes_sealed"] is True
            and contract["model_gpu_docker_used"] is False
            and contract["external_process_actions"] is False
            and all(len(row) == 10 for row in generated_rows + historical_rows)
        ),
    }
    if not gates["D0_certified_inputs"] or not gates["D5_scope"]:
        status = contract["verdicts"]["protocol_fail"]
    elif all(gates.values()):
        status = contract["verdicts"]["go"]
    else:
        status = contract["verdicts"]["no_go"]

    output_dir = resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    payload = {
        "schema": "recurrent_appworld_exclusive_provenance_development_v1",
        "status": status,
        "phase": contract["phase"],
        "rule": contract["rule"],
        "gates": gates,
        "generated": {
            "pairs": len(generated_rows),
            "typed_max_tier": generated["typed_guard"],
            "exclusive": generated_exclusive,
            "rows": generated_rows,
        },
        "historical": {
            "pairs": len(historical_rows),
            "typed_max_tier": historical["typed_guard"],
            "exclusive": historical_exclusive,
            "rows": historical_rows,
        },
        "hashes": {
            "contract": file_hash(contract_path),
            "source": file_hash(Path(__file__)),
            "rule_source": file_hash(resolve("experiments/appworld_exclusive_provenance.py")),
            "generated_input": file_hash(generated_path),
            "historical_input": file_hash(historical_path),
        },
        "confirmation_outcomes_sealed": True,
        "model_gpu_docker_used": False,
        "external_process_actions": False,
        "headline_eligible": False,
    }
    result_path = output_dir / "results.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (output_dir / "result_binding.json").write_text(
        json.dumps(
            {
                "results_sha256": file_hash(result_path),
                "generated_input_sha256": file_hash(generated_path),
                "historical_input_sha256": file_hash(historical_path),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    report = [
        "# AppWorld Exclusive Causal Provenance — Development",
        "",
        f"## Verdict: **`{status}`**",
        "",
        "| Dataset | Guard | Coverage | Correct commits | Wrong commits | Accuracy |",
        "|---|---|---:|---:|---:|---:|",
        f"| Generated development | Typed max-tier | {generated['typed_guard']['coverage']:.3f} | {generated['typed_guard']['correct']} | {generated['typed_guard']['wrong']} | {generated['typed_guard']['accuracy']:.3f} |",
        f"| Generated development | Exclusive | {generated_exclusive['coverage']:.3f} | {generated_exclusive['correct']} | {generated_exclusive['wrong']} | {generated_exclusive['accuracy']:.3f} |",
        f"| Historical development | Typed max-tier | {historical['typed_guard']['coverage']:.3f} | {historical['typed_guard']['correct']} | {historical['typed_guard']['wrong']} | {historical['typed_guard']['accuracy']:.3f} |",
        f"| Historical development | Exclusive | {historical_exclusive['coverage']:.3f} | {historical_exclusive['correct']} | {historical_exclusive['wrong']} | {historical_exclusive['accuracy']:.3f} |",
        "",
        "## Gates",
        "",
    ]
    report.extend(
        f"- `{name}`: **{'PASS' if value else 'FAIL'}**" for name, value in gates.items()
    )
    report.extend(
        [
            "",
            "This is post-NO_GO method development on already opened data. Confirmation",
            "remains sealed; this result only authorizes a pre-outcome confirmation freeze.",
        ]
    )
    (output_dir / "REPORT.md").write_text("\n".join(report) + "\n")
    print(
        json.dumps(
            {
                "status": status,
                "generated": generated_exclusive,
                "historical": historical_exclusive,
            }
        )
    )


if __name__ == "__main__":
    main()
