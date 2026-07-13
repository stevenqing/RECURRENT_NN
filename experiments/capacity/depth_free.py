"""E1: LIFO restore-depth gate replay on oracle or controller decisions."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import torch

from controller.controller_head import Action, ControllerDecision, ControllerHead
from controller.verifier_head import VerifierHead
from experiments.capacity.common import RAW_ROOT, default_depths, experiment_payload, instantiate_operator, parse_int_csv, predicted_d_star, resolve_device, write_json
from experiments.capacity.gate import operator_restore_gate, register_pop_exact
from register.structured import StructuredRegister
from tasks.graph_coloring.generator import GraphColoringInstance, generate_graph_coloring
from tasks.oracle.dpll_oracle import DPLLOracle, TraceAction, TraceStep


MAX_LOCAL_GENERATOR_TARGET_DEPTH = 12
KNOWN_BACKTRACK_EDGES = [
    (0, 1), (0, 4), (0, 6), (1, 3), (2, 6), (3, 8), (3, 10),
    (3, 11), (4, 5), (4, 6), (5, 6), (5, 7), (5, 9), (8, 9),
    (8, 11), (9, 10), (9, 11),
]


def _known_backtrack_fixture() -> GraphColoringInstance:
    constraints = [((u, v), lambda values: values[0] != values[1]) for u, v in KNOWN_BACKTRACK_EDGES]
    trace = DPLLOracle().solve(
        list(range(12)),
        {variable: {1, 2, 3} for variable in range(12)},
        constraints,
    )
    if not trace.solved or trace.total_backtracks < 30:
        raise RuntimeError("known E1 fixture no longer supplies at least 30 genuine backtracks")
    return GraphColoringInstance(12, 3, list(KNOWN_BACKTRACK_EDGES), trace.max_backtrack_depth, trace)


def _task_givens(task: GraphColoringInstance) -> dict[str, Any]:
    return {"n": task.n, "k": task.k, "edges": task.edges}


def _decision_from_trace(step: TraceStep) -> tuple[Action, int | None, int | None]:
    if step.action == TraceAction.PROPAGATE:
        return Action.PROPAGATE, step.variable, step.value
    if step.action == TraceAction.BRANCH:
        return Action.BRANCH, step.variable, step.value
    if step.action == TraceAction.BACKTRACK:
        return Action.REVERT, step.variable, step.value
    if step.action == TraceAction.CONTRADICTION:
        return Action.PROPAGATE, None, None
    if step.action == TraceAction.SOLVED:
        return Action.DONE, step.variable, step.value
    raise ValueError(f"unknown trace action: {step.action}")


def _controller_decision(controller: ControllerHead, hidden: torch.Tensor, register: StructuredRegister, h: torch.Tensor, verifier: Any) -> tuple[Action, int | None, int | None]:
    dead_end = verifier(hidden) if verifier is not None else None
    decision: ControllerDecision = controller(hidden, register.read(h), dead_end)
    return decision.action, int(decision.var_logits.argmax().item()), int(decision.val_logits.argmax().item()) + 1


def _replay_task(operator: Any, controller: ControllerHead, verifier: Any, register: StructuredRegister, task: GraphColoringInstance, decision: str, arm: str) -> list[dict[str, Any]]:
    device = next(controller.parameters()).device
    givens = _task_givens(task)
    h = register.init_state(1, device)
    partial: dict[int, int] = {}
    branch_stack: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for step_index, trace_step in enumerate(task.oracle_trace.steps):
        if trace_step.action == TraceAction.CONTRADICTION:
            continue
        op = operator.forward_step("graph_coloring", givens, partial)
        hidden = op.hidden_state.to(device).detach()
        if decision == "oracle":
            action, var, val = _decision_from_trace(trace_step)
        elif decision == "learned":
            action, var, val = _controller_decision(controller, hidden, register, h, verifier)
        else:
            raise ValueError("decision must be oracle or learned")

        if action == Action.PROPAGATE and var is not None and val is not None:
            partial[int(var)] = int(val)
            continue
        if action == Action.BRANCH and var is not None and val is not None:
            saved = {
                "var": int(var),
                "val": int(val),
                "partial": dict(partial),
                "hidden": hidden.detach(),
                "past_key_values": getattr(op, "past_key_values", None),
                "feed_token_id": int(op.logits.argmax(dim=-1)[0].item()) if getattr(op, "logits", None) is not None else None,
            }
            branch_stack.append(saved)
            if arm == "register":
                h = register.push(h, hidden, len(branch_stack) - 1)
            partial[int(var)] = int(val)
            continue
        if action == Action.REVERT:
            if arm == "no_revert" or not branch_stack:
                raw.append({"step": step_index, "depth": len(branch_stack), "arm": arm, "gate_status": "skipped_no_revert_or_empty_stack", "bit_exact": False, "max_abs_err": None})
                continue
            saved = branch_stack.pop()
            if arm == "register":
                h = register.pop(h, saved["hidden"], len(branch_stack))
                if saved["past_key_values"] is not None and saved["feed_token_id"] is not None:
                    restored_state = {"past_key_values": saved["past_key_values"], "feed_token_id": saved["feed_token_id"]}
                else:
                    restored_state = {"hidden_state": saved["hidden"]}
            elif arm == "in_context":
                restored = operator.forward_step("graph_coloring", givens, saved["partial"])
                if getattr(restored, "past_key_values", None) is not None and getattr(restored, "logits", None) is not None:
                    restored_state = {"past_key_values": restored.past_key_values, "feed_token_id": int(restored.logits.argmax(dim=-1)[0].item())}
                else:
                    restored_state = {"hidden_state": restored.hidden_state.detach()}
            else:
                raise ValueError("arm must be register, in_context, or no_revert")
            partial = dict(saved["partial"])
            gate = operator_restore_gate(operator, {"task_type": "graph_coloring"}, givens, saved["partial"], restored_state)
            raw.append({
                "step": step_index,
                "depth": len(branch_stack) + 1,
                "arm": arm,
                "decision": decision,
                **gate,
            })
            continue
        if action == Action.DONE:
            break
    return raw


def _instances_for_depth(L: int, K: int, instances: int, seed: int) -> list[GraphColoringInstance]:
    if L > MAX_LOCAL_GENERATOR_TARGET_DEPTH:
        return []
    if K == 3:
        fixture = _known_backtrack_fixture()
        if fixture.dpll_backtrack_depth >= L:
            return [fixture]
    n = max(8, min(max(L + 2, K + 2), 64))
    selected: list[GraphColoringInstance] = []
    seen: set[tuple[tuple[int, int], ...]] = set()
    for offset in range(50):
        candidates = generate_graph_coloring(n=n, k=K, edge_prob=0.35, target_depth=None, n_instances=max(20, instances * 20), seed=seed + offset)
        for task in candidates:
            key = tuple(task.edges)
            if key in seen:
                continue
            seen.add(key)
            has_revert = any(step.action == TraceAction.BACKTRACK for step in task.oracle_trace.steps)
            if task.dpll_backtrack_depth >= L and task.oracle_trace.total_backtracks > 0 and has_revert:
                selected.append(task)
                if len(selected) >= instances:
                    return selected
    return selected


def run_depth_free(operator, controller, verifier, D, K, depths, decision="oracle", arm="register", instances=50, seed=0, min_reverts: int = 30) -> list[dict]:
    """Run E1 replay rows for depth-free bit-exactness."""
    rows: list[dict[str, Any]] = []
    for L in [int(depth) for depth in depths]:
        tasks = _instances_for_depth(L, int(K), int(instances), int(seed) + L)
        register = StructuredRegister(dim=int(D), hidden_dim=int(getattr(operator, "hidden_size", D))).to(next(controller.parameters()).device) if tasks else None
        reg_exact, reg_err = register_pop_exact(
            StructuredRegister(
                dim=int(D),
                hidden_dim=int(getattr(operator, "hidden_size", D)),
                max_keys=max(1024, int(L) + 1),
            ),
            int(D),
            int(K),
            int(L),
        )
        raw_rows: list[dict[str, Any]] = []
        for task in tasks:
            if register is None:
                raise RuntimeError("missing register for non-empty E1 task set")
            raw_rows.extend(_replay_task(operator, controller, verifier, register, task, decision, arm))
        measured = [row for row in raw_rows if row["gate_status"] == "measured"]
        decision_agreement = sum(float(row["decision_agreement"]) for row in measured) / max(len(measured), 1)
        within_noise_rate = sum(int(row["within_noise_floor"]) for row in measured) / max(len(measured), 1)
        max_divergences = [float(row["resume_divergence"]["max_abs"]) for row in measured if row.get("resume_divergence", {}).get("max_abs") is not None]
        mean_divergences = [float(row["resume_divergence"]["mean_abs"]) for row in measured if row.get("resume_divergence", {}).get("mean_abs") is not None]
        if measured and len(measured) >= int(min_reverts):
            status = "measured"
        elif measured:
            status = "insufficient_reverts_for_gate"
        elif L > MAX_LOCAL_GENERATOR_TARGET_DEPTH:
            status = "target_depth_above_local_generator_guard"
        else:
            status = "no_supported_gate_measurements"
        rows.append({
            "L": L,
            "arm": arm,
            "decision": decision,
            "D": int(D),
            "K": int(K),
            "d_star": predicted_d_star(int(D), int(K)),
            "requested_instances": int(instances),
            "found_instances": len(tasks),
            "n_reverts": len(raw_rows),
            "n_measured_reverts": len(measured),
            "min_reverts": int(min_reverts),
            "register_pop_exact": bool(reg_exact),
            "register_pop_max_abs_err": reg_err,
            "decision_agreement": decision_agreement if measured else None,
            "within_noise_floor_rate": within_noise_rate if measured else None,
            "resume_divergence_max_abs": max(max_divergences) if max_divergences else None,
            "resume_divergence_mean_abs": sum(mean_divergences) / len(mean_divergences) if mean_divergences else None,
            "status": status,
            "raw": raw_rows,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E1 depth-free LIFO restore replay.")
    parser.add_argument("--D", type=int, default=2560)
    parser.add_argument("--K", type=int, default=9)
    parser.add_argument("--depths", default="")
    parser.add_argument("--decision", choices=["oracle", "learned"], default="oracle")
    parser.add_argument("--arm", choices=["register", "in_context", "no_revert"], default="register")
    parser.add_argument("--instances", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--no-load-model", action="store_true")
    parser.add_argument("--min-reverts", type=int, default=30)
    parser.add_argument("--out", default="results/capacity/E1_depth_free.json")
    args = parser.parse_args()
    device = resolve_device(args.device)
    operator = instantiate_operator(args.model, device, args.dtype, load_model=not args.no_load_model)
    hidden_dim = int(getattr(operator, "hidden_size", args.D))
    controller = ControllerHead(hidden_dim=hidden_dim, max_vars=max(81, args.K * 8), max_vals=max(9, args.K)).to(device)
    verifier = VerifierHead(hidden_dim=hidden_dim).to(device)
    depths = parse_int_csv(args.depths) if args.depths else default_depths(args.D, args.K)
    rows = run_depth_free(operator, controller, verifier, args.D, args.K, depths, args.decision, args.arm, args.instances, args.seed, min_reverts=args.min_reverts)
    raw_rows = [item for row in rows for item in row.pop("raw", [])]
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    raw_name = f"{Path(args.out).stem}_raw.json"
    write_json(RAW_ROOT / raw_name, {"rows": raw_rows})
    payload = experiment_payload("E1", args.model, args.D, args.K, args.seed, args.instances, rows, args.dtype)
    operator_rows = [row for row in rows if row["status"] == "measured"]
    payload["G1_pass"] = bool(operator_rows) and all(
        bool(row["register_pop_exact"])
        and float(row["decision_agreement"]) == 1.0
        and float(row["within_noise_floor_rate"]) == 1.0
        for row in operator_rows
    ) and all(bool(row["register_pop_exact"]) for row in rows)
    write_json(args.out, payload)


if __name__ == "__main__":
    main()