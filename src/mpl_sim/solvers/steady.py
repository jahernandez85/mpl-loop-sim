"""Minimal steady solver — Phase 8C/8D/8E.

Phase 8C/8D — convergence gate (no update_provider):
  evaluate residual at the initial state once.
  - norm <= tolerance  -> CONVERGED
  - norm >  tolerance  -> FAILED

Phase 8E — fixed-point iteration (with update_provider):
  iterate: evaluate residual, check convergence, propose update.
  - norm <= tolerance  -> CONVERGED  (metadata strategy = FIXED_POINT)
  - max_iterations hit -> MAX_ITERATIONS

Iteration semantics (Phase 8E):
  For each iteration i in 1..max_iterations:
    1. Evaluate residual at current state.
    2. If norm <= tolerance -> CONVERGED with iterations=i.
    3. If i == max_iterations -> break (MAX_ITERATIONS; no extra update).
    4. Else -> call update_provider, advance to candidate state.
  This means N iterations produce N residual evaluations and N-1 update calls
  when MAX_ITERATIONS is reached; the final state and final norm are consistent
  (both from the last iteration's pre-break evaluation point).

Hard constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, or geometry.
- MUST NOT mutate the initial SystemState.
- MUST NOT mutate any component or network object.
- No Newton, no Jacobians, no physical residuals.
"""

from __future__ import annotations

from mpl_sim.core.state import SystemState
from mpl_sim.solvers.base import (
    ConvergenceMetadata,
    ConvergenceStrategy,
    SolverOptions,
    SolverReport,
    SolverResult,
    SolverStatus,
)
from mpl_sim.solvers.problem import AssembledSteadyProblem
from mpl_sim.solvers.residuals import ResidualEvaluator
from mpl_sim.solvers.updates import StateUpdate, StateUpdateProvider


