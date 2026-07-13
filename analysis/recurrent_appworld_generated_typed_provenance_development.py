"""Evaluate frozen typed provenance on fresh AppWorld 0.2 development tasks."""
from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import os
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any

from experiments.appworld_live_trace import LiveTraceRecorder
from experiments.appworld_provenance import candidate_evidence, deterministic_choice
from experiments.appworld_trace_replay import ResolvedCall, TraceResolver, canonical, mutations_for
from experiments.appworld_typed_provenance import candidate_typed_evidence, typed_choice

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARD_SCHEMA = "recurrent_appworld_generated_typed_provenance_task_shard_v1"
RESULT_SCHEMA = "recurrent_appworld_generated_typed_provenance_development_v1"


class NullWriter:
    """Discard verbose protected runtime output without retaining it."""

    encoding = "utf-8"

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False


def resolve(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else REPO_ROOT / path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        digest.update(str(item.relative_to(path)).encode())
        digest.update(hashlib.sha256(item.read_bytes()).digest())
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def forbidden_keys(value: Any, forbidden: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in forbidden:
                found.add(str(key).lower())
            found.update(forbidden_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            found.update(forbidden_keys(child, forbidden))
    return found


def metric(rows: list[dict[str, Any]], prefix: str) -> dict[str, float | int]:
    covered = [row for row in rows if row[f"{prefix}_covered"]]
    correct = sum(bool(row[f"{prefix}_correct"]) for row in covered)
    return {
        "coverage": len(covered) / len(rows) if rows else 0.0,
        "covered": len(covered),
        "correct": correct,
        "wrong": len(covered) - correct,
        "accuracy": correct / len(covered) if covered else 0.0,
    }


def task_pair_hash(task_id: str, call_index: int, mutation_id: str) -> str:
    return text_hash(f"generated-typed-v1|{task_id}|{call_index}|{mutation_id}")


def task_progress(
    output_dir: Path,
    completed: int,
    total: int,
    pair_count: int,
    baseline_passes: int,
    state: str,
) -> None:
    write_json(
        output_dir / "progress.json",
        {
            "schema": "recurrent_appworld_generated_typed_provenance_progress_v1",
            "state": state,
            "completed_tasks": completed,
            "total_tasks": total,
            "strict_pairs_so_far": pair_count,
            "baseline_passes_so_far": baseline_passes,
            "confirmation_outcomes_sealed": True,
            "external_process_actions": False,
        },
    )
    (output_dir / "PROGRESS.md").write_text(
        "\n".join(
            [
                "# AppWorld Generated Typed-Provenance Development Progress",
                "",
                f"- State: **{state}**",
                f"- Completed tasks: {completed}/{total}",
                f"- Baseline passes: {baseline_passes}/{completed}",
                f"- Strict pairs so far: {pair_count}",
                "- Confirmation outcomes: Sealed",
                "- External process actions: No",
            ]
        )
        + "\n"
    )


def process_task(
    task_row: dict[str, Any],
    root: Path,
    contract: dict[str, Any],
    execution_lock_sha256: str,
) -> dict[str, Any]:
    from appworld import AppWorld

    task_id = task_row["task_id"]
    generator_id = task_row["generator_id"]
    variation = task_row["variation"]
    summary: dict[str, Any] = {
        "task_id": task_id,
        "generator_id": generator_id,
        "variation": variation,
        "baseline_pass": False,
        "live_calls": 0,
        "write_checkpoints": 0,
        "candidate_mutations": 0,
        "strict_mutations": 0,
        "selected_pairs": 0,
        "error_type": None,
        "error_sha256": None,
    }
    result_rows: list[dict[str, Any]] = []
    world = None
    try:
        sink = NullWriter()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            world = AppWorld(
                task_id=task_id,
                experiment_name=f"generated_typed_v1_{task_id}",
                ground_truth_mode="full",
                load_ground_truth=True,
                raise_on_failure=False,
                raise_on_unsafe_syntax=True,
                null_patch_unsafe_execution=True,
            )
            code = world.task.ground_truth.compiled_solution_code + "\nsolution(apis, requester)"
            with LiveTraceRecorder(world, f"generated_typed_{task_id}") as recorder:
                message = world.execute(code)
            tracker = world.evaluate()

        calls = list(recorder.calls)
        baseline_pass = "Execution failed" not in str(message) and bool(tracker.success)
        summary.update(
            {
                "baseline_pass": baseline_pass,
                "live_calls": len(calls),
                "write_checkpoints": sum(call.checkpoint_id is not None for call in calls),
            }
        )
        if not baseline_pass:
            return {
                "schema": SHARD_SCHEMA,
                "execution_lock_sha256": execution_lock_sha256,
                "task_tree_sha256": task_row["tree_sha256"],
                "summary": summary,
                "rows": result_rows,
            }

        resolver = TraceResolver()
        history_by_index: dict[int, list[dict[str, Any]]] = {}
        mutation_by_id = {}
        candidate_mutations = []
        for call in calls:
            if call.checkpoint_id is None:
                continue
            document = next(
                document
                for document in resolver.docs_for(call.app_name)
                if document["api_name"] == call.api_name
            )
            parameter_docs = {
                parameter["name"]: parameter for parameter in document.get("parameters", [])
            }
            resolved_call = ResolvedCall(
                call.index,
                call.method,
                call.app_name,
                call.api_name,
                canonical(call.arguments),
                canonical(parameter_docs),
            )
            history_by_index[call.index] = [
                {
                    "call_index": prior.index,
                    "app_name": prior.app_name,
                    "api_name": prior.api_name,
                    "method": prior.method,
                    "arguments": prior.arguments,
                    "response": prior.response,
                }
                for prior in calls[: call.index]
            ]
            for mutation in mutations_for(
                resolved_call, contract["mutation_protocol"]["max_mutations_per_call"]
            ):
                candidate_mutations.append(mutation)
                mutation_by_id[mutation.mutation_id] = mutation

        candidate_mutations = sorted(
            candidate_mutations, key=lambda mutation: mutation.mutation_id
        )[: contract["mutation_protocol"]["max_mutations_per_task"]]
        summary["candidate_mutations"] = len(candidate_mutations)

        strict_mutations: list[dict[str, Any]] = []
        for mutation in candidate_mutations:
            target = calls[mutation.call_index]
            action_succeeded = True
            suffix_succeeded = True
            final_pass = False
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                world.load_state(target.checkpoint_id)
                try:
                    world.requester.request(
                        target.app_name,
                        target.api_name,
                        raise_on_failure=True,
                        **mutation.arguments(),
                    )
                except Exception:
                    action_succeeded = False
                if action_succeeded:
                    for future in calls[target.index + 1 :]:
                        try:
                            world.requester.request(
                                future.app_name,
                                future.api_name,
                                raise_on_failure=True,
                                **future.arguments,
                            )
                        except Exception:
                            suffix_succeeded = False
                            break
                if action_succeeded and suffix_succeeded:
                    world._save_state(world.output_db_home_path_on_disk)
                    final_pass = bool(world.evaluate().success)
            if action_succeeded and suffix_succeeded and not final_pass:
                strict_mutations.append(
                    {
                        "call_index": mutation.call_index,
                        "mutation_id": mutation.mutation_id,
                    }
                )

        summary["strict_mutations"] = len(strict_mutations)
        best_by_call: dict[int, dict[str, Any]] = {}
        for row in strict_mutations:
            current = best_by_call.get(row["call_index"])
            if current is None or row["mutation_id"] < current["mutation_id"]:
                best_by_call[row["call_index"]] = row
        selected = sorted(
            best_by_call.values(),
            key=lambda row: task_pair_hash(task_id, row["call_index"], row["mutation_id"]),
        )[: contract["mutation_protocol"]["max_pairs_per_task"]]

        task_goal = world.task.instruction
        evidence_config = {
            "max_citations_per_field_candidate": 3,
            "max_dict_items": 8,
            "max_list_items": 3,
            "max_string_chars": 120,
        }
        for row in selected:
            target = calls[row["call_index"]]
            live_arguments = target.arguments
            dead_arguments = mutation_by_id[row["mutation_id"]].arguments()
            differing_fields = sorted(
                field
                for field in set(live_arguments) | set(dead_arguments)
                if live_arguments.get(field) != dead_arguments.get(field)
            )
            history = history_by_index[row["call_index"]]
            old_live = candidate_evidence(
                live_arguments,
                differing_fields,
                history,
                task_goal,
                evidence_config,
                3,
            )
            old_dead = candidate_evidence(
                dead_arguments,
                differing_fields,
                history,
                task_goal,
                evidence_config,
                3,
            )
            typed_live = candidate_typed_evidence(
                live_arguments, dead_arguments, history, task_goal
            )
            typed_dead = candidate_typed_evidence(
                dead_arguments, live_arguments, history, task_goal
            )
            pair_id = task_pair_hash(task_id, row["call_index"], row["mutation_id"])
            live_is_a = int(pair_id, 16) % 2 == 0
            old_a, old_b = (old_live, old_dead) if live_is_a else (old_dead, old_live)
            typed_a, typed_b = (
                (typed_live, typed_dead) if live_is_a else (typed_dead, typed_live)
            )
            preferred = "A" if live_is_a else "B"
            old_choice = deterministic_choice(old_a, old_b)
            new_choice = typed_choice(typed_a, typed_b)
            result_rows.append(
                {
                    "pair_id": pair_id,
                    "task_id": task_id,
                    "generator_id": generator_id,
                    "variation": variation,
                    "call_index": row["call_index"],
                    "mutation_id": row["mutation_id"],
                    "preferred": preferred,
                    "old_choice": old_choice,
                    "old_covered": old_choice is not None,
                    "old_correct": old_choice == preferred if old_choice else None,
                    "old_support_A": old_a["support_count"],
                    "old_support_B": old_b["support_count"],
                    "typed_choice": new_choice,
                    "typed_covered": new_choice is not None,
                    "typed_correct": new_choice == preferred if new_choice else None,
                    "typed_tier_A": typed_a["max_tier"],
                    "typed_tier_B": typed_b["max_tier"],
                }
            )
        summary["selected_pairs"] = len(result_rows)
    except Exception as error:
        summary["error_type"] = type(error).__name__
        summary["error_sha256"] = text_hash(str(error))
    finally:
        if world is not None:
            try:
                with contextlib.redirect_stdout(NullWriter()), contextlib.redirect_stderr(
                    NullWriter()
                ):
                    AppWorld.close_all()
            except Exception as error:
                if summary["error_type"] is None:
                    summary["error_type"] = type(error).__name__
                    summary["error_sha256"] = text_hash(str(error))
                    summary["baseline_pass"] = False
                    result_rows = []

    return {
        "schema": SHARD_SCHEMA,
        "execution_lock_sha256": execution_lock_sha256,
        "task_tree_sha256": task_row["tree_sha256"],
        "summary": summary,
        "rows": result_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path(
            "specs/recurrent_parallel_appworld_generated_typed_provenance_development_v1.json"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "results/recurrent_parallel_appworld_generated_typed_provenance_development_v1"
        ),
    )
    args = parser.parse_args()
    warnings.filterwarnings("ignore")

    contract_path = resolve(args.contract)
    output_dir = resolve(args.output_dir)
    lock_path = output_dir / "execution_lock.json"
    result_path = output_dir / "results.json"
    if result_path.exists():
        raise RuntimeError(f"Refusing to overwrite frozen results: {result_path}")
    contract = load_json(contract_path)
    execution_lock = load_json(lock_path)
    execution_lock_sha256 = file_hash(lock_path)

    immutable_checks = {
        path: resolve(path).is_file() and file_hash(resolve(path)) == expected_hash
        for path, expected_hash in execution_lock["immutable_inputs"].items()
    }
    source_root = resolve(contract["source_root"])
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source_root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    preflight_checks = {
        "execution_lock_status": execution_lock["status"]
        == "LOCKED_BEFORE_GENERATED_DEVELOPMENT_OUTCOMES",
        "immutable_inputs": all(immutable_checks.values()),
        "source_commit": source_commit == contract["source_commit"],
        "development_tasks": len(execution_lock["selected_tasks"])
        == contract["expected_open_tasks"],
        "development_variations": all(
            row["split"] == contract["open_split"]
            and row["variation"] in contract["open_variations"]
            for row in execution_lock["selected_tasks"]
        ),
        "confirmation_sealed": execution_lock["confirmation_outcomes_sealed"] is True,
        "results_absent": not result_path.exists(),
    }
    if not all(preflight_checks.values()):
        raise RuntimeError(preflight_checks)

    from appworld import update_root

    appworld_root = resolve(contract["appworld_root"])
    update_root(str(appworld_root))
    shard_dir = output_dir / "task_shards"
    shard_dir.mkdir(exist_ok=True)
    selected_tasks = sorted(execution_lock["selected_tasks"], key=lambda row: row["task_id"])
    shards: list[dict[str, Any]] = []
    started = time.time()
    for task_index, task_row in enumerate(selected_tasks, start=1):
        shard_path = shard_dir / f"{task_row['task_id']}.json"
        if shard_path.exists():
            shard = load_json(shard_path)
            valid_existing = (
                shard.get("schema") == SHARD_SCHEMA
                and shard.get("execution_lock_sha256") == execution_lock_sha256
                and shard.get("task_tree_sha256") == task_row["tree_sha256"]
                and shard.get("summary", {}).get("task_id") == task_row["task_id"]
            )
            if not valid_existing:
                raise RuntimeError(f"Invalid existing shard: {shard_path}")
        else:
            shard = process_task(task_row, appworld_root, contract, execution_lock_sha256)
            write_json(shard_path, shard)
        shards.append(shard)
        all_rows_so_far = [row for current in shards for row in current["rows"]]
        baseline_passes = sum(bool(current["summary"]["baseline_pass"]) for current in shards)
        task_progress(
            output_dir,
            task_index,
            len(selected_tasks),
            len(all_rows_so_far),
            baseline_passes,
            "RUNNING" if task_index < len(selected_tasks) else "AGGREGATING",
        )
        print(
            json.dumps(
                {
                    "completed": task_index,
                    "total": len(selected_tasks),
                    "task_id": task_row["task_id"],
                    "baseline_pass": shard["summary"]["baseline_pass"],
                    "selected_pairs": len(shard["rows"]),
                }
            ),
            flush=True,
        )

    task_summaries = [shard["summary"] for shard in shards]
    result_rows = sorted(
        [row for shard in shards for row in shard["rows"]], key=lambda row: row["pair_id"]
    )
    old_metrics = metric(result_rows, "old")
    typed_metrics = metric(result_rows, "typed")
    source_tasks = {row["task_id"] for row in result_rows}
    source_generators = {row["generator_id"] for row in result_rows}

    selected_hashes_match = all(
        (appworld_root / "data/tasks" / row["task_id"]).is_dir()
        and tree_hash(appworld_root / "data/tasks" / row["task_id"])
        == row["tree_sha256"]
        for row in selected_tasks
    )
    immutable_still_match = all(
        resolve(path).is_file() and file_hash(resolve(path)) == expected_hash
        for path, expected_hash in execution_lock["immutable_inputs"].items()
    )
    forbidden = {key.lower() for key in contract["output_forbidden_keys"]}
    scope_payload = {"task_summaries": task_summaries, "rows": result_rows}
    no_forbidden_output_keys = not forbidden_keys(scope_payload, forbidden)

    gates = {
        "T0_live_baselines": (
            len(task_summaries) == contract["expected_open_tasks"]
            and all(summary["baseline_pass"] for summary in task_summaries)
            and all(summary["error_type"] is None for summary in task_summaries)
        ),
        "T1_strict_yield": (
            len(result_rows) >= 20
            and len(source_tasks) >= 12
            and len(source_generators) >= 6
        ),
        "T2_typed_coverage": typed_metrics["coverage"] >= 0.50,
        "T3_typed_safety": (
            typed_metrics["accuracy"] >= 0.80 and typed_metrics["wrong"] == 0
        ),
        "T4_vs_old_safety": typed_metrics["wrong"] <= old_metrics["wrong"],
        "T5_hash_integrity": selected_hashes_match and immutable_still_match,
        "T6_scope": (
            all(
                row["variation"] in contract["open_variations"]
                and row["generator_id"]
                in execution_lock["selected_generator_ids"]
                for row in result_rows
            )
            and execution_lock["confirmation_outcomes_sealed"] is True
            and no_forbidden_output_keys
            and contract["model_gpu_docker_used"] is False
            and contract["external_process_actions"] is False
        ),
    }
    if not gates["T0_live_baselines"] or not gates["T5_hash_integrity"] or not gates["T6_scope"]:
        status = contract["verdicts"]["protocol_fail"]
    elif all(gates.values()):
        status = contract["verdicts"]["go"]
    else:
        status = contract["verdicts"]["no_go"]

    payload = {
        "schema": RESULT_SCHEMA,
        "status": status,
        "gates": gates,
        "source_tasks": len(source_tasks),
        "source_generators": len(source_generators),
        "strict_pairs": len(result_rows),
        "old_guard": old_metrics,
        "typed_guard": typed_metrics,
        "task_summaries": task_summaries,
        "rows": result_rows,
        "preflight_checks": preflight_checks,
        "execution_lock_sha256": execution_lock_sha256,
        "task_shard_sha256": {
            path.stem: file_hash(path) for path in sorted(shard_dir.glob("*.json"))
        },
        "seconds": time.time() - started,
        "development_variations": contract["open_variations"],
        "confirmation_outcomes_sealed": True,
        "protected_content_exported": False,
        "external_process_actions": False,
        "model_gpu_docker_used": False,
        "headline_eligible": False,
    }
    if forbidden_keys(payload, forbidden):
        raise RuntimeError("Forbidden protected keys reached the public result payload")
    write_json(result_path, payload)
    write_json(
        output_dir / "result_binding.json",
        {
            "execution_lock_sha256": execution_lock_sha256,
            "results_sha256": file_hash(result_path),
            "task_shard_sha256": payload["task_shard_sha256"],
        },
    )

    report_lines = [
        "# AppWorld 0.2 Generated Typed-Provenance Development",
        "",
        f"## Verdict: **`{status}`**",
        "",
        f"- Development tasks executed: {len(task_summaries)}/{contract['expected_open_tasks']}",
        f"- Strict pairs: {len(result_rows)}",
        f"- Source tasks: {len(source_tasks)}",
        f"- Source generators: {len(source_generators)}",
        "- Confirmation outcomes: Sealed",
        "- Protected content exported: No",
        "- External process actions: No",
        "- Model/GPU/Docker used: No",
        "",
        "| Guard | Coverage | Covered accuracy | Wrong choices |",
        "|---|---:|---:|---:|",
        f"| Old citation count | {old_metrics['coverage']:.3f} | {old_metrics['accuracy']:.3f} | {old_metrics['wrong']} |",
        f"| Typed max-tier | {typed_metrics['coverage']:.3f} | {typed_metrics['accuracy']:.3f} | {typed_metrics['wrong']} |",
        "",
        "## Gates",
        "",
    ]
    report_lines.extend(
        f"- `{gate}`: **{'PASS' if passed else 'FAIL'}**" for gate, passed in gates.items()
    )
    report_lines.extend(
        [
            "",
            "This opens only generated variations 4–6. It is method-development evidence,",
            "not confirmation and not a headline result.",
        ]
    )
    (output_dir / "REPORT.md").write_text("\n".join(report_lines) + "\n")
    task_progress(
        output_dir,
        len(selected_tasks),
        len(selected_tasks),
        len(result_rows),
        sum(bool(summary["baseline_pass"]) for summary in task_summaries),
        "COMPLETE",
    )
    print(
        json.dumps(
            {
                "status": status,
                "pairs": len(result_rows),
                "old": old_metrics,
                "typed": typed_metrics,
                "report": str((output_dir / "REPORT.md").relative_to(REPO_ROOT)),
            }
        )
    )


if __name__ == "__main__":
    main()
