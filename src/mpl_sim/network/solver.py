"""Configurable network residual solver — Phase 13H.

Provides a minimal configurable solver that iterates explicit unknown values
to drive explicit residual callbacks toward zero, building on the Phase 13G
residual-evaluation layer.

What this module DOES
---------------------
- Accepts a NetworkResidualAssembly (Phase 13F declarations).
- Accepts initial unknown values as NetworkUnknownValues or a Mapping.
- Accepts explicit NetworkResidualEvaluator callbacks (one per residual).
- Accepts explicit residual scales (one per residual).
- Accepts a NetworkSolveConfig controlling iteration behavior.
- Iterates unknown values using a damped finite-difference Newton method.
- Returns a NetworkSolveResult with convergence status, final values,
  final evaluation result, initial evaluation result, and optional
  residual-norm history.

Solver method: damped finite-difference Newton
----------------------------------------------
- Forward finite differences build the n×n Jacobian at each iterate.
- Gaussian elimination with partial pivoting solves J dx = -r.
- Update: x_new = x + damping * dx.
- Convergence: max_abs_scaled <= tolerance.
- Singularity detection: pivot below _SINGULAR_THRESHOLD terminates early.
- Only square systems (n_unknowns == n_residuals) are accepted.

Architecture boundaries (MUST NOT)
-----------------------------------
- MUST NOT construct residuals automatically from component physics.
- MUST NOT execute component instances or call physical component methods.
- MUST NOT call the frozen component contribution method.
- MUST NOT call thermodynamic property backends or correlation registries.
- MUST NOT attach physical state to graph nodes.
- MUST NOT import external optimization or root-finding libraries.
- MUST NOT mutate the caller-supplied assembly, initial values, or evaluators.
- MUST NOT expose a solve(network) method on any type in this module.

Exported names
--------------
NetworkSolveConfig             — immutable solver configuration
NetworkSolveResult             — immutable solve result with diagnostics
solve_network_residual_problem — main solver entry point
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from mpl_sim.network.residual_assembly import NetworkResidualAssembly
from mpl_sim.network.residual_evaluation import (
    NetworkResidualEvaluationResult,
    NetworkResidualEvaluator,
    NetworkUnknownValues,
    evaluate_network_residuals,
)

# ---------------------------------------------------------------------------
# Internal linear-algebra helper
# ---------------------------------------------------------------------------

_SINGULAR_THRESHOLD: float = 1e-14


def _solve_linear_system(
    jacobian: list[list[float]],
    neg_residual: list[float],
    n: int,
) -> list[float]:
    """Solve J dx = neg_residual (i.e. J dx = -r) via Gaussian elimination.

    Uses partial pivoting for numerical stability.  Raises ValueError if the
    system is singular or nearly singular (pivot below _SINGULAR_THRESHOLD).
    """
    M: list[list[float]] = [jacobian[i][:] + [neg_residual[i]] for i in range(n)]

    for col in range(n):
        # Partial pivot: find row with largest absolute value in column.
        max_row = col
        max_abs = abs(M[col][col])
        for row in range(col + 1, n):
            a = abs(M[row][col])
            if a > max_abs:
                max_abs = a
                max_row = row
        if max_row != col:
            M[col], M[max_row] = M[max_row], M[col]

        pivot = M[col][col]
        if abs(pivot) < _SINGULAR_THRESHOLD:
            raise ValueError(
                f"Jacobian is singular or nearly singular "
                f"(pivot abs={abs(pivot):.2e} < threshold={_SINGULAR_THRESHOLD:.2e}) "
                f"at column {col}"
            )

        for row in range(col + 1, n):
            factor = M[row][col] / pivot
            for k in range(col, n + 1):
                M[row][k] -= factor * M[col][k]

    x: list[float] = [0.0] * n
    for row in range(n - 1, -1, -1):
        x[row] = M[row][n]
        for k in range(row + 1, n):
            x[row] -= M[row][k] * x[k]
        x[row] /= M[row][row]

    return x


# ---------------------------------------------------------------------------
# NetworkSolveConfig
# ---------------------------------------------------------------------------


def _require_positive_float(field: str, value: object) -> None:
    if isinstance(value, bool):
        raise TypeError(f"NetworkSolveConfig.{field} must not be bool; got {value!r}")
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"NetworkSolveConfig.{field} must be numeric; " f"got {type(value).__name__!r}"
        )
    fval = float(value)
    if not math.isfinite(fval):
        raise ValueError(f"NetworkSolveConfig.{field} must be finite; got {value!r}")
    if fval <= 0.0:
        raise ValueError(f"NetworkSolveConfig.{field} must be > 0; got {value!r}")


@dataclass(frozen=True)
class NetworkSolveConfig:
    """Immutable configuration for the configurable network residual solver.

    Fields
    ------
    max_iterations : int
        Maximum Newton iterations (>= 1, not bool).
    tolerance : float
        Convergence criterion on max_abs_scaled (finite, > 0, not bool).
    finite_difference_step : float
        Step size for forward-difference Jacobian (finite, > 0, not bool).
    damping : float
        Newton step damping factor in (0, 1] (finite, > 0, <= 1, not bool).
        Default 1.0 gives a full Newton step.
    record_history : bool
        If True, max_abs_scaled is recorded after each iteration and stored
        in NetworkSolveResult.residual_norm_history.  Default False.

    Raises
    ------
    TypeError
        If max_iterations is bool or not int.
        If tolerance, finite_difference_step, or damping is bool or not numeric.
        If record_history is not bool.
    ValueError
        If max_iterations < 1.
        If tolerance, finite_difference_step, or damping is zero, negative,
        nan, or inf.
        If damping > 1.
    """

    max_iterations: int
    tolerance: float
    finite_difference_step: float
    damping: float = 1.0
    record_history: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.max_iterations, bool):
            raise TypeError(
                "NetworkSolveConfig.max_iterations must not be bool; "
                f"got {self.max_iterations!r}"
            )
        if not isinstance(self.max_iterations, int):
            raise TypeError(
                "NetworkSolveConfig.max_iterations must be an int; "
                f"got {type(self.max_iterations).__name__!r}"
            )
        if self.max_iterations < 1:
            raise ValueError(
                "NetworkSolveConfig.max_iterations must be >= 1; " f"got {self.max_iterations!r}"
            )
        _require_positive_float("tolerance", self.tolerance)
        _require_positive_float("finite_difference_step", self.finite_difference_step)
        _require_positive_float("damping", self.damping)
        if float(self.damping) > 1.0:
            raise ValueError(f"NetworkSolveConfig.damping must be <= 1.0; got {self.damping!r}")
        if not isinstance(self.record_history, bool):
            raise TypeError(
                "NetworkSolveConfig.record_history must be bool; "
                f"got {type(self.record_history).__name__!r}"
            )


# ---------------------------------------------------------------------------
# NetworkSolveResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NetworkSolveResult:
    """Immutable result of a configurable network residual solve.

    Contains full diagnostics regardless of convergence status.  The solver
    never claims convergence unless final max_abs_scaled <= config.tolerance.

    Fields
    ------
    converged : bool
        True if final max_abs_scaled <= config.tolerance.
    iteration_count : int
        Number of Newton iterations performed (>= 0).
    reason : str
        Human-readable status string describing why the solver stopped.
    final_unknown_values : NetworkUnknownValues
        Unknown values at the end of the solve, regardless of convergence.
    final_evaluation : NetworkResidualEvaluationResult
        Phase 13G evaluation result at final_unknown_values.
    initial_evaluation : NetworkResidualEvaluationResult
        Phase 13G evaluation result at the initial unknown values.
    residual_norm_history : tuple[float, ...] or None
        max_abs_scaled recorded after each completed iteration when
        record_history=True in config, else None.
    """

    converged: bool
    iteration_count: int
    reason: str
    final_unknown_values: NetworkUnknownValues
    final_evaluation: NetworkResidualEvaluationResult
    initial_evaluation: NetworkResidualEvaluationResult
    residual_norm_history: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if not isinstance(self.converged, bool):
            raise TypeError(
                "NetworkSolveResult.converged must be bool; "
                f"got {type(self.converged).__name__!r}"
            )
        if not isinstance(self.final_unknown_values, NetworkUnknownValues):
            raise TypeError(
                "NetworkSolveResult.final_unknown_values must be a "
                f"NetworkUnknownValues; got {type(self.final_unknown_values).__name__!r}"
            )
        if not isinstance(self.final_evaluation, NetworkResidualEvaluationResult):
            raise TypeError(
                "NetworkSolveResult.final_evaluation must be a "
                f"NetworkResidualEvaluationResult; "
                f"got {type(self.final_evaluation).__name__!r}"
            )
        if not isinstance(self.initial_evaluation, NetworkResidualEvaluationResult):
            raise TypeError(
                "NetworkSolveResult.initial_evaluation must be a "
                f"NetworkResidualEvaluationResult; "
                f"got {type(self.initial_evaluation).__name__!r}"
            )
        if self.residual_norm_history is not None and not isinstance(
            self.residual_norm_history, tuple
        ):
            object.__setattr__(self, "residual_norm_history", tuple(self.residual_norm_history))


# ---------------------------------------------------------------------------
# solve_network_residual_problem
# ---------------------------------------------------------------------------


def solve_network_residual_problem(
    assembly: object,
    initial_values: object,
    evaluators: object,
    scales: object,
    config: object,
) -> NetworkSolveResult:
    """Solve an explicit network residual problem with a damped Newton method.

    Repeatedly calls evaluate_network_residuals (Phase 13G) and updates the
    unknown values using a finite-difference Newton step until the scaled
    residual norm drops below config.tolerance or max_iterations is reached.

    Parameters
    ----------
    assembly
        NetworkResidualAssembly (Phase 13F).  Provides declared unknown and
        residual names in insertion order.
    initial_values
        Starting point: NetworkUnknownValues or Mapping[str, float].  Keys
        must match the assembly unknown declarations exactly.  Not mutated.
    evaluators
        Sequence of NetworkResidualEvaluator, one per declared residual.
        Names must match assembly residual declarations exactly.  Callbacks
        may represent any pure algebraic computation.
    scales
        Mapping[str, float] from residual name to characteristic scale.
        Forwarded to evaluate_network_residuals for each iteration.
    config
        NetworkSolveConfig controlling max_iterations, tolerance,
        finite_difference_step, damping, and record_history.

    Returns
    -------
    NetworkSolveResult
        Always returned (never raises for normal solver failure).  Contains
        converged flag, iteration count, reason string, final and initial
        evaluations, and optional residual-norm history.

    Raises
    ------
    TypeError
        If config is not NetworkSolveConfig.
        If assembly is not NetworkResidualAssembly.
        If initial_values is not NetworkUnknownValues or a Mapping.
    ValueError
        If unknown names in initial_values do not match assembly declarations.
        If evaluator or scale names do not match assembly declarations.
        From NetworkUnknownValues construction if values are invalid.
    Exception
        Callback exceptions from evaluators propagate unchanged (consistent
        with evaluate_network_residuals Phase 13G semantics).

    Notes
    -----
    - Only square systems (n_unknowns == n_residuals) are accepted; an
      underdetermined or overdetermined system returns converged=False
      immediately with a descriptive reason.
    - The initial guess is checked before any iteration; if already converged,
      iteration_count=0 is returned.
    - The Jacobian is built by forward finite differences (one extra
      evaluation per unknown per iteration).
    - Singular or nearly singular Jacobians return converged=False with a
      descriptive reason rather than raising.
    - Non-finite unknown values after an update return converged=False.
    - The caller-supplied assembly, initial_values, and evaluators are never
      mutated.
    - Does NOT construct physical residuals from components.
    - Does NOT execute ComponentInstance objects.
    - Does NOT look up fluid properties.
    - Does NOT attach state to NetworkGraph nodes.
    """
    # --- validate config first so callers get a clear error early ---
    if not isinstance(config, NetworkSolveConfig):
        raise TypeError(
            "solve_network_residual_problem: config must be a NetworkSolveConfig; "
            f"got {type(config).__name__!r}"
        )

    # --- validate assembly ---
    if not isinstance(assembly, NetworkResidualAssembly):
        raise TypeError(
            "solve_network_residual_problem: assembly must be a "
            f"NetworkResidualAssembly; got {type(assembly).__name__!r}"
        )

    # --- build initial NetworkUnknownValues ---
    if isinstance(initial_values, NetworkUnknownValues):
        initial_uv: NetworkUnknownValues = initial_values
    elif isinstance(initial_values, Mapping):
        initial_uv = NetworkUnknownValues(values=dict(initial_values))
    else:
        raise TypeError(
            "solve_network_residual_problem: initial_values must be a "
            "NetworkUnknownValues or Mapping[str, float]; "
            f"got {type(initial_values).__name__!r}"
        )

    # --- normalise evaluators to a list once so generators work correctly ---
    if isinstance(evaluators, Mapping):
        raise TypeError(
            "solve_network_residual_problem: evaluators must be a Sequence of "
            "NetworkResidualEvaluator, not a Mapping"
        )
    try:
        evaluators_list: list[NetworkResidualEvaluator] = list(evaluators)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(
            "solve_network_residual_problem: evaluators must be iterable; "
            f"got {type(evaluators).__name__!r}"
        ) from exc

    # --- evaluate initial residuals; this validates evaluators and scales ---
    initial_eval: NetworkResidualEvaluationResult = evaluate_network_residuals(
        assembly, initial_uv, evaluators_list, scales
    )

    # --- require square system before iterating ---
    n_unknowns: int = assembly.unknowns.count()
    n_residuals: int = assembly.residuals.count()
    if n_unknowns != n_residuals:
        return NetworkSolveResult(
            converged=False,
            iteration_count=0,
            reason=(
                f"underdetermined or overdetermined system: "
                f"{n_unknowns} unknown(s) != {n_residuals} residual(s)"
            ),
            final_unknown_values=initial_uv,
            final_evaluation=initial_eval,
            initial_evaluation=initial_eval,
            residual_norm_history=None,
        )

    n: int = n_unknowns
    unknown_names: tuple[str, ...] = assembly.unknowns.names()
    h: float = config.finite_difference_step
    damping: float = float(config.damping)
    record: bool = config.record_history

    # --- check if initial guess already satisfies the tolerance ---
    if initial_eval.max_abs_scaled <= config.tolerance:
        return NetworkSolveResult(
            converged=True,
            iteration_count=0,
            reason="converged at initial guess",
            final_unknown_values=initial_uv,
            final_evaluation=initial_eval,
            initial_evaluation=initial_eval,
            residual_norm_history=() if record else None,
        )

    # --- main Newton loop ---
    current_uv: NetworkUnknownValues = initial_uv
    current_eval: NetworkResidualEvaluationResult = initial_eval
    history: list[float] = []

    for iteration in range(config.max_iterations):
        r0: list[float] = [ev.value for ev in current_eval.evaluations]
        current_dict: dict[str, float] = dict(current_eval.unknown_values.values)

        # Build n×n Jacobian by forward finite differences.
        J: list[list[float]] = [[0.0] * n for _ in range(n)]
        for j, name in enumerate(unknown_names):
            perturbed: dict[str, float] = dict(current_dict)
            perturbed[name] = perturbed[name] + h
            perturbed_uv = NetworkUnknownValues(values=perturbed)
            perturbed_eval = evaluate_network_residuals(
                assembly, perturbed_uv, evaluators_list, scales
            )
            r1: list[float] = [ev.value for ev in perturbed_eval.evaluations]
            for i in range(n):
                J[i][j] = (r1[i] - r0[i]) / h

        # Solve J dx = -r.
        neg_r: list[float] = [-r for r in r0]
        try:
            dx: list[float] = _solve_linear_system(J, neg_r, n)
        except ValueError as exc:
            return NetworkSolveResult(
                converged=False,
                iteration_count=iteration,
                reason=f"singular Jacobian at iteration {iteration}: {exc}",
                final_unknown_values=current_uv,
                final_evaluation=current_eval,
                initial_evaluation=initial_eval,
                residual_norm_history=tuple(history) if record else None,
            )

        # Apply damped update.
        new_dict: dict[str, float] = dict(current_dict)
        for j, name in enumerate(unknown_names):
            new_dict[name] = new_dict[name] + damping * dx[j]

        # Check all updated values are finite.
        for name, val in new_dict.items():
            if not math.isfinite(val):
                return NetworkSolveResult(
                    converged=False,
                    iteration_count=iteration + 1,
                    reason=(
                        f"non-finite unknown '{name}' after update " f"at iteration {iteration + 1}"
                    ),
                    final_unknown_values=current_uv,
                    final_evaluation=current_eval,
                    initial_evaluation=initial_eval,
                    residual_norm_history=tuple(history) if record else None,
                )

        # Evaluate residuals at updated values.
        new_uv = NetworkUnknownValues(values=new_dict)
        new_eval: NetworkResidualEvaluationResult = evaluate_network_residuals(
            assembly, new_uv, evaluators_list, scales
        )

        current_uv = new_uv
        current_eval = new_eval

        if record:
            history.append(current_eval.max_abs_scaled)

        if current_eval.max_abs_scaled <= config.tolerance:
            return NetworkSolveResult(
                converged=True,
                iteration_count=iteration + 1,
                reason="converged",
                final_unknown_values=current_uv,
                final_evaluation=current_eval,
                initial_evaluation=initial_eval,
                residual_norm_history=tuple(history) if record else None,
            )

    return NetworkSolveResult(
        converged=False,
        iteration_count=config.max_iterations,
        reason="max_iterations reached without convergence",
        final_unknown_values=current_uv,
        final_evaluation=current_eval,
        initial_evaluation=initial_eval,
        residual_norm_history=tuple(history) if record else None,
    )
