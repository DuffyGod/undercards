"""Solve a finite zero-sum matrix game over a declared causal policy pool.

Rows maximize, columns minimize the supplied payoff. This module does not
establish that either pool contains all strategies of the underlying game,
nor that a supplied payoff matrix respects hidden information or game rules.

Usage: result = solve([[1, -1], [-1, 1]])
Requires NumPy and SciPy; all returned fields are JSON-serializable.
"""
from __future__ import annotations

import json
import math

import numpy as np
from scipy.optimize import linprog


def _probabilities(raw: np.ndarray, label: str) -> np.ndarray:
    """Remove numerical LP noise, then validate an actual mixed strategy."""
    p = np.asarray(raw, dtype=float)
    if not np.all(np.isfinite(p)) or np.min(p) < -1e-8:
        raise RuntimeError(f"{label}: solver returned invalid probabilities")
    p = np.maximum(p, 0.0)
    total = float(p.sum())
    if total <= 0 or not math.isclose(total, 1.0, abs_tol=1e-7):
        raise RuntimeError(f"{label}: solver probabilities do not sum to one")
    p /= total
    if np.any(p < 0) or not math.isclose(float(p.sum()), 1.0, abs_tol=1e-12):
        raise RuntimeError(f"{label}: probability normalization failed")
    return p


def solve(matrix) -> dict:
    """Return mixed policies and a numerical primal/dual certificate.

    For payoff matrix A, x is the row mixture and y the column mixture:
      lower_bound = min_j (x^T A)_j
      upper_bound = max_i (A y)_i
      value       = x^T A y
      gap         = upper_bound - lower_bound

    The bounds certify only this finite matrix game. Invalid inputs, failed
    LPs, or an excessive numerical certificate gap raise an exception rather
    than silently returning an uncertified policy. Payoffs can be negative.
    """
    try:
        a = np.asarray(matrix, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Expected a rectangular finite numeric matrix") from exc
    if a.ndim != 2 or min(a.shape, default=0) == 0:
        raise ValueError("Expected a nonempty two-dimensional matrix")
    if not np.all(np.isfinite(a)):
        raise ValueError("Payoffs must all be finite")
    rows, cols = a.shape
    # Positive scaling preserves equilibria and prevents large/small payoff
    # units from controlling the LP feasibility tolerances.
    scale = float(np.max(np.abs(a))) or 1.0
    b = a / scale
    options = dict(primal_feasibility_tolerance=1e-9,
                   dual_feasibility_tolerance=1e-9)

    # Maximize v with B^T x >= v and sum(x)=1. v is unrestricted.
    row_lp = linprog(
        np.r_[np.zeros(rows), -1.0],
        A_ub=np.column_stack((-b.T, np.ones(cols))),
        b_ub=np.zeros(cols),
        A_eq=np.r_[np.ones(rows), 0.0][None, :], b_eq=[1.0],
        bounds=[(0.0, None)] * rows + [(None, None)],
        method="highs", options=options,
    )
    # Minimize w with B y <= w and sum(y)=1. w is unrestricted.
    col_lp = linprog(
        np.r_[np.zeros(cols), 1.0],
        A_ub=np.column_stack((b, -np.ones(rows))),
        b_ub=np.zeros(rows),
        A_eq=np.r_[np.ones(cols), 0.0][None, :], b_eq=[1.0],
        bounds=[(0.0, None)] * cols + [(None, None)],
        method="highs", options=options,
    )
    for label, result in (("row", row_lp), ("column", col_lp)):
        if not result.success:
            raise RuntimeError(f"{label} LP failed: {result.message}")

    x = _probabilities(row_lp.x[:-1], "row")
    y = _probabilities(col_lp.x[:-1], "column")
    lower = float(np.min(x @ b))
    upper = float(np.max(b @ y))
    value = float(x @ b @ y)
    tolerance = 1e-7  # in normalized payoff units
    if lower > upper + tolerance or not lower - tolerance <= value <= upper + tolerance:
        raise RuntimeError("Computed policies violate minimax bounds")
    if upper - lower > tolerance:
        raise RuntimeError(f"Uncertified numerical minimax gap: {upper-lower}")
    if abs(-row_lp.fun - col_lp.fun) > tolerance:
        raise RuntimeError("Primal and dual LP values disagree")
    # Only widen a possible sub-ULP crossing; never make a strategy's
    # mathematical guarantee stronger through numerical rounding.
    lower, upper = min(lower, upper, value), max(lower, upper, value)
    result = dict(row_mixture=x.tolist(), col_mixture=y.tolist(),
                  value=value*scale, lower_bound=lower*scale,
                  upper_bound=upper*scale, gap=(upper-lower)*scale)
    if not all(math.isfinite(result[k]) for k in
               ("value", "lower_bound", "upper_bound", "gap")):
        raise RuntimeError("Payoff magnitudes overflow finite diagnostics")
    return result


def _self_check() -> dict:
    cases = [
        ("matching_pennies", [[1, -1], [-1, 1]], 0.0,
         [0.5, 0.5], [0.5, 0.5]),
        ("dominant_row", [[3, 1], [2, 0], [0, -1]], 1.0,
         [1.0, 0.0, 0.0], [0.0, 1.0]),
        ("rectangular_pure", [[3, 2, 4], [1, 0, 2]], 2.0,
         [1.0, 0.0], [0.0, 1.0, 0.0]),
        ("rectangular_mixed", [[1, 0], [0, 1], [-1, -1]], 0.5,
         [0.5, 0.5, 0.0], [0.5, 0.5]),
    ]
    checked = []
    for name, matrix, expected, row, col in cases:
        result = solve(matrix)
        assert math.isclose(result["value"], expected, abs_tol=1e-7), name
        assert np.allclose(result["row_mixture"], row, atol=1e-7), name
        assert np.allclose(result["col_mixture"], col, atol=1e-7), name
        assert result["lower_bound"] <= expected + 1e-7, name
        assert result["upper_bound"] >= expected - 1e-7, name
        assert 0 <= result["gap"] <= 1e-7, name
        checked.append(dict(name=name, **result))
    return dict(status="passed", cases=checked,
                scope="Declared finite policy pools only; not full-game equilibrium")


if __name__ == "__main__":
    print(json.dumps(_self_check(), indent=2))
