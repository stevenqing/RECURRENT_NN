"""Capacity-law helpers for Module 1 stack benchmarks."""

from __future__ import annotations

import math
from typing import Iterable


def d_star_product(D: int, K: int) -> float:
    if K <= 1:
        raise ValueError("K must be greater than 1")
    return D / (2.0 * math.log(K))


def d_star_factored(D: int, K_var: int, K_val: int, c: float = 2.0) -> float:
    K_factor = max(K_var, K_val)
    if K_factor <= 1:
        raise ValueError("max(K_var, K_val) must be greater than 1")
    return (D / 2.0) / (c * math.log(K_factor))


def fit_constant_factored(D: int, K_var: int, K_val: int, observed_frontier: float) -> float:
    if observed_frontier <= 0:
        raise ValueError("observed_frontier must be positive")
    return (D / 2.0) / (observed_frontier * math.log(max(K_var, K_val)))


def linear_fit_r2(xs: Iterable[float], ys: Iterable[float]) -> dict[str, float]:
    x = list(xs)
    y = list(ys)
    if len(x) != len(y) or len(x) < 2:
        return {"slope": 0.0, "intercept": 0.0, "r2": 0.0}
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    denom = sum((value - x_mean) ** 2 for value in x)
    slope = 0.0 if denom == 0 else sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y)) / denom
    intercept = y_mean - slope * x_mean
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return {"slope": slope, "intercept": intercept, "r2": r2}


def fit_through_origin(xs: Iterable[float], ys: Iterable[float]) -> dict[str, float]:
    x = list(xs)
    y = list(ys)
    denom = sum(value * value for value in x)
    slope = 0.0 if denom == 0 else sum(xi * yi for xi, yi in zip(x, y)) / denom
    y_mean = sum(y) / len(y) if y else 0.0
    ss_tot = sum((yi - y_mean) ** 2 for yi in y)
    ss_res = sum((yi - slope * xi) ** 2 for xi, yi in zip(x, y))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return {"slope": slope, "r2": r2}


def capacity_features(D: int, K_var: int, K_val: int) -> dict[str, float]:
    return {
        "D_over_ln_Kvar": D / math.log(K_var),
        "D_over_ln_product": D / math.log(K_var * K_val),
        "halfD_over_ln_max_factor": (D / 2.0) / math.log(max(K_var, K_val)),
    }