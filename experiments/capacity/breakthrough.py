"""E3: independent full-D routing versus split-D controls."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import torch

from experiments.capacity.common import RAW_ROOT, experiment_payload, instantiate_operator, parse_int_csv, resolve_device, write_json
from experiments.capacity.encode import encode_branches, encode_prepared_values, prepare_values, read_branch
from experiments.capacity.stats import holm_bonferroni, mcnemar_exact
from experiments.capacity.width_wall import _sample_branch_states, load_state_shards, predicted_d_star


holm_correct = holm_bonferroni


def _chunks(W: int, N: int) -> list[range]:
    base = W // N
    remainder = W % N
    chunks = []
    start = 0
    for owner in range(N):
        size = base + (1 if owner < remainder else 0)
        chunks.append(range(start, start + size))
        start += size
    return chunks


def _project(states: torch.Tensor, D: int) -> torch.Tensor:
    if states.shape[-1] >= D:
        return states[..., :D]
    pad = torch.zeros(*states.shape[:-1], D - states.shape[-1], dtype=states.dtype)
    return torch.cat([states, pad], dim=-1)


def _routing_read(branch_states: torch.Tensor, D: int, N: int, index: int, seed: int, split: bool) -> tuple[int, int]:
    chunks = _chunks(int(branch_states.shape[0]), N)
    for owner, chunk in enumerate(chunks):
        if index in chunk:
            local_index = index - chunk.start
            dim = max(1, D // N) if split else D
            local_states = _project(branch_states[list(chunk)], dim)
            register = encode_branches(local_states, dim, seed + owner, encoder="bind", device="cpu")
            return chunk.start + read_branch(register, local_index), dim
    raise IndexError(index)


def _consensus_read(branch_states: torch.Tensor, D: int, N: int, index: int, seed: int) -> int:
    votes = []
    states = _project(branch_states, D)
    for replica in range(N):
        register = encode_branches(states, D, seed + 1009 * replica, encoder="bind", device="cpu")
        votes.append(read_branch(register, index))
    return Counter(votes).most_common(1)[0][0]


def run_breakthrough(
    operator,
    D,
    K,
    W,
    Ns,
    mode="routing",
    seed=0,
    batch_size: int = 1,
    instances: int = 50,
    branch_states: torch.Tensor | None = None,
    W_star_bind: int | None = None,
    single_reg_acc_at_W: float | None = None,
    regime: str | None = None,
) -> list[dict]:
    """Run E3' only beyond a measured D-regime bind wall."""
    if mode not in {"routing", "split", "consensus"}:
        raise ValueError("mode must be one of routing, split, consensus")
    if regime != "D":
        raise AssertionError("E3' only valid in the D-regime")
    if W_star_bind is None or int(W) <= int(W_star_bind):
        raise AssertionError("E3' requires W strictly above measured W*_bind")
    if single_reg_acc_at_W is None or float(single_reg_acc_at_W) + 1e-12 >= 0.9:
        raise AssertionError("E3' requires measured single-register accuracy below 0.9 at W")
    if branch_states is None:
        branch_states = _sample_branch_states(operator, int(D), int(K), int(W), int(seed), batch_size=batch_size)
    branch_states = _project(branch_states[: int(W)].detach().float().cpu(), int(D))
    if int(branch_states.shape[0]) < int(W):
        raise ValueError(f"W={W} exceeds available branch states {branch_states.shape[0]}")
    query_generator = torch.Generator(device="cpu").manual_seed(65537 + int(seed) + 104729 * int(W))
    queries = [int(item) for item in torch.randint(0, int(W), (int(instances),), generator=query_generator).tolist()]
    N_values = [int(item) for item in Ns]
    rows: list[dict[str, Any]] = []
    consensus_votes: list[list[int]] | None = None
    if mode == "consensus":
        prepared = prepare_values(branch_states, int(D), "bind")
        max_replicas = max(N_values)
        consensus_registers = [
            encode_prepared_values(prepared, int(D), int(seed) + 1009 * replica, device="cpu")
            for replica in range(max_replicas)
        ]
        consensus_votes = []
        for index in queries:
            votes = [read_branch(register, index) for register in consensus_registers]
            consensus_votes.append(votes)
    for N in N_values:
        correct = 0
        raw = []
        split_dim = max(1, int(D) // max(N, 1)) if mode == "split" else int(D)
        chunks = _chunks(int(W), N)
        prepared_by_owner: list[torch.Tensor] = []
        if mode in {"routing", "split"}:
            for chunk in chunks:
                local_states = _project(branch_states[list(chunk)], split_dim)
                prepared_by_owner.append(prepare_values(local_states, split_dim, "bind"))
            registers_by_owner = [
                encode_prepared_values(values, split_dim, int(seed) + owner, device="cpu")
                for owner, values in enumerate(prepared_by_owner)
            ]
        for trial, index in enumerate(queries):
            if mode == "routing":
                owner = next(owner for owner, chunk in enumerate(chunks) if index in chunk)
                local_index = index - chunks[owner].start
                register = registers_by_owner[owner]
                prediction = chunks[owner].start + read_branch(register, local_index)
                used_dim = split_dim
            elif mode == "split":
                owner = next(owner for owner, chunk in enumerate(chunks) if index in chunk)
                local_index = index - chunks[owner].start
                register = registers_by_owner[owner]
                prediction = chunks[owner].start + read_branch(register, local_index)
                used_dim = split_dim
            else:
                if consensus_votes is None:
                    raise RuntimeError("missing consensus votes")
                prediction = Counter(consensus_votes[trial][:N]).most_common(1)[0][0]
                used_dim = int(D)
            is_correct = prediction == index
            correct += int(is_correct)
            raw.append({"trial": trial, "N": N, "mode": mode, "query_index": index, "prediction": prediction, "correct": is_correct, "register_dim": used_dim})
        rows.append({
            "N": N,
            "mode": mode,
            "D": int(D),
            "K": int(K),
            "W": int(W),
            "W_star_bind": int(W_star_bind),
            "single_reg_acc_at_W": float(single_reg_acc_at_W),
            "regime": regime,
            "d_star": predicted_d_star(int(D), int(K)),
            "register_dim": split_dim,
            "read_accuracy": correct / max(int(instances), 1),
            "n_reads": int(instances),
            "raw": raw,
        })
    single_row = next((row for row in rows if int(row["N"]) == 1), None)
    if single_row is None or abs(float(single_row["read_accuracy"]) - float(single_reg_acc_at_W)) > 1e-12:
        raise AssertionError("E3' N=1 did not reproduce the paired E2' single-register measurement")
    return rows


def run_breakthrough_2x2(
    operator,
    D,
    K,
    W,
    Ns,
    preprocess,
    partition,
    seed,
    *,
    instances: int = 300,
    batch_size: int = 1,
    branch_states: torch.Tensor | None = None,
    regime: str | None = None,
    W_star_bind: int | None = None,
    single_register_acc_at_W: float | None = None,
) -> list[dict[str, Any]]:
    """Run one cell of the v4 partition × preprocessing factorial design."""
    if preprocess not in {"none", "whiten"}:
        raise ValueError("preprocess must be one of {'none', 'whiten'}")
    if partition not in {"routing", "split"}:
        raise ValueError("partition must be one of {'routing', 'split'}")
    if regime != "D":
        raise AssertionError("E3 double-prime only valid in the D-regime")
    if W_star_bind is None or int(W) <= int(W_star_bind):
        raise AssertionError("E3 double-prime requires W above measured W*_bind")
    if single_register_acc_at_W is None or float(single_register_acc_at_W) + 1e-12 >= 0.9:
        raise AssertionError("E3 double-prime requires a measured failing single-register width")
    if branch_states is None:
        branch_states = _sample_branch_states(operator, int(D), int(K), int(W), int(seed), batch_size=batch_size)
    branch_states = _project(branch_states[: int(W)].detach().float().cpu(), int(D))
    if int(branch_states.shape[0]) < int(W):
        raise ValueError(f"W={W} exceeds available branch states {branch_states.shape[0]}")
    query_generator = torch.Generator(device="cpu").manual_seed(65537 + int(seed) + 104729 * int(W))
    queries = [int(item) for item in torch.randint(0, int(W), (int(instances),), generator=query_generator).tolist()]
    encoder_name = "raw" if preprocess == "none" else "bind"
    rows: list[dict[str, Any]] = []
    for N in [int(item) for item in Ns]:
        chunks = _chunks(int(W), N)
        local_dim = int(D) if partition == "routing" else max(1, int(D) // max(N, 1))
        registers = []
        for owner, chunk in enumerate(chunks):
            local_states = _project(branch_states[list(chunk)], local_dim)
            values = prepare_values(local_states, local_dim, encoder_name)
            registers.append(encode_prepared_values(values, local_dim, int(seed) + owner, device="cpu"))
        correct = 0
        raw = []
        for trial, index in enumerate(queries):
            owner = next(owner for owner, chunk in enumerate(chunks) if index in chunk)
            local_index = index - chunks[owner].start
            prediction = chunks[owner].start + read_branch(registers[owner], local_index)
            is_correct = prediction == index
            correct += int(is_correct)
            raw.append({
                "trial": int(trial),
                "N": int(N),
                "W": int(W),
                "preprocess": preprocess,
                "partition": partition,
                "query_index": int(index),
                "prediction": int(prediction),
                "correct": bool(is_correct),
                "register_dim": int(local_dim),
            })
        rows.append({
            "N": int(N),
            "preprocess": preprocess,
            "partition": partition,
            "mode": f"{partition}_{preprocess}",
            "D": int(D),
            "K": int(K),
            "W": int(W),
            "W_star_bind": int(W_star_bind),
            "single_register_acc_at_W": float(single_register_acc_at_W),
            "regime": regime,
            "register_dim": int(local_dim),
            "read_accuracy": correct / max(int(instances), 1),
            "n_reads": int(instances),
            "raw": raw,
        })
    if preprocess == "whiten":
        single_row = next((row for row in rows if int(row["N"]) == 1), None)
        if single_row is None or abs(float(single_row["read_accuracy"]) - float(single_register_acc_at_W)) > 1e-12:
            raise AssertionError("whitened N=1 cell did not reproduce paired E2' accuracy")
    return rows


def _query_indices(load: int, count: int, seed: int) -> list[int]:
    generator = torch.Generator(device="cpu").manual_seed(65537 + int(seed) + 104729 * int(load))
    return [int(item) for item in torch.randint(0, int(load), (int(count),), generator=generator).tolist()]


def per_register_load_curve(
    operator,
    D,
    K,
    loads,
    seed,
    whiten=True,
    *,
    instances: int = 300,
    batch_size: int = 1,
    branch_states: torch.Tensor | None = None,
) -> dict[str, Any]:
    """Measure acc(load) for one full-D whitened register."""
    if whiten is not True:
        raise AssertionError("v5 per-register load curves require whitening")
    load_values = sorted(set(int(load) for load in loads))
    if not load_values or load_values[0] < 1:
        raise ValueError("loads must be positive")
    if branch_states is None:
        branch_states = _sample_branch_states(operator, int(D), int(K), max(load_values), int(seed), batch_size=batch_size)
    branch_states = _project(branch_states.detach().float().cpu(), int(D))
    if max(load_values) > int(branch_states.shape[0]):
        raise ValueError("load curve exceeds available branch states")
    curve = []
    all_raw = []
    for load in load_values:
        values = prepare_values(branch_states[:load], int(D), "bind")
        register = encode_prepared_values(values, int(D), int(seed), device="cpu")
        queries = _query_indices(load, int(instances), int(seed))
        correct = 0
        raw = []
        for trial, index in enumerate(queries):
            prediction = read_branch(register, index)
            is_correct = prediction == index
            correct += int(is_correct)
            raw.append({
                "trial": int(trial),
                "load": int(load),
                "query_index": int(index),
                "prediction": int(prediction),
                "correct": bool(is_correct),
            })
        curve.append({
            "load": int(load),
            "D": int(D),
            "K": int(K),
            "whiten": True,
            "read_accuracy": correct / max(int(instances), 1),
            "n_reads": int(instances),
        })
        all_raw.extend(raw)
    return {"curve": curve, "raw": all_raw}


def run_matched_load(
    operator,
    D,
    K,
    W,
    Ns,
    arm,
    seed,
    whiten=True,
    *,
    instances: int = 300,
    batch_size: int = 1,
    branch_states: torch.Tensor | None = None,
    regime: str | None = None,
    W_star_bind: int | None = None,
    single_register_acc_at_W: float | None = None,
) -> list[dict[str, Any]]:
    """Run v5 single, matched-load consensus, or full-D routing arms."""
    if arm not in {"single", "consensus", "routing"}:
        raise ValueError("arm must be one of {'single', 'consensus', 'routing'}")
    if whiten is not True:
        raise AssertionError("all v5 matched-load arms require whitening")
    if regime != "D":
        raise AssertionError("v5 matched-load tests require the D regime")
    if W_star_bind is None or int(W) <= int(W_star_bind):
        raise AssertionError("v5 matched-load tests require W above W*_bind")
    if single_register_acc_at_W is None or float(single_register_acc_at_W) + 1e-12 >= 0.9:
        raise AssertionError("v5 requires a failing single-register width")
    if branch_states is None:
        branch_states = _sample_branch_states(operator, int(D), int(K), int(W), int(seed), batch_size=batch_size)
    branch_states = _project(branch_states[: int(W)].detach().float().cpu(), int(D))
    if int(branch_states.shape[0]) < int(W):
        raise ValueError(f"W={W} exceeds available branch states {branch_states.shape[0]}")
    n_values = [int(item) for item in Ns]
    if arm == "single" and n_values != [1]:
        raise AssertionError("single arm is defined only at N=1")
    full_values = prepare_values(branch_states, int(D), "bind")
    max_n = max(n_values)
    full_registers = [
        encode_prepared_values(full_values, int(D), int(seed) + 1009 * replica, device="cpu")
        for replica in range(max_n)
    ] if arm in {"single", "consensus"} else []
    queries = _query_indices(int(W), int(instances), int(seed))
    rows: list[dict[str, Any]] = []
    for N in n_values:
        routing_chunks = _chunks(int(W), N) if arm == "routing" else []
        routing_registers = []
        if arm == "routing":
            for owner, chunk in enumerate(routing_chunks):
                local_values = prepare_values(branch_states[list(chunk)], int(D), "bind")
                routing_registers.append(encode_prepared_values(local_values, int(D), int(seed) + owner, device="cpu"))
        correct = 0
        raw = []
        for trial, index in enumerate(queries):
            if arm == "single":
                prediction = read_branch(full_registers[0], index)
                per_register_load = int(W)
            elif arm == "consensus":
                votes = [read_branch(register, index) for register in full_registers[:N]]
                prediction = Counter(votes).most_common(1)[0][0]
                per_register_load = int(W)
            else:
                owner = next(owner for owner, chunk in enumerate(routing_chunks) if index in chunk)
                local_index = index - routing_chunks[owner].start
                prediction = routing_chunks[owner].start + read_branch(routing_registers[owner], local_index)
                per_register_load = max(len(chunk) for chunk in routing_chunks)
            is_correct = prediction == index
            correct += int(is_correct)
            raw.append({
                "trial": int(trial),
                "arm": arm,
                "N": int(N),
                "W": int(W),
                "per_register_load": int(per_register_load),
                "query_index": int(index),
                "prediction": int(prediction),
                "correct": bool(is_correct),
            })
        rows.append({
            "arm": arm,
            "N": int(N),
            "D": int(D),
            "K": int(K),
            "W": int(W),
            "per_register_load": int(per_register_load),
            "whiten": True,
            "W_star_bind": int(W_star_bind),
            "single_register_acc_at_W": float(single_register_acc_at_W),
            "read_accuracy": correct / max(int(instances), 1),
            "n_reads": int(instances),
            "raw": raw,
        })
    if arm in {"single", "consensus"}:
        n1 = next((row for row in rows if int(row["N"]) == 1), None)
        if n1 is None or abs(float(n1["read_accuracy"]) - float(single_register_acc_at_W)) > 1e-12:
            raise AssertionError("matched-load N=1 did not reproduce the single-register measurement")
    return rows


def _gate_from_width_wall(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    encoder = payload.get("encoder")
    schema = payload.get("schema")
    if schema != "bind_capacity_curve_v3":
        return {
            "path": path,
            "schema": schema,
            "G2_prime_pass": False,
            "reason": "E3_prime_requires_bind_capacity_curve_v3",
            "rows": rows,
        }
    threshold = float(payload.get("threshold", 0.9))
    first_fail_W = payload.get("first_fail_W")
    first_fail_row = next((row for row in rows if first_fail_W is not None and int(row["W"]) == int(first_fail_W)), None)
    clean_rows = [{key: value for key, value in row.items() if key != "raw"} for row in rows]
    return {
        "path": path,
        "schema": schema,
        "G2_prime_pass": bool(payload.get("G2_prime_pass")) and encoder == "bind",
        "W_star_bind": int(payload.get("W_star_bind", 0)),
        "first_fail_W": int(first_fail_W) if first_fail_W is not None else None,
        "first_fail_accuracy": float(first_fail_row["read_accuracy"]) if first_fail_row is not None else None,
        "threshold": threshold,
        "regime": payload.get("regime"),
        "encoder": encoder,
        "rows": clean_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run E3 multi-agent routing versus split controls.")
    parser.add_argument("--D", type=int, default=2560)
    parser.add_argument("--K", type=int, default=9)
    parser.add_argument("--W", type=int, default=0)
    parser.add_argument("--Ns", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--mode", choices=["routing", "split", "consensus"], default="routing")
    parser.add_argument("--preprocess", choices=["none", "whiten"], default="")
    parser.add_argument("--partition", choices=["routing", "split"], default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", choices=["fp32", "bf16", "fp16"], default="fp32")
    parser.add_argument("--no-load-model", action="store_true")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--instances", type=int, default=50)
    parser.add_argument("--states-dir", default="")
    parser.add_argument("--width-wall-result", default="")
    parser.add_argument("--allow-ungated", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if args.allow_ungated:
        raise SystemExit("SPEC v3 removes ungated E3 runs; supply a passing E2' bind wall artifact")
    if not args.width_wall_result:
        raise SystemExit("E3' requires --width-wall-result from E2'")
    gate = _gate_from_width_wall(args.width_wall_result)
    if not gate.get("G2_prime_pass"):
        raise SystemExit(f"G2' failed or is not a v3 bind-wall artifact: {args.width_wall_result}")
    if gate.get("regime") != "D":
        raise SystemExit(f"E3' blocked: measured bind regime is {gate.get('regime')!r}, not 'D'")
    W = int(args.W or gate["first_fail_W"] or 0)
    measured_row = next((row for row in gate["rows"] if int(row["W"]) == W), None)
    if measured_row is None:
        raise SystemExit(f"E3' W={W} must be an exactly measured E2' curve point")
    single_reg_acc_at_W = float(measured_row["read_accuracy"])
    if single_reg_acc_at_W + 1e-12 >= float(gate["threshold"]):
        raise SystemExit(f"E3' W={W} is below the wall: single-register accuracy={single_reg_acc_at_W}")
    if bool(args.preprocess) != bool(args.partition):
        raise SystemExit("v4 2x2 cells require both --preprocess and --partition")
    branch_states = None
    state_source = None
    if args.states_dir:
        branch_states, state_source = load_state_shards(args.states_dir)
        branch_states = branch_states[: int(state_source["unique_branch_state_bound"])]
        if int(state_source["K"]) != int(args.K):
            raise SystemExit(f"state-shard K={state_source['K']} does not match --K={args.K}")
    operator = None
    if branch_states is None:
        device = resolve_device(args.device)
        operator = instantiate_operator(args.model, device, args.dtype, load_model=not args.no_load_model)
    factorial = bool(args.preprocess and args.partition)
    if factorial:
        rows = run_breakthrough_2x2(
            operator,
            args.D,
            args.K,
            W,
            parse_int_csv(args.Ns),
            args.preprocess,
            args.partition,
            args.seed,
            batch_size=args.batch_size,
            instances=args.instances,
            branch_states=branch_states,
            W_star_bind=int(gate["W_star_bind"]),
            single_register_acc_at_W=single_reg_acc_at_W,
            regime=str(gate["regime"]),
        )
    else:
        rows = run_breakthrough(
            operator,
            args.D,
            args.K,
            W,
            parse_int_csv(args.Ns),
            args.mode,
            args.seed,
            batch_size=args.batch_size,
            instances=args.instances,
            branch_states=branch_states,
            W_star_bind=int(gate["W_star_bind"]),
            single_reg_acc_at_W=single_reg_acc_at_W,
            regime=str(gate["regime"]),
        )
    raw_rows = [item for row in rows for item in row.pop("raw", [])]
    default_name = f"E3_double_prime_{args.partition}_{args.preprocess}" if factorial else f"E3_prime_breakthrough_{args.mode}"
    out = args.out or f"results/capacity/{default_name}.json"
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    raw_name = f"{Path(out).stem}_raw.json"
    write_json(RAW_ROOT / raw_name, {"rows": raw_rows})
    experiment_name = "E3_double_prime" if factorial else "E3_prime"
    payload = experiment_payload(experiment_name, args.model, args.D, args.K, args.seed, args.instances, rows, args.dtype)
    payload["schema"] = "multiagent_2x2_v4" if factorial else "multiagent_breakthrough_v3"
    payload["factorial_cell"] = {"partition": args.partition, "preprocess": args.preprocess} if factorial else None
    payload["width_wall_gate"] = gate
    payload["states_source"] = state_source
    payload["allow_ungated"] = False
    write_json(out, payload)


if __name__ == "__main__":
    main()
