"""Minimal pressure closure solver — Phase 13B.

Implements a fixed-architecture one-variable pressure closure for a
reference → evaporator → condenser path.

Solved unknown: primary mass flow rate primary_mdot [kg/s].
Solved condition: pump_head(mdot) - dP_total(mdot) = 0  (pressure closure).
Solver method: bisection via the private _bisect_bounded helper.

This is Option A (pressure-only closure).  The energy residual
h_return - h_reference is reported as a diagnostic and is NOT driven to zero.
Combined energy + pressure closure is deferred to Phase 13C.

This is NOT a generic network solver.
Architecture is fixed: one evaporator, one condenser, one pump-head law.
No parallel evaporators, valves, manifolds, recuperators, or pre/post-heaters.
No new HX physics, no new correlations, no moving-boundary model.
No CoolProp, no PropertyBackend, no CorrelationRegistry resolution.

Public API
----------
PumpHeadCurve
PressureClosureConfig
MinimalPressureClosureCase
MinimalPressureClosureResult
solve_minimal_pressure_closure(case, config=None) -> MinimalPressureClosureResult

Architectural constraints
-------------------------
- No import of mpl_sim.network, mpl_sim.solvers, or mpl_sim.properties.
- No CoolProp call, no PropertyBackend construction, no registry resolution.
- FluidState carries only (P, h, identity); no property lookup occurs here.
- All closures/scenarios must be explicit; none are inferred automatically.
- Components are orchestrated through their public Phase 11R scenario API.
- The bisection is bounded and explicit; non-convergence is never silent.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

from mpl_sim.closed_loop._scalar_solve import _bisect_bounded
from mpl_sim.components import (
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState
from mpl_sim.correlations import ValidityStatus
from mpl_sim.hx_models import HXSolveResult

# ---------------------------------------------------------------------------
# PumpHeadCurve
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PumpHeadCurve:
    """Explicit pump-head law — Phase 13B.

    Represents a simple deterministic pump curve with no hidden physical
    defaults.  Two modes are supported:

    Constant head (slope_Pa_s_kg = 0, the default):
        ΔP_pump = head_Pa

    Linear curve:
        ΔP_pump(mdot) = head_Pa - slope_Pa_s_kg * mdot

    A positive slope means pump head decreases with increasing mass flow,
    which is the typical behaviour for a centrifugal pump curve.

    Fields
    ------
    head_Pa       : pump head at zero flow [Pa]; must be finite.
    slope_Pa_s_kg : linear slope [Pa·s/kg]; must be finite.  Default: 0.0
                    (constant head regardless of mass flow).

    Validation
    ----------
    - head_Pa must be finite (nan and inf are rejected).
    - slope_Pa_s_kg must be finite (nan and inf are rejected).
    """

    head_Pa: float
    slope_Pa_s_kg: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.head_Pa):
            raise ValueError(f"PumpHeadCurve.head_Pa must be finite; got {self.head_Pa!r}")
        if not math.isfinite(self.slope_Pa_s_kg):
            raise ValueError(
                f"PumpHeadCurve.slope_Pa_s_kg must be finite; got {self.slope_Pa_s_kg!r}"
            )

    def evaluate(self, mdot: float) -> float:
        """Return pump head [Pa] at primary mass flow mdot [kg/s]."""
        return self.head_Pa - self.slope_Pa_s_kg * mdot


# ---------------------------------------------------------------------------
# PressureClosureConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PressureClosureConfig:
    """Explicit solver configuration for the minimal pressure closure solver.

    Fields
    ------
    max_iter  : maximum number of bisection steps; must be a plain int >= 1;
                bool and float values are rejected explicitly.  Default: 50.
    tolerance : pressure residual convergence tolerance [Pa]; bisection stops
                when abs(pump_head - dP_total) <= tolerance.
                Must be finite and strictly positive.  Default: 1.0.

    Validation
    ----------
    - max_iter must be a non-bool int and >= 1.
    - tolerance must be finite and > 0.
    """

    max_iter: int = 50
    tolerance: float = 1.0  # [Pa]

    def __post_init__(self) -> None:
        if isinstance(self.max_iter, bool) or not isinstance(self.max_iter, int):
            raise ValueError(
                f"PressureClosureConfig.max_iter must be an int (not bool or float); "
                f"got {self.max_iter!r}"
            )
        if self.max_iter < 1:
            raise ValueError(f"PressureClosureConfig.max_iter must be >= 1; got {self.max_iter!r}")
        if not math.isfinite(self.tolerance) or self.tolerance <= 0:
            raise ValueError(
                f"PressureClosureConfig.tolerance must be finite and > 0; "
                f"got {self.tolerance!r}"
            )


# ---------------------------------------------------------------------------
# MinimalPressureClosureCase
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalPressureClosureCase:
    """Fixed-architecture minimal pressure closure case — Phase 13B.

    Defines a one-variable pressure-closure solve for the path:

        reference_state → evaporator → condenser

    The unknown is the primary mass flow rate primary_mdot [kg/s].
    The solved condition is:

        pump_head(mdot) - dP_total(mdot) = 0   (pressure loop closure)

    where:

        dP_total = dP_evap(mdot) + dP_cond(mdot)

    Formulation
    -----------
    - The evaporator is evaluated at each trial mdot with the fixed
      reference_state and the supplied evap_scenario, with only mass flux G
      replaced by mdot / evap_flow_area.
    - The condenser is evaluated at each trial mdot using the evaporator
      outlet state and the supplied cond_scenario, with only mass flux G
      replaced by mdot / cond_flow_area. No BC fields are replaced.
    - The pump-head law is explicit via PumpHeadCurve.
    - The caller supplies an explicit bracket mdot_bounds = (lo, hi).
      The solver validates that r(lo) and r(hi) have opposite signs.

    This is a pressure-ONLY closure (Option A).  Energy residual
    h_return - h_reference is computed at the solution and reported as a
    diagnostic only.  It is NOT driven to zero by this solver.

    This is NOT a generic network solver.  The architecture is fixed at one
    evaporator and one condenser.  Pressure closure does not solve parallel
    branches, valves, manifolds, or arbitrary topologies.

    Fields
    ------
    reference_state : primary fluid inlet / reference state (P, h, identity)
    pump_head_curve : explicit pump-head law (PumpHeadCurve value object)
    evap_component  : configured EvaporatorComponent (not mutated during solve)
    evap_scenario   : EvaporatorScenarioBinding with explicit dp_primary
    evap_flow_area  : primary evaporator flow area [m^2], used to set
                      trial mass flux G = primary_mdot / evap_flow_area
    cond_component  : configured CondenserComponent (not mutated during solve)
    cond_scenario   : CondenserScenarioBinding with explicit dp_primary
    cond_flow_area  : primary condenser flow area [m^2], used to set
                      trial mass flux G = primary_mdot / cond_flow_area
    mdot_bounds     : explicit bracket (lo, hi) for primary_mdot [kg/s];
                      both values must be finite, lo > 0, and lo < hi;
                      the solver checks sign change before bisecting

    Validation (raises ValueError on construction)
    ----------
    - mdot_bounds[0] and mdot_bounds[1] must be finite.
    - mdot_bounds[0] must be > 0 (mass flow is always positive).
    - mdot_bounds[0] must be strictly less than mdot_bounds[1].
    - both flow areas must be finite and > 0.
    - both scenarios must provide an explicit dp_primary closure.
    """

    reference_state: FluidState
    pump_head_curve: PumpHeadCurve
    evap_component: EvaporatorComponent
    evap_scenario: EvaporatorScenarioBinding
    evap_flow_area: float
    cond_component: CondenserComponent
    cond_scenario: CondenserScenarioBinding
    cond_flow_area: float
    mdot_bounds: tuple[float, float]

    def __post_init__(self) -> None:
        for name, area in (
            ("evap_flow_area", self.evap_flow_area),
            ("cond_flow_area", self.cond_flow_area),
        ):
            if not math.isfinite(area) or area <= 0.0:
                raise ValueError(
                    f"MinimalPressureClosureCase.{name} must be finite and > 0; got {area!r}"
                )
        if self.evap_scenario.dp_primary is None:
            raise ValueError(
                "MinimalPressureClosureCase.evap_scenario.dp_primary is required "
                "for pressure closure"
            )
        if self.cond_scenario.dp_primary is None:
            raise ValueError(
                "MinimalPressureClosureCase.cond_scenario.dp_primary is required "
                "for pressure closure"
            )
        lo, hi = self.mdot_bounds
        if not math.isfinite(lo) or not math.isfinite(hi):
            raise ValueError(
                f"MinimalPressureClosureCase.mdot_bounds must be two finite values; "
                f"got ({lo!r}, {hi!r})"
            )
        if lo <= 0:
            raise ValueError(
                f"MinimalPressureClosureCase.mdot_bounds[0] must be > 0 "
                f"(mass flow is strictly positive); got {lo!r}"
            )
        if lo >= hi:
            raise ValueError(
                f"MinimalPressureClosureCase.mdot_bounds[0] must be < mdot_bounds[1]; "
                f"got ({lo!r}, {hi!r})"
            )


# ---------------------------------------------------------------------------
# MinimalPressureClosureResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalPressureClosureResult:
    """Result from a minimal pressure closure solve — Phase 13B.

    Fields
    ------
    converged            : True if abs(pressure_residual) <= config.tolerance
    iterations           : number of bisection steps performed (0 for
                           endpoint roots; each midpoint evaluation counts 1)
    evaluations          : number of complete evaporator+condenser evaluations;
                           includes both bracket endpoints
    pressure_residual    : pump_head - dP_total at the returned solution [Pa];
                           near zero (within tolerance) when converged=True
    solved_primary_mdot  : primary mass flow rate at the solution [kg/s]
    pump_head            : pump_head_curve.evaluate(solved_primary_mdot) [Pa]
    dP_evap              : primary pressure drop across the evaporator [Pa]
    dP_cond              : primary pressure drop across the condenser [Pa]
    dP_total             : dP_evap + dP_cond [Pa]
    evap_result          : full HXSolveResult from the evaporator at solution
    cond_result          : full HXSolveResult from the condenser at solution
    reference_state      : supplied reference / inlet FluidState
    state_after_evap     : primary FluidState after the evaporator (cond inlet)
    return_state         : primary FluidState after the condenser
    h_reference          : reference enthalpy [J/kg]
    h_return             : primary enthalpy at loop return [J/kg]
    energy_residual      : h_return - h_reference [J/kg] — diagnostic only;
                           NOT driven to zero by Phase 13B (Option A).
                           Combined energy + pressure closure: Phase 13C.
    warnings             : non-IN_ENVELOPE correlation verdict messages
                           (empty when all invoked correlations are in-envelope)

    Notes
    -----
    - pressure_residual and dP_total are the authoritative pressure outputs.
    - energy_residual is always reported and never suppressed, even when
      it is non-zero.  This makes the energy imbalance explicit to the caller.
    - dP_total = dP_evap + dP_cond is always exact (no approximation).
    """

    converged: bool
    iterations: int
    evaluations: int
    pressure_residual: float
    solved_primary_mdot: float
    pump_head: float
    dP_evap: float
    dP_cond: float
    dP_total: float
    evap_result: HXSolveResult
    cond_result: HXSolveResult
    reference_state: FluidState
    state_after_evap: FluidState
    return_state: FluidState
    h_reference: float
    h_return: float
    energy_residual: float
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# solve_minimal_pressure_closure
# ---------------------------------------------------------------------------


def solve_minimal_pressure_closure(
    case: MinimalPressureClosureCase,
    config: PressureClosureConfig | None = None,
) -> MinimalPressureClosureResult:
    """Solve the minimal pressure closure — Phase 13B.

    Finds primary_mdot such that:

        pump_head(mdot) - dP_total(mdot) = 0

    where:

        dP_total = dP_evap(mdot) + dP_cond(mdot)

    Uses bounded bisection over the explicit caller-supplied mdot_bounds
    bracket.

    This is a pressure-only closure (Option A).  Energy closure is NOT
    performed.  energy_residual = h_return - h_reference is computed at the
    solution and reported as a diagnostic only; it is not driven to zero.

    Parameters
    ----------
    case   : MinimalPressureClosureCase — fully specified loop case
    config : PressureClosureConfig | None — solver settings; defaults to
             PressureClosureConfig() if None

    Returns
    -------
    MinimalPressureClosureResult

    Raises
    ------
    ValueError
        - if mdot_bounds does not enclose a root (same-sign residuals at both
          bracket endpoints)
    """
    if config is None:
        config = PressureClosureConfig()

    # Capture last component evaluations and count complete loop evaluations.
    # Using lists as single-element mutable cells avoids the nonlocal keyword
    # across the nested function boundary.
    _last_evap: list[HXSolveResult | None] = [None]
    _last_cond: list[HXSolveResult | None] = [None]
    _evaluations = [0]

    def _pressure_residual(mdot: float) -> float:
        evap_geom_scalars = dict(case.evap_scenario.geom_scalars)
        evap_geom_scalars["G"] = mdot / case.evap_flow_area
        evap_scenario = dataclasses.replace(
            case.evap_scenario,
            geom_scalars=evap_geom_scalars,
        )
        evap_r = case.evap_component.evaluate_scenario(case.reference_state, mdot, evap_scenario)
        cond_geom_scalars = dict(case.cond_scenario.geom_scalars)
        cond_geom_scalars["G"] = mdot / case.cond_flow_area
        cond_scenario = dataclasses.replace(
            case.cond_scenario,
            geom_scalars=cond_geom_scalars,
        )
        cond_r = case.cond_component.evaluate_scenario(
            evap_r.primary_state_out, mdot, cond_scenario
        )
        _evaluations[0] += 1
        _last_evap[0] = evap_r
        _last_cond[0] = cond_r
        dP_tot = evap_r.dP_primary + cond_r.dP_primary
        return case.pump_head_curve.evaluate(mdot) - dP_tot

    # --- Evaluate bracket endpoints. ---
    mdot_lo, mdot_hi = case.mdot_bounds
    r_lo = _pressure_residual(mdot_lo)
    saved_evap_lo: HXSolveResult = _last_evap[0]  # type: ignore[assignment]
    saved_cond_lo: HXSolveResult = _last_cond[0]  # type: ignore[assignment]
    r_hi = _pressure_residual(mdot_hi)
    saved_evap_hi: HXSolveResult = _last_evap[0]  # type: ignore[assignment]
    saved_cond_hi: HXSolveResult = _last_cond[0]  # type: ignore[assignment]

    if r_lo * r_hi > 0:
        raise ValueError(
            f"solve_minimal_pressure_closure: bracket [{mdot_lo!r}, {mdot_hi!r}] does "
            f"not enclose a root; r(lo)={r_lo:.6g} Pa, r(hi)={r_hi:.6g} Pa have the "
            f"same sign. Widen or correct the mdot_bounds bracket."
        )

    # Pre-set the captured component results for the endpoint-root case.
    # _bisect_bounded returns immediately for endpoint roots without calling
    # _pressure_residual, so _last_evap/_last_cond must already hold the
    # correct values before calling it.
    if abs(r_lo) <= config.tolerance:
        _last_evap[0] = saved_evap_lo
        _last_cond[0] = saved_cond_lo
    elif abs(r_hi) <= config.tolerance:
        _last_evap[0] = saved_evap_hi
        _last_cond[0] = saved_cond_hi
    # else: each midpoint call updates _last_evap[0] and _last_cond[0].

    # --- Bisect (uses shared private utility). ---
    bres = _bisect_bounded(
        _pressure_residual,
        mdot_lo,
        r_lo,
        mdot_hi,
        r_hi,
        config.max_iter,
        config.tolerance,
    )

    final_evap: HXSolveResult = _last_evap[0]  # type: ignore[assignment]
    final_cond: HXSolveResult = _last_cond[0]  # type: ignore[assignment]

    # --- Assemble result. ---
    solved_mdot = bres.x
    pump_h = case.pump_head_curve.evaluate(solved_mdot)
    dP_evap = final_evap.dP_primary
    dP_cond = final_cond.dP_primary
    dP_total = dP_evap + dP_cond

    state_after_evap = final_evap.primary_state_out
    return_state = final_cond.primary_state_out
    h_reference = case.reference_state.h
    h_return = return_state.h
    energy_residual = h_return - h_reference  # diagnostic only; NOT solved

    warnings: list[str] = []
    for co in final_evap.verdicts + final_cond.verdicts:
        if co.verdict.status is not ValidityStatus.IN_ENVELOPE:
            note = f"{co.metadata.name}: {co.verdict.status.name}"
            if co.verdict.detail:
                note += f" — {co.verdict.detail}"
            warnings.append(note)

    return MinimalPressureClosureResult(
        converged=bres.converged,
        iterations=bres.iterations,
        evaluations=_evaluations[0],
        pressure_residual=bres.residual,
        solved_primary_mdot=solved_mdot,
        pump_head=pump_h,
        dP_evap=dP_evap,
        dP_cond=dP_cond,
        dP_total=dP_total,
        evap_result=final_evap,
        cond_result=final_cond,
        reference_state=case.reference_state,
        state_after_evap=state_after_evap,
        return_state=return_state,
        h_reference=h_reference,
        h_return=h_return,
        energy_residual=energy_residual,
        warnings=tuple(warnings),
    )
