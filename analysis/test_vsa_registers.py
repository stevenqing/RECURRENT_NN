"""Unit tests for proper Module 1 VSA register primitives."""

from __future__ import annotations

import json

import torch

from register.vsa_stack import BoundSingleRegister, FactoredRegister, bind, cleanup, involution, make_permutation_powers, rand_vec, unbind


def test_permutation_identities(device: str = "cuda:0" if torch.cuda.is_available() else "cpu") -> dict:
    n = 128
    max_depth = 16
    pow_index, inv_index = make_permutation_powers(n, max_depth, seed=42, device=device)
    x = torch.randn(n, device=device)
    errors = []
    for level in range(max_depth + 1):
        rolled = x[pow_index[level]]
        restored = rolled[inv_index[level]]
        errors.append(float((restored - x).abs().max().item()))
    return {"name": "permutation_identities", "max_error": max(errors), "passed": max(errors) < 1e-7}


def test_single_item_unbind(device: str = "cuda:0" if torch.cuda.is_available() else "cpu") -> dict:
    generator = torch.Generator().manual_seed(137)
    n = 256
    a = rand_vec(n, generator, device)
    b = rand_vec(n, generator, device)
    c = bind(a, b)
    recovered = unbind(c, a)
    codebook = torch.stack([b, rand_vec(n, generator, device), rand_vec(n, generator, device)])
    pred, margin = cleanup(recovered, codebook)
    return {"name": "single_item_unbind", "prediction": int(pred.item()), "margin": float(margin.item()), "passed": int(pred.item()) == 0}


def test_push_pop(register_cls, device: str = "cuda:0" if torch.cuda.is_available() else "cpu") -> dict:
    register = register_cls(D=128, K_var=20, K_val=3, max_depth=4, seed=256, device=device)
    register.push(0, 7, 2)
    var, val, margin = register.pop(0)
    residual = float(register.h.norm().item())
    return {"name": f"{register_cls.__name__}_d1_push_pop", "var": var, "val": val, "margin": margin, "residual_norm": residual, "passed": var == 7 and val == 2 and residual < 1e-5}


def run() -> dict:
    checks = [
        test_permutation_identities(),
        test_single_item_unbind(),
        test_push_pop(BoundSingleRegister),
        test_push_pop(FactoredRegister),
    ]
    result = {"passed": all(check["passed"] for check in checks), "checks": checks}
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    result = run()
    if not result["passed"]:
        raise SystemExit(1)