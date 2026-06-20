"""Minimal closed MPL solver — Phase 13A.

Implements a fixed-architecture one-variable energy closure for a
reference → evaporator → condenser → return path.

Solved unknown: condenser heat rate Q_cond [W] (via FixedHeatRate BC).
Solved condition: h_return = h_reference  (energy loop closure).
Solver method: bisection over an explicit caller-supplied bracket.

This is NOT a generic network solver.
Architecture is fixed: one evaporator, one condenser, one mass flow.
Pressure closure is NOT implemented here (deferred to Phase 13B).
The pressure-drop accumulation is reported as a diagnostic only.

Public API
----------
ClosedLoopSolveConfig
MinimalClosedMPLCase
MinimalClosedMPLResult
solve_minimal_closed_mpl(case, config=None) -> MinimalClosedMPLResult

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
# ClosedLoopSolveConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClosedLoopSolveConfig:
    """Explicit solver configuration for the minimal closed MPL solver.

    Fields
    ------
    max_iter  : maximum number of bisection steps; must be a plain int >= 1;
                bool and float values are rejected explicitly.  Default: 50.
    tolerance : energy residual convergence tolerance [J/kg]; bisection stops
                when abs(h_return - h_reference) <= tolerance.
                Must be finite and strictly positive.  Default: 1e-6.

    Validation
    ----------
    - max_iter must be a non-bool int and >= 1.
    - tolerance must be finite and > 0.
    """

    max_iter: int = 50
    tolerance: float = 1e-6

    def __post_init__(self) -> None:
        if isinstance(self.max_iter, bool) or not isinstance(self.max_iter, int):
            raise ValueError(
                f"ClosedLoopSolveConfig.max_iter must be an int (not bool or float); "
                f"got {self.max_iter!r}"
            )
        if self.max_iter < 1:
            raise ValueError(f"ClosedLoopSolveConfig.max_iter must be >= 1; got {self.max_iter!r}")
        if not math.isfinite(self.tolerance) or self.tolerance <= 0:
            raise ValueError(
                f"ClosedLoopSolveConfig.tolerance must be finite and > 0; "
                f"got {self.tolerance!r}"
            )


# ---------------------------------------------------------------------------
# MinimalClosedMPLCase
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalClosedMPLCase:
    """Fixed-architecture minimal closed MPL loop case — Phase 13A.

    Defines a one-variable energy-closure solve for the path:

        reference_state → evaporator → condenser → return_state

    The unknown is the condenser heat rate Q_cond [W].  The solve condition is:

        h_return = h_reference   (energy loop closure)

    Formulation
    -----------
    - The evaporator is evaluated once with the fixed reference_state and
      primary_mdot.  Its scenario is not changed during solving.
    - The condenser scenario template must use FixedHeatRate as secondary_bc.
      The solver replaces only the Q value of that BC at each bisection step;
      all other condenser scenario fields remain unchanged.
    - The caller must supply an explicit bracket q_cond_bounds = (lo, hi) that
      encloses the root.  The solver validates that r(lo) and r(hi) have
      opposite signs.

    This is NOT a generic network solver.  The architecture is fixed at one
    evaporator and one condenser.  Pressure closure is not implemented; dP_total
    is a diagnostic accumulation only.

    Fields
    ------
    reference_state : primary fluid inlet / reference state (P, h, identity)
    primary_mdot    : primary mass flow rate [kg/s]; must be finite and > 0
    evap_component  : configured EvaporatorComponent (not mutated during solve)
    evap_scenario   : EvaporatorScenarioBinding (not mutated during solve)
    cond_component  : configured CondenserComponent (not mutated during solve)
    cond_scenario   : CondenserScenarioBinding template; secondary_bc MUST be
                      FixedHeatRate; the Q is replaced by the solver at each step
    q_cond_bounds   : explicit bracket (lo, hi) for the condenser Q_cond [W];
                      both values must be finite and lo < hi; the solver checks
                      sign change before bisecting

    Validation (raises ValueError on construction)
    ----------
    - primary_mdot must be finite and > 0.
    - q_cond_bounds[0] and q_cond_bounds[1] must be finite.
    - q_cond_bounds[0] must be strictly less than q_cond_bounds[1].
    """

    reference_state: FluidState
    primary_mdot: float
    evap_component: EvaporatorComponent
    evap_scenario: EvaporatorScenarioBinding
    cond_component: CondenserComponent
    cond_scenario: CondenserScenarioBinding
    q_cond_bounds: tuple[float, float]

    def __post_init__(self) -> None:
        if not math.isfinite(self.primary_mdot) or self.primary_mdot <= 0:
            raise ValueError(
                f"MinimalClosedMPLCase.primary_mdot must be finite and > 0; "
                f"got {self.primary_mdot!r}"
            )
        lo, hi = self.q_cond_bounds
        if not math.isfinite(lo) or not math.isfinite(hi):
            raise ValueError(
                f"MinimalClosedMPLCase.q_cond_bounds must be two finite values; "
                f"got ({lo!r}, {hi!r})"
            )
        if lo >= hi:
            raise ValueError(
                f"MinimalClosedMPLCase.q_cond_bounds[0] must be < q_cond_bounds[1]; "
                f"got ({lo!r}, {hi!r})"
            )


# ---------------------------------------------------------------------------
# MinimalClosedMPLResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MinimalClosedMPLResult:
    """Result from a minimal closed MPL energy-closure solve — Phase 13A.

    Fields
    ------
    converged        : True if abs(energy_residual) <= config.tolerance at the
                       returned solution; False if max_iter was reached first
    iterations       : number of bisection steps performed (bracket evaluations
                       are not counted; only the bisection loop steps are counted)
    residual         : energy residual at the returned solution [J/kg]
                       = h_return - h_reference
                       Near zero (within tolerance) when converged=True
    energy_residual  : identical to residual [J/kg]; provided as a named field
                       so callers can reference it without ambiguity
    solved_q_cond    : condenser heat rate at the (approximate) solution [W]
                       This is the midpoint from the last bisection step
    evap_result      : full HXSolveResult from the evaporator evaluation
    cond_result      : full HXSolveResult from the condenser at solved_q_cond
    reference_state  : supplied reference / inlet FluidState
    state_after_evap : primary FluidState after the evaporator (cond inlet)
    return_state     : primary FluidState after the condenser (loop return)
    h_reference      : reference enthalpy [J/kg]
    h_after_evap     : primary enthalpy after the evaporator [J/kg]
    h_return         : primary enthalpy at loop return [J/kg]
    net_Q            : Q_evap + Q_cond [W]; near zero when converged=True
    net_dh           : h_return - h_reference [J/kg]; near zero when converged=True
    dP_total         : dP_evap + dP_cond [Pa] — diagnostic accumulation only;
                       no pressure closure is performed or claimed
    warnings         : non-IN_ENVELOPE correlation verdict messages (empty when
                       all invoked correlations are in-envelope)

    Notes
    -----
    - Pressure closure is NOT implemented in Phase 13A.  dP_total is a
      diagnostic only; it is not driven to zero by this solver.
    - net_Q and net_dh are always reported, never suppressed, so the caller
      can verify loop balance independent of the converged flag.
    """

    converged: bool
    iterations: int
    residual: float
    energy_residual: float
    solved_q_cond: float
    evap_result: HXSolveResult
    cond_result: HXSolveResult
    reference_state: FluidState
    state_after_evap: FluidState
    return_state: FluidState
    h_reference: float
    h_after_evap: float
    h_return: float
    net_Q: float
    net_dh: float
    dP_total: float
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# solve_minimal_closed_mpl
# ---------------------------------------------------------------------------


def solve_minimal_closed_mpl(
    case: MinimalClosedMPLCase,
    config: ClosedLoopSolveConfig | None = None,
) -> MinimalClosedMPLResult:
    """Solve the minimal closed MPL energy closure — Phase 13A.

    Finds Q_cond such that h_return = h_reference using bounded bisection.

    The evaporator is evaluated once with the fixed reference state and mass
    flow.  The condenser is re-evaluated at each bisection step with a trial
    Q_cond replacing the FixedHeatRate BC value.

    Pressure closure is NOT performed.  dP_total is accumulated and reported
    as a diagnostic only.

    Parameters
    ----------
    case   : MinimalClosedMPLCase — fully specified loop case
    config : ClosedLoopSolveConfig | None — solver settings; defaults to
             ClosedLoopSolveConfig() if None

    Returns
    -------
    MinimalClosedMPLResult

    Raises
    ------
    ValueError
        - if case.cond_scenario.secondary_bc is not FixedHeatRate
        - if the bracket q_cond_bounds does not enclose a root (same-sign residuals)
    """
    if config is None:
        config = ClosedLoopSolveConfig()

    # --- Validate condenser BC type. ---
    if not isinstance(case.cond_scenario.secondary_bc, FixedHeatRate):
        raise ValueError(
            f"solve_minimal_closed_mpl: cond_scenario.secondary_bc must be "
            f"FixedHeatRate for Phase 13A; got "
            f"{type(case.cond_scenario.secondary_bc).__name__!r}. "
            f"Other condenser BC types are deferred to future phases."
        )

    # --- Step 1: Evaluate the evaporator (fixed; not iterated). ---
    evap_result = case.evap_component.evaluate_scenario(
        case.reference_state,
        case.primary_mdot,
        case.evap_scenario,
    )
    state_after_evap = evap_result.primary_state_out
    h_reference = case.reference_state.h
    h_after_evap = state_after_evap.h

    # --- Step 2: Define residual function. ---
    def _energy_residual(q_cond: float) -> tuple[float, HXSolveResult]:
        trial_scenario = dataclasses.replace(
            case.cond_scenario,
            secondary_bc=FixedHeatRate(Q=q_cond),
        )
        cond_r = case.cond_component.evaluate_scenario(
            state_after_evap,
            case.primary_mdot,
            trial_scenario,
        )
        return cond_r.primary_state_out.h - h_reference, cond_r

    # --- Step 3: Evaluate bracket endpoints. ---
    q_lo, q_hi = case.q_cond_bounds
    r_lo, cond_lo = _energy_residual(q_lo)
    r_hi, cond_hi = _energy_residual(q_hi)

    if r_lo * r_hi > 0:
        raise ValueError(
            f"solve_minimal_closed_mpl: bracket [{q_lo!r}, {q_hi!r}] does not "
            f"enclose a root; r(lo)={r_lo:.6g}, r(hi)={r_hi:.6g} have the same "
            f"sign. Widen or correct the q_cond_bounds bracket."
        )

    # --- Step 4: Bisection. ---
    iterations = 0
    if abs(r_lo) <= config.tolerance:
        converged = True
        q_mid = q_lo
        r_mid = r_lo
        last_cond_result = cond_lo
    elif abs(r_hi) <= config.tolerance:
        converged = True
        q_mid = q_hi
        r_mid = r_hi
        last_cond_result = cond_hi
    else:
        converged = False
        q_mid = 0.5 * (q_lo + q_hi)
        r_mid = r_lo
        last_cond_result = cond_lo

        for _ in range(config.max_iter):
            q_mid = 0.5 * (q_lo + q_hi)
            r_mid, cond_result_trial = _energy_residual(q_mid)
            iterations += 1
            last_cond_result = cond_result_trial

            if abs(r_mid) <= config.tolerance:
                converged = True
                break

            if r_lo * r_mid < 0:
                q_hi = q_mid
                r_hi = r_mid
            else:
                q_lo = q_mid
                r_lo = r_mid

    # --- Step 5: Assemble result. ---
    final_cond_result = last_cond_result
    return_state = final_cond_result.primary_state_out
    h_return = return_state.h
    energy_residual = h_return - h_reference
    net_Q = evap_result.Q + final_cond_result.Q
    net_dh = h_return - h_reference
    dP_total = evap_result.dP_primary + final_cond_result.dP_primary

    warnings: list[str] = []
    for co in evap_result.verdicts + final_cond_result.verdicts:
        if co.verdict.status is not ValidityStatus.IN_ENVELOPE:
            note = f"{co.metadata.name}: {co.verdict.status.name}"
            if co.verdict.detail:
                note += f" — {co.verdict.detail}"
            warnings.append(note)

    return MinimalClosedMPLResult(
        converged=converged,
        iterations=iterations,
        residual=r_mid,
        energy_residual=energy_residual,
        solved_q_cond=q_mid,
        evap_result=evap_result,
        cond_result=final_cond_result,
        reference_state=case.reference_state,
        state_after_evap=state_after_evap,
        return_state=return_state,
        h_reference=h_reference,
        h_after_evap=h_after_evap,
        h_return=h_return,
        net_Q=net_Q,
        net_dh=net_dh,
        dP_total=dP_total,
        warnings=tuple(warnings),
    )
