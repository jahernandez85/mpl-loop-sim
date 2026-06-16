"""Solvers package — Phase 8: first steady solver foundation.

Exports:

  Phase 8A — solver contract primitives:
    SolverId, SolverStatus, SolverOptions, SolverReport, SolverResult

  Phase 8B — residual evaluation interface:
    ResidualVector, ResidualEvaluation, ResidualEvaluator

  Phase 8C — minimal steady solver:
    SteadySolver

MUST NOT be imported by network/, components/, properties/, correlations/,
calibration/, geometry/, or discretization/.
"""

from mpl_sim.solvers.base import (
    SolverId,
    SolverOptions,
    SolverReport,
    SolverResult,
    SolverStatus,
)
from mpl_sim.solvers.residuals import (
    ResidualEvaluation,
    ResidualEvaluator,
    ResidualVector,
)
from mpl_sim.solvers.steady import SteadySolver

__all__ = [
    # Phase 8A
    "SolverId",
    "SolverStatus",
    "SolverOptions",
    "SolverReport",
    "SolverResult",
    # Phase 8B
    "ResidualVector",
    "ResidualEvaluation",
    "ResidualEvaluator",
    # Phase 8C
    "SteadySolver",
]
