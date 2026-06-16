"""Minimal steady solver — Phase 8C.

Convergence gate: evaluates residual at the initial state once.
  - norm <= tolerance  -> CONVERGED
  - norm >  tolerance  -> FAILED  (no update rule in Phase 8C)

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
    SolverOptions,
    SolverReport,
    SolverResult,
    SolverStatus,
)
from mpl_sim.solvers.residuals import ResidualEvaluator


class SteadySolver:
    """Minimal steady solver: convergence gate over a ResidualEvaluator.

    Phase 8C algorithm (Option A — convergence gate only):
      1. Evaluate residual at the initial state (evaluator called once).
      2. If norm <= tolerance  -> CONVERGED; return copy of initial state.
      3. Otherwise             -> FAILED;    return copy of initial state.

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
