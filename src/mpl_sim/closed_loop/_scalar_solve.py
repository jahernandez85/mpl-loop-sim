"""Private bounded bisection helper — Phase 13B.

Not a public API.  Shared internally by minimal_solver.py (Phase 13A energy
closure) and pressure_solver.py (Phase 13B pressure closure).

The caller is responsible for:
- validating bracket bounds (finite, lo < hi, lo > 0 where applicable);
- computing r_lo and r_hi before calling;
- confirming r_lo * r_hi <= 0 (sign change or exact endpoint root);
- supplying a non-bool int max_iter >= 1 and finite tolerance > 0.

This module does NOT validate inputs; all validation lives in the public
solver functions.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class _BisectionResult:
    """Internal result of a single bounded bisection run."""

    converged: bool
    x: float
    residual: float
    iterations: int


def _bisect_bounded(
    f: Callable[[float], float],
    lo: float,
    r_lo: float,
    hi: float,
    r_hi: float,
    max_iter: int,
    tolerance: float,
) -> _BisectionResult:
    """Bounded bisection: find x in [lo, hi] such that f(x) ≈ 0.

    Preconditions (caller must guarantee before calling):
    - r_lo = f(lo) and r_hi = f(hi) already computed.
    - r_lo * r_hi <= 0 (sign change or exact root at one endpoint).
    - max_iter >= 1 and tolerance > 0.

    Exact roots at either endpoint are returned immediately with iterations=0
    and without calling f again.

    Returns _BisectionResult with the best x found, the corresponding
    residual, whether abs(residual) <= tolerance, and the bisection step count
    (endpoint roots return iterations=0; each midpoint evaluation increments
    by one).
    """
    if abs(r_lo) <= tolerance:
        return _BisectionResult(converged=True, x=lo, residual=r_lo, iterations=0)
    if abs(r_hi) <= tolerance:
        return _BisectionResult(converged=True, x=hi, residual=r_hi, iterations=0)

    iterations = 0
    converged = False
    x_mid = lo
    r_mid = r_lo

    for _ in range(max_iter):
        x_mid = 0.5 * (lo + hi)
        r_mid = f(x_mid)
        iterations += 1

        if abs(r_mid) <= tolerance:
            converged = True
            break

        if r_lo * r_mid < 0:
            hi = x_mid
            r_hi = r_mid
        else:
            lo = x_mid
            r_lo = r_mid

    return _BisectionResult(converged=converged, x=x_mid, residual=r_mid, iterations=iterations)
