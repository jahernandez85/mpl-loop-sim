"""closed_loop — Phase 13A minimal closed MPL solver.

Exports the fixed-architecture one-variable energy-closure solver for the
reference → evaporator → condenser → return path.

This package does NOT implement a generic network solver.  The architecture is
fixed at one evaporator and one condenser.  Pressure closure is deferred to
Phase 13B.

Exports
-------
ClosedLoopSolveConfig    — explicit solver configuration (max_iter, tolerance)
MinimalClosedMPLCase     — fully specified loop case (components + scenarios + bracket)
MinimalClosedMPLResult   — structured result with residuals, states, and diagnostics
solve_minimal_closed_mpl — entry-point solve function

Architectural constraints
-------------------------
- MUST NOT import from mpl_sim.network or mpl_sim.solvers.
- MUST NOT import CoolProp or mpl_sim.properties.
- MUST NOT resolve CorrelationRegistry or HeatExchangerModelRegistry internally.
- FluidState remains (P, h, identity); no property lookup occurs here.
"""

from mpl_sim.closed_loop.minimal_solver import (
    ClosedLoopSolveConfig,
    MinimalClosedMPLCase,
    MinimalClosedMPLResult,
    solve_minimal_closed_mpl,
)

__all__ = [
    "ClosedLoopSolveConfig",
    "MinimalClosedMPLCase",
    "MinimalClosedMPLResult",
    "solve_minimal_closed_mpl",
]
