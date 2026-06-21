"""closed_loop — Phase 13A/13B/13C/13D minimal closed MPL solvers and residual framework.

Exports fixed-architecture loop-closure solvers and a residual/unknown/scaling
framework foundation.

Phase 13A — one-variable energy closure:
  Solves Q_cond such that h_return = h_reference.

Phase 13B — one-variable pressure closure:
  Solves primary_mdot such that pump_head(mdot) = dP_total(mdot).
  This is a pressure-only closure (Option A); energy residual is diagnostic.

Phase 13C — residual/unknown/scaling framework:
  Value objects for declaring unknowns, residual equations, and scaled residual
  vectors.  Does NOT implement a generic solve(network) API.  Does NOT implement
  simultaneous energy+pressure closure.  Prepares the path toward Phase 13D
  (coupled fixed-architecture closure) and later network solving.

Phase 13D — coupled fixed-architecture energy+pressure closure:
  Solves both Q_cond and primary_mdot simultaneously so that:
    energy_residual   = h_return - h_reference = 0   (energy closure)
    pressure_residual = pump_head(mdot) - dP_total(mdot) = 0  (pressure closure)
  Uses nested scalar bisection (Option A): outer bisect over mdot for
  pressure closure; inner bisect over Q_cond for energy closure at each
  outer trial.  Uses ResidualVector for convergence diagnostics.
  This is NOT a generic network solver.  Architecture is fixed at one
  evaporator and one condenser.  No arbitrary topology.

Neither solver implements a generic network solver.  The architecture is
fixed at one evaporator and one condenser.

Exports
-------
Phase 13A:
  ClosedLoopSolveConfig    — solver config (max_iter, tolerance)
  MinimalClosedMPLCase     — loop case (components + scenarios + Q bracket)
  MinimalClosedMPLResult   — result with residuals, states, diagnostics
  solve_minimal_closed_mpl — energy-closure entry point

Phase 13B:
  PumpHeadCurve                  — explicit pump-head law value object
  PressureClosureConfig          — solver config (max_iter, tolerance)
  MinimalPressureClosureCase     — loop case (components + scenarios + mdot bracket)
  MinimalPressureClosureResult   — result with pressure residuals, states, diagnostics
  solve_minimal_pressure_closure — pressure-closure entry point

Phase 13C:
  UnknownSpec        — declares a scalar unknown (name, unit, optional bounds)
  ResidualSpec       — declares a residual equation (name, unit, scale)
  ResidualEvaluation — pairs a ResidualSpec with a raw residual value
  ResidualVector     — ordered collection with scaled norms and convergence check

Phase 13D:
  CoupledClosureConfig           — solver config (tolerances, scales, max_iters)
  MinimalCoupledClosureCase      — loop case (components + scenarios + both brackets)
  MinimalCoupledClosureResult    — result with both residuals, ResidualVector, diagnostics
  solve_minimal_coupled_closure  — coupled energy+pressure closure entry point

Architectural constraints
-------------------------
- MUST NOT import from mpl_sim.network or mpl_sim.solvers.
- MUST NOT import CoolProp or mpl_sim.properties.
- MUST NOT resolve CorrelationRegistry or HeatExchangerModelRegistry internally.
- FluidState remains (P, h, identity); no property lookup occurs here.
"""

from mpl_sim.closed_loop.coupled_solver import (
    CoupledClosureConfig,
    MinimalCoupledClosureCase,
    MinimalCoupledClosureResult,
    solve_minimal_coupled_closure,
)
from mpl_sim.closed_loop.minimal_solver import (
    ClosedLoopSolveConfig,
    MinimalClosedMPLCase,
    MinimalClosedMPLResult,
    solve_minimal_closed_mpl,
)
from mpl_sim.closed_loop.pressure_solver import (
    MinimalPressureClosureCase,
    MinimalPressureClosureResult,
    PressureClosureConfig,
    PumpHeadCurve,
    solve_minimal_pressure_closure,
)
from mpl_sim.closed_loop.residuals import (
    ResidualEvaluation,
    ResidualSpec,
    ResidualVector,
    UnknownSpec,
)

__all__ = [
    # Phase 13A — energy closure
    "ClosedLoopSolveConfig",
    "MinimalClosedMPLCase",
    "MinimalClosedMPLResult",
    "solve_minimal_closed_mpl",
    # Phase 13B — pressure closure
    "PumpHeadCurve",
    "PressureClosureConfig",
    "MinimalPressureClosureCase",
    "MinimalPressureClosureResult",
    "solve_minimal_pressure_closure",
    # Phase 13C — residual/unknown/scaling framework
    "UnknownSpec",
    "ResidualSpec",
    "ResidualEvaluation",
    "ResidualVector",
    # Phase 13D — coupled energy+pressure closure
    "CoupledClosureConfig",
    "MinimalCoupledClosureCase",
    "MinimalCoupledClosureResult",
    "solve_minimal_coupled_closure",
]
