"""Minimal steady solver — Phase 8C/8D.

Convergence gate: evaluates residual at the initial state once.
  - norm <= tolerance  -> CONVERGED
  - norm >  tolerance  -> FAILED  (no update rule in Phase 8C/8D)

Phase 8D adds:
  - solve_problem(): consume an AssembledSteadyProblem and return a
    SolverResult with ConvergenceMetadata (strategy RESIDUAL_GATE).

Hard constraints:
- MUST NOT import CoolProp, properties, correlations, calibration.
- MUST NOT import network, components, or geometry.
- MUST NOT mutate the initial SystemState.
- MUST NOT mutate any component or network object.
- No Newton, no Jacobians, no physical residuals in this phase.
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


class SteadySolver:
    """Minimal steady solver: convergence gate over a ResidualEvaluator.

    Phase 8C algorithm (Option A — convergence gate only):
      1. Evaluate residual at the initial state (evaluator called once).
      2. If norm <= tolerance  -> CONVERGED; return copy of initial state.
      3. Otherwise             -> FAILED;    return copy of initial state.

    Phase 8D adds solve_problem() which wraps the same gate and attaches
    ConvergenceMetadata to the report.

    No update rule is applied.  The initial SystemState is never mutated.
    """

    def solve(
        self,
        initial_state: SystemState,
        evaluator: ResidualEvaluator,
        options: SolverOptions,
    ) -> SolverResult:
        """Run the convergence gate and return a SolverResult.

        Parameters
        ----------
        initial_state : starting SystemState (never mutated in-place)
        evaluator     : ResidualEvaluator; called exactly once
        options       : SolverOptions specifying tolerance and max_iterations
        """
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

    def solve_problem(
        self,
        problem: AssembledSteadyProblem,
        options: SolverOptions,
    ) -> SolverResult:
        """Solve by consuming an AssembledSteadyProblem.

        Convergence gate (Phase 8D):
          1. Evaluate residual at problem.initial_state (evaluator called once).
          2. norm <= tolerance -> CONVERGED
          3. norm >  tolerance -> FAILED
          Attaches ConvergenceMetadata with strategy RESIDUAL_GATE.

        Does not mutate problem.initial_state.
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
