"""Minimal coupled fixed-architecture closure — Phase 13D.

Implements a fixed-architecture two-variable coupled closure for a
reference → evaporator → condenser path.

Solved unknowns:
  Q_cond       — condenser heat rate [W]  (via FixedHeatRate BC)
  primary_mdot — primary mass flow [kg/s] (via pump-head balance)

Solved conditions:
  energy_residual   = h_return - h_reference = 0   (energy loop closure)
  pressure_residual = pump_head(mdot) - dP_total(mdot) = 0  (pressure closure)

Solver strategy: Option A — nested scalar bisection.
  Outer: bisect primary_mdot until pressure residual = 0.
  Inner: at each outer trial mdot, bisect Q_cond until energy residual = 0.

Both residuals are driven to zero.  Neither is diagnostic-only.

A ResidualVector (Phase 13C) is built at the solution for scaled convergence
diagnostics.

This is NOT a generic network solver.
Architecture is fixed: one evaporator, one condenser, one pump-head law.
No parallel evaporators, valves, manifolds, recuperators, or pre/post-heaters.
No new HX physics, no new correlations, no moving-boundary model.
No CoolProp, no PropertyBackend, no CorrelationRegistry resolution.

Public API
----------
CoupledClosureConfig
MinimalCoupledClosureCase
MinimalCoupledClosureResult
solve_minimal_coupled_closure(case, config=None) -> MinimalCoupledClosureResult

Architectural constraints
-------------------------
- No import of mpl_sim.network, mpl_sim.solvers, or mpl_sim.properties.
- No CoolProp call, no PropertyBackend construction, no registry resolution.
- FluidState carries only (P, h, identity); no property lookup occurs here.
- All closures/scenarios must be explicit; none are inferred automatically.
- Components are orchestrated through their public Phase 11R scenario API.
- Both bisections are bounded and explicit; non-convergence is never silent.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

from mpl_sim.closed_loop._scalar_solve import _bisect_bounded
from mpl_sim.closed_loop.pressure_solver import PumpHeadCurve
from mpl_sim.closed_loop.residuals import ResidualEvaluation, ResidualSpec, ResidualVector
from mpl_sim.components import (
    CondenserComponent,
    CondenserScenarioBinding,
    EvaporatorComponent,
    EvaporatorScenarioBinding,
)
from mpl_sim.core import FluidState
from mpl_sim.correlations import ValidityStatus
from mpl_sim.hx_models import FixedHeatRate, HXSolveResult

# ---------------------------------------------------------------------------
# CoupledClosureConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoupledClosureConfig:
    """Solver configuration for the minimal coupled closure — Phase 13D.

    Fields
    ------
    energy_tolerance   : inner bisection convergence threshold [J/kg]; stop when
                         abs(h_return - h_reference) <= energy_tolerance.
                         Must be finite, > 0, not bool.  Default: 1e-6.
    pressure_tolerance : outer bisection convergence threshold [Pa]; stop when
                         abs(pump_head - dP_total) <= pressure_tolerance.
                         Must be finite, > 0, not bool.  Default: 1.0.
    energy_scale       : characteristic enthalpy scale [J/kg] for ResidualVector
                         scaled norms.  Must be finite, > 0, not bool.  Default: 1000.0.
    pressure_scale     : characteristic pressure scale [Pa] for ResidualVector
                         scaled norms.  Must be finite, > 0, not bool.  Default: 100.0.
    inner_max_iter     : max bisection steps for the inner Q_cond solve; must be
                         a non-bool int >= 1.  Default: 50.
    outer_max_iter     : max bisection steps for the outer mdot solve; must be
                         a non-bool int >= 1.  Default: 50.

    Validation
    ----------
    - All four float fields must be non-bool, finite, and strictly > 0.
    - Both int fields must be a non-bool int and >= 1.
    """

    energy_tolerance: float = 1e-6
    pressure_tolerance: float = 1.0
    energy_scale: float = 1000.0
    pressure_scale: float = 100.0
    inner_max_iter: int = 50
    outer_max_iter: int = 50

    def __post_init__(self) -> None:
        for name, val in (
            ("energy_tolerance", self.energy_tolerance),
            ("pressure_tolerance", self.pressure_tolerance),
            ("energy_scale", self.energy_scale),
            ("pressure_scale", self.pressure_scale),
        ):
            if isinstance(val, bool):
                raise ValueError(f"CoupledClosureConfig.{name} must not be bool; got {val!r}")
            if not math.isfinite(val) or val <= 0:
                raise ValueError(f"CoupledClosureConfig.{name} must be finite and > 0; got {val!r}")
        for name, val in (
            ("inner_max_iter", self.inner_max_iter),
            ("outer_max_iter", self.outer_max_iter),
        ):
            if isinstance(val, bool) or not isinstance(val, int):
                raise ValueError(
                    f"CoupledClosureConfig.{name} must be an int (not bool or float); "
                    f"got {val!r}"
                )
            if val < 1:
                raise ValueError(f"CoupledClosureConfig.{name} must be >= 1; got {val!r}")


# ---------------------------------------------------------------------------
# MinimalCoupledClosureCase
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalCoupledClosureCase:
    """Fixed-architecture minimal coupled closure case — Phase 13D.

    Defines a two-variable coupled closure solve for the path:

        reference_state → evaporator → condenser → return_state

    Unknowns:
        Q_cond       — condenser heat rate [W]  (inner: energy closure)
        primary_mdot — primary mass flow [kg/s] (outer: pressure closure)

    Conditions solved simultaneously:
        energy_residual   = h_return - h_reference = 0
        pressure_residual = pump_head(mdot) - dP_total(mdot) = 0

    where:
        dP_total = dP_evap(mdot) + dP_cond(mdot)
        G_evap   = primary_mdot / evap_flow_area
        G_cond   = primary_mdot / cond_flow_area

    Solver strategy (Option A — nested scalar bisection)
    ----------------------------------------------------
    Outer bisection iterates over primary_mdot.  At each outer trial:
      1. Evaluate evaporator with G = mdot / evap_flow_area.
      2. Inner bisection: find Q_cond such that h_return = h_reference.
         Condenser is evaluated with G = mdot / cond_flow_area at each
         inner step; only Q in FixedHeatRate BC is varied.
      3. Pressure residual = pump_head(mdot) - (dP_evap + dP_cond) is
         returned to the outer bisection.
    The outer bisection converges when pressure residual ≤ pressure_tolerance.

    Fields
    ------
    reference_state : primary fluid inlet / reference state (P, h, identity)
    pump_head_curve : explicit pump-head law (PumpHeadCurve value object)
    evap_component  : configured EvaporatorComponent (not mutated during solve)
    evap_scenario   : EvaporatorScenarioBinding; dp_primary is required
    evap_flow_area  : primary evaporator flow area [m²]; finite and > 0
    cond_component  : configured CondenserComponent (not mutated during solve)
    cond_scenario   : CondenserScenarioBinding; secondary_bc must be
                      FixedHeatRate; dp_primary is required; the Q value is
                      replaced by the inner solver at each step
    cond_flow_area  : primary condenser flow area [m²]; finite and > 0
    q_cond_bounds   : explicit bracket (lo, hi) for Q_cond [W]; both must be
                      finite and lo < hi; must enclose the energy root for
                      all mdot values encountered during the outer solve
    mdot_bounds     : explicit bracket (lo, hi) for primary_mdot [kg/s];
                      both must be finite, lo > 0, lo < hi; must enclose the
                      pressure root

    Validation (raises ValueError on construction)
    ----------
    - evap_flow_area and cond_flow_area must be finite and > 0.
    - evap_scenario.dp_primary must not be None.
    - cond_scenario.dp_primary must not be None.
    - q_cond_bounds: both finite, lo < hi.
    - mdot_bounds: both finite, lo > 0, lo < hi.

    Note: cond_scenario.secondary_bc must be FixedHeatRate; this is validated
    at solve time (not at case construction) so that the type error points
    clearly at the solver entry point.
    """

    reference_state: FluidState
    pump_head_curve: PumpHeadCurve
    evap_component: EvaporatorComponent
    evap_scenario: EvaporatorScenarioBinding
    evap_flow_area: float
    cond_component: CondenserComponent
    cond_scenario: CondenserScenarioBinding
    cond_flow_area: float
    q_cond_bounds: tuple[float, float]
    mdot_bounds: tuple[float, float]

    def __post_init__(self) -> None:
        for name, area in (
            ("evap_flow_area", self.evap_flow_area),
            ("cond_flow_area", self.cond_flow_area),
        ):
            if isinstance(area, bool) or not math.isfinite(area) or area <= 0.0:
                raise ValueError(
                    f"MinimalCoupledClosureCase.{name} must be finite, > 0, "
                    f"and not bool; got {area!r}"
                )
        if self.evap_scenario.dp_primary is None:
            raise ValueError(
                "MinimalCoupledClosureCase.evap_scenario.dp_primary is required "
                "for pressure closure"
            )
        if self.cond_scenario.dp_primary is None:
            raise ValueError(
                "MinimalCoupledClosureCase.cond_scenario.dp_primary is required "
                "for pressure closure"
            )
        q_lo, q_hi = self.q_cond_bounds
        if not math.isfinite(q_lo) or not math.isfinite(q_hi):
            raise ValueError(
                f"MinimalCoupledClosureCase.q_cond_bounds must be two finite values; "
                f"got ({q_lo!r}, {q_hi!r})"
            )
        if q_lo >= q_hi:
            raise ValueError(
                f"MinimalCoupledClosureCase.q_cond_bounds[0] must be < q_cond_bounds[1]; "
                f"got ({q_lo!r}, {q_hi!r})"
            )
        mdot_lo, mdot_hi = self.mdot_bounds
        if not math.isfinite(mdot_lo) or not math.isfinite(mdot_hi):
            raise ValueError(
                f"MinimalCoupledClosureCase.mdot_bounds must be two finite values; "
                f"got ({mdot_lo!r}, {mdot_hi!r})"
            )
        if mdot_lo <= 0:
            raise ValueError(
                f"MinimalCoupledClosureCase.mdot_bounds[0] must be > 0 "
                f"(mass flow is strictly positive); got {mdot_lo!r}"
            )
        if mdot_lo >= mdot_hi:
            raise ValueError(
                f"MinimalCoupledClosureCase.mdot_bounds[0] must be < mdot_bounds[1]; "
                f"got ({mdot_lo!r}, {mdot_hi!r})"
            )


# ---------------------------------------------------------------------------
# MinimalCoupledClosureResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalCoupledClosureResult:
    """Result from a minimal coupled closure solve — Phase 13D.

    Fields
    ------
    converged               : True if BOTH outer pressure bisection converged
                              (abs(pressure_residual) <= pressure_tolerance) AND
                              the final inner energy bisection converged
                              (abs(energy_residual) <= energy_tolerance)
    outer_iterations        : outer bisection step count (0 for endpoint roots)
    inner_iterations_total  : total inner bisection steps across all outer calls
    inner_evaluations_total : total inner HX evaluations (includes bracket
                              endpoints at each outer call)
    solved_q_cond           : condenser heat rate at the solution [W]
    solved_primary_mdot     : primary mass flow rate at the solution [kg/s]
    energy_residual         : h_return - h_reference at the solution [J/kg];
                              near zero (within energy_tolerance) when converged
    pressure_residual       : pump_head - dP_total at the solution [Pa];
                              near zero (within pressure_tolerance) when converged
    residual_vector         : ResidualVector with energy and pressure evaluations
                              using the configured scales; use .max_abs_scaled(),
                              .l2_scaled(), .is_converged(tol) for diagnostics
    max_abs_scaled          : residual_vector.max_abs_scaled() — L-infinity norm
                              of the scaled residuals at the solution
    pump_head               : pump_head_curve.evaluate(solved_primary_mdot) [Pa]
    dP_evap                 : primary pressure drop across the evaporator [Pa]
    dP_cond                 : primary pressure drop across the condenser [Pa]
    dP_total                : dP_evap + dP_cond [Pa]
    evap_result             : full HXSolveResult from the evaporator at solution
    cond_result             : full HXSolveResult from the condenser at solution
    reference_state         : supplied reference / inlet FluidState
    state_after_evap        : primary FluidState after the evaporator (cond inlet)
    return_state            : primary FluidState after the condenser (loop return)
    h_reference             : reference enthalpy [J/kg]
    h_return                : primary enthalpy at loop return [J/kg]
    warnings                : non-IN_ENVELOPE correlation verdict messages
                              (empty when all invoked correlations are in-envelope)

    Notes
    -----
    - Both residuals are always reported and never suppressed, even when
      converged=False.  This makes both imbalances visible to the caller.
    - dP_total = dP_evap + dP_cond is always exact (no approximation).
    - pump_head ≈ dP_total within pressure_tolerance when converged=True.
    - energy_residual ≈ 0 within energy_tolerance when converged=True.
    """

    converged: bool
    outer_iterations: int
    inner_iterations_total: int
    inner_evaluations_total: int
    solved_q_cond: float
    solved_primary_mdot: float
    energy_residual: float
    pressure_residual: float
    residual_vector: ResidualVector
    max_abs_scaled: float
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
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# solve_minimal_coupled_closure
# ---------------------------------------------------------------------------


def solve_minimal_coupled_closure(
    case: MinimalCoupledClosureCase,
    config: CoupledClosureConfig | None = None,
) -> MinimalCoupledClosureResult:
    """Solve the minimal coupled fixed-architecture closure — Phase 13D.

    Finds (Q_cond, primary_mdot) such that:

        h_return - h_reference = 0   (energy closure)
        pump_head(mdot) - dP_total(mdot) = 0   (pressure closure)

    where:
        dP_total = dP_evap(mdot) + dP_cond(mdot)
        G_evap   = primary_mdot / evap_flow_area
        G_cond   = primary_mdot / cond_flow_area

    Solver strategy: nested scalar bisection (Option A).
      Outer: bisect primary_mdot for pressure residual = 0.
      Inner: at each outer trial mdot, bisect Q_cond for energy residual = 0.

    Parameters
    ----------
    case   : MinimalCoupledClosureCase — fully specified loop case
    config : CoupledClosureConfig | None — solver settings; defaults to
             CoupledClosureConfig() if None

    Returns
    -------
    MinimalCoupledClosureResult

    Raises
    ------
    ValueError
        - if case.cond_scenario.secondary_bc is not FixedHeatRate
        - if the outer mdot bracket does not enclose a pressure root
        - if the inner Q_cond bracket does not enclose an energy root at any
          outer trial mdot (indicates q_cond_bounds must be widened)
    """
    if config is None:
        config = CoupledClosureConfig()

    if not isinstance(case.cond_scenario.secondary_bc, FixedHeatRate):
        raise ValueError(
            f"solve_minimal_coupled_closure: cond_scenario.secondary_bc must be "
            f"FixedHeatRate for Phase 13D; got "
            f"{type(case.cond_scenario.secondary_bc).__name__!r}. "
            f"Other condenser BC types are deferred to future phases."
        )

    h_reference = case.reference_state.h
    q_lo, q_hi = case.q_cond_bounds

    # Mutable cells for cross-call state (avoids nonlocal across closures).
    _last_evap: list[HXSolveResult | None] = [None]
    _last_cond: list[HXSolveResult | None] = [None]
    _last_q_cond: list[float] = [q_lo]
    _last_energy_residual: list[float] = [math.nan]
    _last_state_after_evap: list[FluidState | None] = [None]
    _inner_converged: list[bool] = [False]
    _inner_iterations_total: list[int] = [0]
    _inner_evaluations_total: list[int] = [0]

    def _outer_residual(mdot: float) -> float:
        # --- Step 1: Evaluate evaporator with trial mass flux. ---
        evap_geom_scalars = dict(case.evap_scenario.geom_scalars)
        evap_geom_scalars["G"] = mdot / case.evap_flow_area
        evap_scenario_trial = dataclasses.replace(
            case.evap_scenario,
            geom_scalars=evap_geom_scalars,
        )
        evap_r = case.evap_component.evaluate_scenario(
            case.reference_state, mdot, evap_scenario_trial
        )
        state_after_evap = evap_r.primary_state_out

        # --- Step 2: Inner energy closure — bisect Q_cond. ---
        _inner_cond: list[HXSolveResult | None] = [None]
        _inner_eval_count = [0]

        def _inner_energy(q_cond: float) -> float:
            cond_geom_scalars = dict(case.cond_scenario.geom_scalars)
            cond_geom_scalars["G"] = mdot / case.cond_flow_area
            cond_scenario_trial = dataclasses.replace(
                case.cond_scenario,
                geom_scalars=cond_geom_scalars,
                secondary_bc=FixedHeatRate(Q=q_cond),
            )
            cond_r = case.cond_component.evaluate_scenario(
                state_after_evap, mdot, cond_scenario_trial
            )
            _inner_cond[0] = cond_r
            _inner_eval_count[0] += 1
            return cond_r.primary_state_out.h - h_reference

        # Evaluate inner bracket endpoints.
        r_q_lo = _inner_energy(q_lo)
        saved_inner_cond_lo: HXSolveResult = _inner_cond[0]  # type: ignore[assignment]
        r_q_hi = _inner_energy(q_hi)
        saved_inner_cond_hi: HXSolveResult = _inner_cond[0]  # type: ignore[assignment]

        if r_q_lo * r_q_hi > 0:
            raise ValueError(
                f"solve_minimal_coupled_closure: inner Q_cond bracket "
                f"[{q_lo!r}, {q_hi!r}] does not enclose an energy root at "
                f"mdot={mdot!r}; r(lo)={r_q_lo:.6g} J/kg, "
                f"r(hi)={r_q_hi:.6g} J/kg have the same sign. "
                f"Widen or correct the q_cond_bounds bracket."
            )

        # Pre-set inner cond cell for inner endpoint-root cases.
        if abs(r_q_lo) <= config.energy_tolerance:
            _inner_cond[0] = saved_inner_cond_lo
        elif abs(r_q_hi) <= config.energy_tolerance:
            _inner_cond[0] = saved_inner_cond_hi

        inner_bres = _bisect_bounded(
            _inner_energy,
            q_lo,
            r_q_lo,
            q_hi,
            r_q_hi,
            config.inner_max_iter,
            config.energy_tolerance,
        )

        # Accumulate inner diagnostics.
        _inner_iterations_total[0] += inner_bres.iterations
        _inner_evaluations_total[0] += _inner_eval_count[0]
        _inner_converged[0] = inner_bres.converged

        # --- Step 3: Pressure residual from the energy-closed state. ---
        final_inner_cond: HXSolveResult = _inner_cond[0]  # type: ignore[assignment]
        dP_total = evap_r.dP_primary + final_inner_cond.dP_primary

        # Save state for result assembly at the outer solution.
        _last_evap[0] = evap_r
        _last_cond[0] = final_inner_cond
        _last_q_cond[0] = inner_bres.x
        _last_energy_residual[0] = inner_bres.residual
        _last_state_after_evap[0] = state_after_evap

        return case.pump_head_curve.evaluate(mdot) - dP_total

    # --- Evaluate outer bracket endpoints. ---
    mdot_lo, mdot_hi = case.mdot_bounds
    r_mdot_lo = _outer_residual(mdot_lo)
    saved_evap_lo: HXSolveResult = _last_evap[0]  # type: ignore[assignment]
    saved_cond_lo: HXSolveResult = _last_cond[0]  # type: ignore[assignment]
    saved_q_lo = _last_q_cond[0]
    saved_er_lo = _last_energy_residual[0]
    saved_sae_lo: FluidState = _last_state_after_evap[0]  # type: ignore[assignment]
    saved_ic_lo = _inner_converged[0]

    r_mdot_hi = _outer_residual(mdot_hi)
    saved_evap_hi: HXSolveResult = _last_evap[0]  # type: ignore[assignment]
    saved_cond_hi: HXSolveResult = _last_cond[0]  # type: ignore[assignment]
    saved_q_hi = _last_q_cond[0]
    saved_er_hi = _last_energy_residual[0]
    saved_sae_hi: FluidState = _last_state_after_evap[0]  # type: ignore[assignment]
    saved_ic_hi = _inner_converged[0]

    if r_mdot_lo * r_mdot_hi > 0:
        raise ValueError(
            f"solve_minimal_coupled_closure: outer mdot bracket "
            f"[{mdot_lo!r}, {mdot_hi!r}] does not enclose a pressure root; "
            f"r(lo)={r_mdot_lo:.6g} Pa, r(hi)={r_mdot_hi:.6g} Pa have the "
            f"same sign. Widen or correct the mdot_bounds bracket."
        )

    # Pre-set outer tracking cells for outer endpoint-root cases.
    # _bisect_bounded returns without calling _outer_residual for endpoint
    # roots, so the tracking cells must already hold the correct values.
    if abs(r_mdot_lo) <= config.pressure_tolerance:
        _last_evap[0] = saved_evap_lo
        _last_cond[0] = saved_cond_lo
        _last_q_cond[0] = saved_q_lo
        _last_energy_residual[0] = saved_er_lo
        _last_state_after_evap[0] = saved_sae_lo
        _inner_converged[0] = saved_ic_lo
    elif abs(r_mdot_hi) <= config.pressure_tolerance:
        _last_evap[0] = saved_evap_hi
        _last_cond[0] = saved_cond_hi
        _last_q_cond[0] = saved_q_hi
        _last_energy_residual[0] = saved_er_hi
        _last_state_after_evap[0] = saved_sae_hi
        _inner_converged[0] = saved_ic_hi

    # --- Outer bisection. ---
    outer_bres = _bisect_bounded(
        _outer_residual,
        mdot_lo,
        r_mdot_lo,
        mdot_hi,
        r_mdot_hi,
        config.outer_max_iter,
        config.pressure_tolerance,
    )

    # --- Assemble result. ---
    final_evap: HXSolveResult = _last_evap[0]  # type: ignore[assignment]
    final_cond: HXSolveResult = _last_cond[0]  # type: ignore[assignment]
    final_sae: FluidState = _last_state_after_evap[0]  # type: ignore[assignment]

    solved_mdot = outer_bres.x
    solved_q_cond = _last_q_cond[0]
    energy_residual = _last_energy_residual[0]
    pressure_residual = outer_bres.residual

    dP_evap = final_evap.dP_primary
    dP_cond = final_cond.dP_primary
    dP_total = dP_evap + dP_cond
    pump_h = case.pump_head_curve.evaluate(solved_mdot)

    return_state = final_cond.primary_state_out
    h_return = return_state.h

    converged = outer_bres.converged and _inner_converged[0]

    energy_spec = ResidualSpec(name="energy", unit="J/kg", scale=config.energy_scale)
    pressure_spec = ResidualSpec(name="pressure", unit="Pa", scale=config.pressure_scale)
    rv = ResidualVector(
        evaluations=(
            ResidualEvaluation(spec=energy_spec, value=energy_residual),
            ResidualEvaluation(spec=pressure_spec, value=pressure_residual),
        )
    )

    warnings: list[str] = []
    for co in final_evap.verdicts + final_cond.verdicts:
        if co.verdict.status is not ValidityStatus.IN_ENVELOPE:
            note = f"{co.metadata.name}: {co.verdict.status.name}"
            if co.verdict.detail:
                note += f" — {co.verdict.detail}"
            warnings.append(note)

    return MinimalCoupledClosureResult(
        converged=converged,
        outer_iterations=outer_bres.iterations,
        inner_iterations_total=_inner_iterations_total[0],
        inner_evaluations_total=_inner_evaluations_total[0],
        solved_q_cond=solved_q_cond,
        solved_primary_mdot=solved_mdot,
        energy_residual=energy_residual,
        pressure_residual=pressure_residual,
        residual_vector=rv,
        max_abs_scaled=rv.max_abs_scaled(),
        pump_head=pump_h,
        dP_evap=dP_evap,
        dP_cond=dP_cond,
        dP_total=dP_total,
        evap_result=final_evap,
        cond_result=final_cond,
        reference_state=case.reference_state,
        state_after_evap=final_sae,
        return_state=return_state,
        h_reference=h_reference,
        h_return=h_return,
        warnings=tuple(warnings),
    )