class SteadySolver:
    """Steady solver with convergence gate and optional fixed-point iteration.

    Phase 8C/8D: solve() / solve_problem() without update_provider — single
      residual evaluation; CONVERGED or FAILED.

    Phase 8E: solve() with update_provider — fixed-point loop; CONVERGED or
      MAX_ITERATIONS. ConvergenceMetadata.strategy is FIXED_POINT.

    The initial SystemState is never mutated. The problem and evaluator are
    never mutated. No physics, network, or component code is called.
    """

    def solve(
        self,
        initial_state: SystemState,
        evaluator: ResidualEvaluator,
        options: SolverOptions,
        update_provider: StateUpdateProvider | None = None,
    ) -> SolverResult:
        """Run the solver and return a SolverResult.

        Without update_provider: convergence gate (Phase 8C) — evaluator
          called exactly once; no ConvergenceMetadata attached.
        With update_provider: fixed-point iteration (Phase 8E) — evaluator
          called up to max_iterations times; ConvergenceMetadata attached.

        The initial SystemState is never mutated in-place.
        """
        if update_provider is None:
            return self._solve_gate(initial_state, evaluator, options)
        return self._solve_fixed_point(initial_state, evaluator, options, update_provider)

    # ------------------------------------------------------------------
    # Phase 8C/8D: convergence gate
    # ------------------------------------------------------------------

    def _solve_gate(
        self,
        initial_state: SystemState,
        evaluator: ResidualEvaluator,
        options: SolverOptions,
    ) -> SolverResult:
        evaluation = evaluator.evaluate(initial_state)
        norm = evaluation.norm
        final_state = initial_state.copy()

        if norm <= options.tolerance:
            report = SolverReport(
                status=SolverStatus.CONVERGED,
                iterations=1,
                residual_norm=norm,
                message=f"Converged at initial evaluation; norm={norm:.6g}",
            )
        else:
            report = SolverReport(
                status=SolverStatus.FAILED,
                iterations=1,
                residual_norm=norm,
                message=(
                    f"Residual norm {norm:.6g} exceeds tolerance "
                    f"{options.tolerance:.6g}; no update rule in Phase 8C."
                ),
            )

        return SolverResult(state=final_state, report=report)

    # ------------------------------------------------------------------
    # Phase 8E: fixed-point iteration
    # ------------------------------------------------------------------

    def _solve_fixed_point(
        self,
        initial_state: SystemState,
        evaluator: ResidualEvaluator,
        options: SolverOptions,
        update_provider: StateUpdateProvider,
    ) -> SolverResult:
        current_state = initial_state.copy()
        last_norm: float = 0.0

        for iteration in range(1, options.max_iterations + 1):
            evaluation = evaluator.evaluate(current_state)
            last_norm = evaluation.norm

            if last_norm <= options.tolerance:
                metadata = ConvergenceMetadata(
                    strategy=ConvergenceStrategy.FIXED_POINT,
                    tolerance=options.tolerance,
                    max_iterations=options.max_iterations,
                    iterations=iteration,
                    converged=True,
                    final_residual_norm=last_norm,
                    message=(
                        f"Fixed-point converged at iteration {iteration}; " f"norm={last_norm:.6g}"
                    ),
                )
                report = SolverReport(
                    status=SolverStatus.CONVERGED,
                    iterations=iteration,
                    residual_norm=last_norm,
                    message=(
                        f"Fixed-point converged at iteration {iteration}; " f"norm={last_norm:.6g}"
                    ),
                    convergence_metadata=metadata,
                )
                return SolverResult(state=current_state, report=report)

            if iteration == options.max_iterations:
                break

            update = update_provider.propose_update(current_state, evaluation)
            if not isinstance(update, StateUpdate):
                raise TypeError(
                    f"update_provider.propose_update must return StateUpdate; "
                    f"got {type(update)!r}"
                )
            if not isinstance(update.state, SystemState):
                raise TypeError(
                    f"StateUpdate.state must be a SystemState; " f"got {type(update.state)!r}"
                )
            current_state = update.state

        metadata = ConvergenceMetadata(
            strategy=ConvergenceStrategy.FIXED_POINT,
            tolerance=options.tolerance,
            max_iterations=options.max_iterations,
            iterations=options.max_iterations,
            converged=False,
            final_residual_norm=last_norm,
            message=(
                f"Fixed-point reached max_iterations={options.max_iterations}; "
                f"norm={last_norm:.6g}"
            ),
        )
        report = SolverReport(
            status=SolverStatus.MAX_ITERATIONS,
            iterations=options.max_iterations,
            residual_norm=last_norm,
            message=(
                f"Fixed-point reached max_iterations={options.max_iterations}; "
                f"norm={last_norm:.6g}"
            ),
            convergence_metadata=metadata,
        )
        return SolverResult(state=current_state, report=report)

    # ------------------------------------------------------------------
    # Phase 8D: solve_problem() — convergence gate via AssembledSteadyProblem
    # ------------------------------------------------------------------

    def solve_problem(
        self,
        problem: AssembledSteadyProblem,
        options: SolverOptions,
    ) -> SolverResult:
        """Solve by consuming an AssembledSteadyProblem (Phase 8D).

        Convergence gate: evaluator called once.  ConvergenceMetadata attached
        with strategy RESIDUAL_GATE.  Does not mutate problem.initial_state.
        """
        evaluation = problem.evaluate_residual(problem.initial_state)
        norm = evaluation.norm
        final_state = problem.initial_state.copy()
        converged = norm <= options.tolerance

        metadata = ConvergenceMetadata(
            strategy=ConvergenceStrategy.RESIDUAL_GATE,
            tolerance=options.tolerance,
            max_iterations=options.max_iterations,
            iterations=1,
            converged=converged,
            final_residual_norm=norm,
            message=f"Convergence gate; norm={norm:.6g}",
        )

        if converged:
            report = SolverReport(
                status=SolverStatus.CONVERGED,
                iterations=1,
                residual_norm=norm,
                message=f"Converged at initial evaluation; norm={norm:.6g}",
                convergence_metadata=metadata,
            )
        else:
            report = SolverReport(
                status=SolverStatus.FAILED,
                iterations=1,
                residual_norm=norm,
                message=(
                    f"Residual norm {norm:.6g} exceeds tolerance "
                    f"{options.tolerance:.6g}; no update rule in Phase 8D."
                ),
                convergence_metadata=metadata,
            )

        return SolverResult(state=final_state, report=report)
