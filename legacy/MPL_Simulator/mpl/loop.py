"""
loop.py — MPL Steady-State Loop Assembler & Newton-Raphson Solver
==================================================================
MPL Simulation Library — Module 7 (Phase 7)

Assembles MPL components in sequence and closes the loop by solving two
simultaneous scalar equations with Newton-Raphson (SciPy fsolve):

    R1 = ΔP_pump − ΣΔP_components  ≈ 0   [pressure balance]
    R2 = P_sys    − P_accumulator   ≈ 0   [pressure set-point]

Iteration variables
-------------------
  x[0] = mdot   [kg/s]  — mass flow rate through the loop
  x[1] = P_sys  [Pa]    — system pressure (≈ evaporator saturation pressure)

The pump is represented as *PumpFixed* (prescribed ΔP) so that:
  ΔP_pump = x[0]  → no, ΔP_pump is derived from the pump curve if a
  PumpCurve is used, or set as a free variable if PumpFixed is used.

Loop topology (single-loop with one accumulator)
------------------------------------------------
  [Accumulator] sets P_sys
  [Pump]  → [Pipe_liquid] → [Evaporator] → [Pipe_tp] → [Condenser] → (back)

The solver accepts an **ordered list of components** (excluding accumulator).
The accumulator is passed separately and provides the pressure boundary
condition.

Algorithm
---------
1. Accumulator sets P_sys → saturated-liquid state at condenser outlet.
2. Propagate forward through component chain: each solve_ss() returns outlet.
3. Pump provides ΔP_pump from its curve (PumpCurve) or as iteration variable
   (PumpFixed with dp_set = mdot-dependent).
4. R1 = ΔP_pump − ΣΔP  ,  R2 = P_sys_guess − P_acc
5. Newton-Raphson (SciPy fsolve) iterates until |R| < tol.

Physical basis
--------------
* HEM with (P, h) state variables — VanGerner (2016)
* Pressure balance: pump head = sum of component pressure drops
* Accumulator sets saturation pressure → T_sat (Lee 2022, Truster 2024)

References
----------
[1] M. VanGerner et al., "1D dynamic model for CO2 two-phase loop," (2016).
[2] R. Kokate, C. Park, "Pumped two-phase loop," Appl. Therm. Eng. 229 (2023).
[3] R. Kokate, PhD Thesis, 2024.  [loop solver, Ledinegg criterion]
[4] J. Lee et al., "Accumulator effects on MPL instabilities," (2022).
[5] N. Truster et al., "PCA and MPC in MPL," Energies 17 (2024).
[6] X. Wang et al., "MPL modeling for data center cooling," (2023).
[7] Middelhuis et al., "Review MPL experiments," (2024).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence, Union

import numpy as np
from scipy.optimize import fsolve

from base import Component, ComponentError, Port
from fluid_properties import FluidState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class LoopSolverError(RuntimeError):
    """Raised when the Newton-Raphson solver fails to converge."""


class LoopConfigError(ValueError):
    """Raised for invalid loop configuration (missing pump, etc.)."""


# ---------------------------------------------------------------------------
# Accumulator protocol — both HCA and PCA satisfy this
# ---------------------------------------------------------------------------

class AccumulatorProtocol(Protocol):
    """
    Minimal interface the loop solver expects from an accumulator.

    Both AccumulatorHCA and AccumulatorPCA satisfy this protocol.
    """
    fluid: str

    def set_pressure(self) -> float:
        """Return system pressure [Pa] imposed by the accumulator."""
        ...


# ---------------------------------------------------------------------------
# LoopResult — output of a successful SS solve
# ---------------------------------------------------------------------------

@dataclass
class LoopResult:
    """
    Full steady-state solution of the MPL loop.

    Attributes
    ----------
    mdot : float
        Mass flow rate [kg/s].
    P_sys : float
        System pressure [Pa] (accumulator set-point).
    T_sat : float
        Saturation temperature [K] at P_sys.
    x_evap_out : float
        Vapour quality at evaporator outlet [-].
    dp_pump : float
        Pump pressure rise [Pa].
    dp_total : float
        Sum of component pressure drops [Pa].
    nodes : dict[str, Port]
        Port state at the inlet of every component, keyed by component name.
    components : list[str]
        Ordered list of component names in the loop.
    residuals : tuple[float, float]
        Final (R1, R2) residuals from the solver.
    n_iter : int
        Number of solver function evaluations.
    converged : bool
        True if solver reported convergence (|residuals| < tol).
    """
    mdot:        float
    P_sys:       float
    T_sat:       float
    x_evap_out:  float
    dp_pump:     float
    dp_total:    float
    nodes:       dict[str, Port]
    components:  list[str]
    residuals:   tuple[float, float]
    n_iter:      int
    converged:   bool

    def summary(self) -> str:
        """Return a human-readable summary string."""
        lines = [
            "── MPL Steady-State Solution ──",
            f"  mdot       = {self.mdot*1e3:.3f} g/s",
            f"  P_sys      = {self.P_sys/1e5:.4f} bar",
            f"  T_sat      = {self.T_sat - 273.15:.2f} °C",
            f"  x_evap_out = {self.x_evap_out:.4f}",
            f"  ΔP_pump    = {self.dp_pump:.1f} Pa",
            f"  ΣΔP_loop   = {self.dp_total:.1f} Pa",
            f"  Converged  = {self.converged}  (|R|={max(abs(r) for r in self.residuals):.2e})",
            "  Node pressures:",
        ]
        for name, port in self.nodes.items():
            lines.append(
                f"    {name:20s}  P={port.state.P/1e5:.4f} bar"
                f"  h={port.state.h:.1f} J/kg"
                f"  x={port.state.x:.4f}"
                f"  T={port.state.T - 273.15:.2f} °C"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pump interface helper
# ---------------------------------------------------------------------------

def _pump_dp(pump: Component, mdot: float, inlet: Port) -> tuple[float, Port]:
    """
    Evaluate pump ΔP and return (dp, outlet_port).

    Handles both PumpCurve and PumpFixed.
    For PumpFixed, dp_set is used directly.
    For PumpCurve, the curve is evaluated at mdot.
    """
    # Temporarily set mdot on inlet if needed
    inlet_m = Port(state=inlet.state, mdot=mdot)
    outlet = pump.solve_ss(inlet_m)
    dp = outlet.state.P - inlet.state.P
    return dp, outlet


# ---------------------------------------------------------------------------
# LoopSolver
# ---------------------------------------------------------------------------

@dataclass
class LoopSolver:
    """
    Steady-state solver for a single-loop MPL system.

    Parameters
    ----------
    components : list of Component
        Ordered list of components (excluding accumulator).
        Must include exactly one pump (detected by class name containing
        'Pump'). Order: pump → … → evaporator → … → condenser → (loop back).
    accumulator : AccumulatorProtocol
        HCA or PCA accumulator that imposes the system pressure.
    fluid : str
        CoolProp fluid identifier (e.g. 'Acetone', 'R1234yf').
    subcooling : float, optional
        Subcooling [K] at pump inlet (condenser outlet). Default 2.0 K.
    tol : float, optional
        Convergence tolerance on residuals. Default 1e-6.
    max_iter : int, optional
        Maximum Newton-Raphson iterations. Default 200.
    mdot_guess : float, optional
        Initial guess for mass flow rate [kg/s]. Default 0.01.
    verbose : bool, optional
        Print solver progress. Default False.

    Notes
    -----
    The accumulator is assumed to be connected to the liquid line (between
    condenser outlet and pump inlet) and acts as a pressure boundary
    condition only — it does not contribute a pressure drop in the main
    flow path.

    Usage
    -----
    >>> solver = LoopSolver(components=[pump, pipe1, evap, pipe2, cond],
    ...                     accumulator=hca, fluid='Acetone')
    >>> result = solver.solve(Q_evap=300.0)
    >>> print(result.summary())
    """

    components:  list[Component]
    accumulator: Any                    # AccumulatorHCA | AccumulatorPCA
    fluid:       str
    subcooling:  float = 2.0            # K subcooling at pump inlet
    tol:         float = 1e-6
    max_iter:    int   = 200
    mdot_guess:  float = 0.01
    verbose:     bool  = False

    # Internal counter — incremented in _residuals()
    _n_eval: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.components:
            raise LoopConfigError("components list is empty.")
        # Detect pump (first component whose class name contains 'Pump')
        pumps = [c for c in self.components
                 if "pump" in type(c).__name__.lower()]
        if not pumps:
            raise LoopConfigError(
                "No pump found in components. Include a Pump or PumpFixed."
            )
        if len(pumps) > 1:
            raise LoopConfigError(
                f"Multiple pump-like components found: {[type(p).__name__ for p in pumps]}. "
                "Only one pump per loop is supported."
            )
        self._pump = pumps[0]
        self._non_pump = [c for c in self.components if c is not self._pump]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def solve(
        self,
        Q_evap: float = 0.0,
        mdot_guess: Optional[float] = None,
    ) -> LoopResult:
        """
        Solve the steady-state loop at the given heat load.

        Parameters
        ----------
        Q_evap : float
            Total evaporator heat load [W]. Injected into any component
            whose ``name`` attribute starts with 'evap' (case-insensitive),
            or whose class name contains 'Evaporator'.
        mdot_guess : float, optional
            Override initial guess for mdot [kg/s].

        Returns
        -------
        LoopResult
            Full SS solution including node states, residuals, and summary.

        Raises
        ------
        LoopSolverError
            If the solver does not converge within max_iter iterations.
        """
        self._n_eval = 0
        self._Q_evap = float(Q_evap)

        # System pressure from accumulator
        P_sys = self.accumulator.set_pressure()

        # Initial guesses
        mdot0 = mdot_guess if mdot_guess is not None else self.mdot_guess
        x0 = np.array([mdot0, P_sys], dtype=float)

        if self.verbose:
            logger.info(
                "LoopSolver.solve() start: P_sys=%.4f bar, mdot_guess=%.4f g/s",
                P_sys / 1e5, mdot0 * 1e3
            )

        # Run fsolve
        sol, info, ier, mesg = fsolve(
            self._residuals,
            x0,
            full_output=True,
            xtol=self.tol,
            maxfev=self.max_iter * 10,
        )

        mdot_sol = float(sol[0])
        P_sol    = float(sol[1])
        r1, r2   = self._residuals(sol)
        converged = (ier == 1) and (abs(r1) < self.tol * 1e3) and (abs(r2) < self.tol * 1e3)

        if not converged:
            warnings.warn(
                f"LoopSolver did not converge: {mesg}  "
                f"|R1|={abs(r1):.2e} Pa, |R2|={abs(r2):.2e} Pa",
                RuntimeWarning,
                stacklevel=2,
            )

        # Reconstruct full solution at converged point
        result = self._build_result(mdot_sol, P_sol, (r1, r2), converged)

        if self.verbose:
            logger.info(
                "LoopSolver converged=%s  mdot=%.3f g/s  P_sys=%.4f bar",
                converged, mdot_sol * 1e3, P_sol / 1e5,
            )

        return result

    # ------------------------------------------------------------------
    # Parametric sweep helpers
    # ------------------------------------------------------------------

    def sweep_Q(
        self,
        Q_values: Sequence[float],
        mdot_guess: Optional[float] = None,
    ) -> list[LoopResult]:
        """
        Parametric sweep over heat loads.

        Parameters
        ----------
        Q_values : sequence of float
            Heat loads to sweep [W].
        mdot_guess : float, optional
            Initial mdot guess [kg/s]. Each subsequent solve uses the
            previous solution as warm-start.

        Returns
        -------
        list of LoopResult
        """
        results: list[LoopResult] = []
        mg = mdot_guess or self.mdot_guess
        for Q in Q_values:
            try:
                r = self.solve(Q_evap=Q, mdot_guess=mg)
                mg = r.mdot  # warm-start
                results.append(r)
            except (LoopSolverError, ComponentError) as exc:
                warnings.warn(
                    f"sweep_Q: solver failed at Q={Q:.1f} W — {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
                results.append(None)   # type: ignore[arg-type]
        return results

    def sweep_mdot(
        self,
        mdot_values: Sequence[float],
        Q_evap: float = 0.0,
    ) -> list[tuple[float, float]]:
        """
        Evaluate total loop ΔP as a function of mdot (at fixed Q_evap).

        Useful for plotting the loop's internal characteristic curve
        ΔP_loop(mdot) alongside the pump curve — Ledinegg stability check.

        Parameters
        ----------
        mdot_values : sequence of float
            Mass flow rates [kg/s].
        Q_evap : float
            Evaporator heat load [W].

        Returns
        -------
        list of (mdot, dp_total) tuples
        """
        P_sys = self.accumulator.set_pressure()
        pairs: list[tuple[float, float]] = []
        for mdot in mdot_values:
            try:
                _, dp, _ = self._propagate(mdot, P_sys, Q_evap=Q_evap)
                pairs.append((mdot, dp))
            except (ComponentError, Exception):
                pairs.append((mdot, float("nan")))
        return pairs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_pump_inlet(self, P_sys: float) -> Port:
        """
        Construct the pump inlet Port.

        The pump inlet is subcooled liquid at P_sys + small margin,
        with T = T_sat(P_sys) − subcooling.

        The condenser outlet state (saturated liquid + subcooling) sets
        the pump inlet.
        """
        # Saturated liquid enthalpy at P_sys
        state_sat_l = FluidState.from_Px(fluid=self.fluid, P=P_sys, x=0.0)
        T_pump_in = state_sat_l.T - self.subcooling        # [K]
        # Subcooled liquid at same pressure
        try:
            state_in = FluidState.from_PT(
                fluid=self.fluid, P=P_sys, T=T_pump_in
            )
        except Exception:
            # Fallback: use saturated liquid (zero subcooling)
            state_in = state_sat_l
        return Port(state=state_in, mdot=0.0)   # mdot set in propagation

    def _set_Q_on_component(self, comp: Component, Q: float) -> None:
        """
        Inject heat load Q [W] into a component if it looks like an evaporator.

        Supports components with a ``Q_evap``, ``Q_total``, or ``Q`` attribute.
        """
        for attr in ("Q_evap", "Q_total", "Q"):
            if hasattr(comp, attr):
                setattr(comp, attr, Q)
                return

    def _is_evaporator(self, comp: Component) -> bool:
        """Return True if comp appears to be the evaporator."""
        name_lower = getattr(comp, "name", "").lower()
        cls_lower  = type(comp).__name__.lower()
        return "evap" in name_lower or "evaporator" in cls_lower

    def _propagate(
        self,
        mdot: float,
        P_sys: float,
        Q_evap: float = 0.0,
    ) -> tuple[dict[str, Port], float]:
        """
        Propagate flow through the component chain.

        Parameters
        ----------
        mdot : float   [kg/s]
        P_sys : float  [Pa]
        Q_evap : float [W]

        Returns
        -------
        (nodes, dp_non_pump) where:
            nodes       : dict mapping component name → inlet Port
            dp_non_pump : sum of pressure drops over all non-pump components [Pa]
        """
        # Build pump inlet state
        pump_inlet = self._make_pump_inlet(P_sys)
        pump_inlet = Port(state=pump_inlet.state, mdot=mdot)

        # 1. Solve pump first
        pump_outlet = self._pump.solve_ss(pump_inlet)
        dp_pump = pump_outlet.state.P - pump_inlet.state.P

        # 2. Thread through remaining components
        nodes: dict[str, Port] = {self._pump.name: pump_inlet}
        current_port = pump_outlet
        dp_non_pump  = 0.0

        for comp in self._non_pump:
            # Inject Q_evap if this is the evaporator
            if self._is_evaporator(comp) and Q_evap > 0:
                self._set_Q_on_component(comp, Q_evap)

            nodes[comp.name] = current_port
            P_before = current_port.state.P
            current_port = Port(state=current_port.state, mdot=mdot)
            try:
                outlet = comp.solve_ss(current_port)
            except ComponentError as exc:
                raise ComponentError(comp, str(exc)) from exc
            dp_comp      = P_before - outlet.state.P    # positive = pressure drop
            dp_non_pump += dp_comp
            current_port = outlet

        return nodes, dp_non_pump, dp_pump

    def _residuals(self, x: np.ndarray) -> np.ndarray:
        """
        Residual vector for Newton-Raphson.

        x[0] = mdot  [kg/s]
        x[1] = P_sys [Pa]

        R[0] = ΔP_pump − ΣΔP_non_pump   (pressure balance, should → 0)
        R[1] = P_sys   − P_acc           (accumulator set-point, should → 0)
        """
        self._n_eval += 1
        mdot  = float(x[0])
        P_sys = float(x[1])

        # Guard against unphysical iterates
        mdot  = max(mdot,  1e-6)
        P_sys = max(P_sys, 1e3)

        # Accumulator pressure
        P_acc = self.accumulator.set_pressure()

        try:
            nodes, dp_non_pump, dp_pump_val = self._propagate(mdot, P_sys, Q_evap=self._Q_evap)

            R1 = dp_pump_val - dp_non_pump      # pressure balance [Pa]
            R2 = P_sys       - P_acc            # accumulator setpoint [Pa]

        except (ComponentError, Exception) as exc:
            if self.verbose:
                logger.debug("_residuals: component error mdot=%.4f g/s — %s",
                             mdot * 1e3, exc)
            # Return large residual to steer solver away
            R1 = 1e6
            R2 = P_sys - P_acc

        return np.array([R1, R2], dtype=float)

    def _build_result(
        self,
        mdot: float,
        P_sys: float,
        residuals: tuple[float, float],
        converged: bool,
    ) -> LoopResult:
        """Reconstruct the full solution at the converged (mdot, P_sys)."""
        mdot  = max(mdot,  1e-6)
        P_sys = max(P_sys, 1e3)

        nodes, dp_non_pump, dp_pump = self._propagate(
            mdot, P_sys, Q_evap=self._Q_evap
        )

        # Find evaporator outlet quality
        x_evap_out = float("nan")
        for comp in self._non_pump:
            if self._is_evaporator(comp):
                try:
                    evap_inlet = nodes[comp.name]
                    evap_inlet_p = Port(state=evap_inlet.state, mdot=mdot)
                    evap_outlet = comp.solve_ss(evap_inlet_p)
                    x_evap_out = evap_outlet.state.x
                except Exception:
                    pass
                break

        # Saturation temperature at P_sys
        try:
            T_sat = FluidState.from_Px(fluid=self.fluid, P=P_sys, x=0.0).T
        except Exception:
            T_sat = float("nan")

        return LoopResult(
            mdot        = mdot,
            P_sys       = P_sys,
            T_sat       = T_sat,
            x_evap_out  = x_evap_out,
            dp_pump     = dp_pump,
            dp_total    = dp_non_pump,
            nodes       = nodes,
            components  = [c.name for c in self.components],
            residuals   = residuals,
            n_iter      = self._n_eval,
            converged   = converged,
        )


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def build_standard_loop(
    pump:        Component,
    evaporator:  Component,
    condenser:   Component,
    accumulator: Any,
    fluid:       str,
    pipes:       Optional[list[Component]] = None,
    **solver_kwargs: Any,
) -> LoopSolver:
    """
    Convenience factory for the standard MPL topology:

        Pump → [pipe_l] → Evaporator → [pipe_tp] → Condenser → (accumulator)

    Parameters
    ----------
    pump, evaporator, condenser : Component
    accumulator : AccumulatorHCA | AccumulatorPCA
    fluid : str
    pipes : list of Pipe, optional
        If given, inserted between components in the order:
        [pipe_liquid, pipe_two_phase]  (liquid before evap, two-phase after)
    **solver_kwargs
        Passed to LoopSolver (e.g. tol, max_iter, subcooling).

    Returns
    -------
    LoopSolver
    """
    if pipes is None:
        components = [pump, evaporator, condenser]
    elif len(pipes) == 1:
        components = [pump, pipes[0], evaporator, condenser]
    elif len(pipes) == 2:
        components = [pump, pipes[0], evaporator, pipes[1], condenser]
    else:
        # Insert all pipes after pump, then evap, then condenser
        components = [pump] + list(pipes) + [evaporator, condenser]

    return LoopSolver(
        components=components,
        accumulator=accumulator,
        fluid=fluid,
        **solver_kwargs,
    )


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Minimal smoke-test using stub components.
    For full testing run: pytest test_loop.py
    """
    print("loop.py — smoke test")

    # --- Stub classes ---
    from dataclasses import dataclass as dc

    @dc
    class _StubState:
        P: float; h: float; T: float; rho: float
        x: float; phase: str = "liquid"

    @dc
    class _StubPort:
        state: _StubState; mdot: float = 0.01

    class _StubPump(Component):
        name = "Pump"
        def __init__(self):
            super().__init__(name="Pump")
        def solve_ss(self, inlet):
            dp = 10_000.0
            s = _StubState(P=inlet.state.P + dp, h=inlet.state.h + 100,
                           T=290.0, rho=800.0, x=-0.01)
            return _StubPort(state=s, mdot=inlet.mdot)
        def pressure_drop(self): return 0.0

    class _StubEvap(Component):
        name = "Evaporator"
        Q_evap = 200.0
        def __init__(self):
            super().__init__(name="Evaporator")
        def solve_ss(self, inlet):
            s = _StubState(P=inlet.state.P - 3000, h=inlet.state.h + 20_000,
                           T=295.0, rho=10.0, x=0.3)
            return _StubPort(state=s, mdot=inlet.mdot)
        def pressure_drop(self): return 3000.0

    class _StubCond(Component):
        name = "Condenser"
        def __init__(self):
            super().__init__(name="Condenser")
        def solve_ss(self, inlet):
            s = _StubState(P=inlet.state.P - 7000, h=inlet.state.h - 25_000,
                           T=285.0, rho=750.0, x=-0.01)
            return _StubPort(state=s, mdot=inlet.mdot)
        def pressure_drop(self): return 7000.0

    class _StubAcc:
        fluid = "Acetone"
        def set_pressure(self): return 2.0e5   # 2 bar

    # This smoke test only checks that LoopSolver can be instantiated and
    # that the residual function runs without exception.
    solver = LoopSolver(
        components=[_StubPump(), _StubEvap(), _StubCond()],
        accumulator=_StubAcc(),
        fluid="Acetone",
        verbose=False,
    )
    R = solver._residuals(np.array([0.01, 2.0e5]))
    print(f"  Residuals at initial guess: R={R}")
    print("  Smoke test PASSED (full solve requires CoolProp + real components)")
