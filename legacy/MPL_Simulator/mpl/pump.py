"""
components/pump.py — Centrifugal Pump Model
============================================
MPL Simulation Library — Module 6a (Phase 6)

Models the mechanical pump that circulates the working fluid around the loop.
In an MPL, the pump provides the pressure rise to overcome total loop losses.

Physical model
--------------
The pump is assumed to handle **pure subcooled liquid** (inlet quality x ≤ 0).
Two representations are available:

1. **Curve-based** (PumpCurve):  ΔP_pump = f(mdot)  polynomial from datasheet.
   Isentropic efficiency η can be constant or a function of mdot.

2. **Fixed-ΔP** (PumpFixed):  user prescribes ΔP directly; useful for
   loop-level Newton-Raphson where ΔP_pump is an iteration variable.

Thermodynamic model (both classes)
-----------------------------------
The pump handles liquid:  ρ ≈ ρ_liquid = 1/v_l  (incompressible approximation)

  W_shaft = mdot * ΔP / ρ_l / η            [W]  — shaft power consumed
  Δh      = ΔP / ρ_l / η                   [J/kg] — enthalpy rise (irreversible)
  h_out   = h_in + Δh

For a truly isentropic pump:  Δh_ideal = ΔP * v_l  (v_l = 1/ρ_l).
Irreversibilities raise the actual enthalpy by 1/η.

Cavitation guard (NPSH)
-----------------------
Net Positive Suction Head:

  NPSH_a = (P_in - P_sat(T_in)) / (ρ_l * g)   [m]

A warning is issued when NPSH_a < NPSH_r (required, user-supplied).

References
----------
[1] R. Kokate, C. Park, "Pumped two-phase loop …,"
    Appl. Therm. Eng. 229 (2023) 120630.
[2] X. Wang et al., "MPL modeling for data center cooling,"
    Appl. Energy 344 (2023) 121271.  [Eq. 23 — pump power]
[3] R. Kokate, PhD Thesis, 2024.  [pump curve and Ledinegg]
[4] A. Leveque et al., "MPL dynamics," Therm. Sci. Eng. Prog. (2024).
    [pump parameter b: linear ΔP-mdot slope]
[5] Middelhuis et al., "Review MPL experiments," (2024).
[6] M. VanGerner et al., "1D dynamic model," (2016).
"""


from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

import numpy as np

from base import Component, ComponentError, Port
from fluid_properties import FluidState, resolve_fluid_name

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_g = 9.80665  # gravitational acceleration [m/s²]


# ---------------------------------------------------------------------------
# Pump curve helpers
# ---------------------------------------------------------------------------

def polynomial_pump_curve(
    coeffs: Sequence[float],
) -> Callable[[float], float]:
    """
    Return a ΔP_pump(mdot) callable from polynomial coefficients.

    Parameters
    ----------
    coeffs : sequence of float
        Coefficients [a0, a1, a2, …] so that
        ΔP = a0 + a1*mdot + a2*mdot² + …
        (numpy.polyval convention: highest degree first is NOT used here;
        index 0 = constant term)

    Returns
    -------
    Callable[[float], float]
        ΔP [Pa] as a function of mdot [kg/s].

    Examples
    --------
    >>> curve = polynomial_pump_curve([30000.0, -5e6])  # ΔP = 30 kPa - 5e6*mdot
    >>> curve(0.005)   # 30000 - 5e6*0.005 = 5000 Pa
    5000.0
    """
    c = np.asarray(coeffs, dtype=float)

    def _curve(mdot: float) -> float:
        # Horner evaluation: c[0] + c[1]*m + c[2]*m^2 + …
        return float(np.polyval(c[::-1], mdot))

    return _curve


def linear_pump_curve(
    dp_zero_flow: float,
    b: float,
) -> Callable[[float], float]:
    """
    Linear pump model: ΔP = dp_zero_flow - b * mdot.

    Used in Leveque (2024) stability analysis.

    Parameters
    ----------
    dp_zero_flow : float
        Shut-off head [Pa]  (ΔP when mdot = 0).
    b : float
        Slope [Pa·s/kg].  Positive → ΔP decreases with flow.

    Returns
    -------
    Callable[[float], float]
    """
    def _curve(mdot: float) -> float:
        return dp_zero_flow - b * mdot

    return _curve


# ---------------------------------------------------------------------------
# Pump — curve-based (primary component)
# ---------------------------------------------------------------------------

@dataclass
class Pump(Component):
    """
    Centrifugal pump with a user-supplied ΔP-mdot characteristic curve.

    The pump raises the fluid pressure and slightly increases its enthalpy
    due to irreversibilities (η < 1).

    Parameters
    ----------
    dp_curve : Callable[[float], float]
        ΔP_pump [Pa] = dp_curve(mdot [kg/s]).
        Build with ``polynomial_pump_curve`` or ``linear_pump_curve``.
    eta : float or Callable[[float], float]
        Isentropic efficiency [-].
        • float  → constant efficiency (typical 0.30–0.65 for small pumps).
        • callable → η(mdot) for variable-speed or off-design use.
    fluid : str
        CoolProp fluid identifier (e.g. "Acetone", "R1234yf").
    npsh_required : float
        Required NPSH [m].  If None, cavitation check is skipped.
    name : str
        Component label.

    Notes
    -----
    * The pump is assumed to always handle pure liquid.  If the inlet has
      x > 0, a ComponentError is raised (two-phase pump not modelled).
    * mdot is carried from the inlet Port unchanged (incompressible loop
      assumption at steady state).

    Physical equations
    ------------------
    Isentropic specific work:
        w_ideal = ΔP / ρ_l              [J/kg]
    Actual enthalpy rise (irreversible):
        Δh = w_ideal / η = ΔP / (ρ_l * η)
    Outlet enthalpy:
        h_out = h_in + Δh
    Shaft power:
        W_shaft = mdot * ΔP / (ρ_l * η)  [W]
    NPSH available:
        NPSH_a = (P_in - P_sat) / (ρ_l * g)  [m]
    """

    dp_curve:       Callable[[float], float]
    eta:            float | Callable[[float], float]
    fluid:          str
    npsh_required:  Optional[float] = None
    name:           str = field(default="Pump")

    # ---- post-init (dataclass + Component.__init__ coexistence) -----------
    def __post_init__(self) -> None:
        Component.__init__(self, name=self.name)
        # Validate constant efficiency
        if isinstance(self.eta, float):
            if not (0.0 < self.eta <= 1.0):
                raise ValueError(
                    f"Pump.eta must be in (0, 1]; got {self.eta}"
                )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _eta(self, mdot: float) -> float:
        """Return efficiency for given mass flow rate."""
        if callable(self.eta):
            eta_val = float(self.eta(mdot))
        else:
            eta_val = float(self.eta)
        if not (0.0 < eta_val <= 1.0):
            raise ComponentError(
                self, f"η={eta_val:.4f} is outside (0, 1] at mdot={mdot:.5f} kg/s"
            )
        return eta_val

    def _dp(self, mdot: float) -> float:
        """Evaluate pump curve; guard against negative ΔP."""
        dp_val = float(self.dp_curve(mdot))
        if dp_val < 0.0:
            raise ComponentError(
                self,
                f"dp_curve returned negative ΔP = {dp_val:.1f} Pa "
                f"at mdot = {mdot:.5f} kg/s. "
                "Check curve coefficients or operating range."
            )
        return dp_val

    def _npsh_check(self, inlet: Port) -> None:
        """Warn if NPSH available < NPSH required."""
        if self.npsh_required is None:
            return
        try:
            import CoolProp.CoolProp as CP
            f = resolve_fluid_name(self.fluid)
            P_sat = float(CP.PropsSI("P", "T", inlet.T, "Q", 0, f))
        except Exception:
            return  # skip if CoolProp call fails
        rho_l = inlet.rho
        npsh_a = (inlet.P - P_sat) / (rho_l * _g)
        if npsh_a < self.npsh_required:
            warnings.warn(
                f"{self.name}: NPSH_available = {npsh_a:.2f} m < "
                f"NPSH_required = {self.npsh_required:.2f} m. "
                "Cavitation risk!",
                RuntimeWarning,
                stacklevel=3,
            )

    # ------------------------------------------------------------------ #
    #  Component interface                                                 #
    # ------------------------------------------------------------------ #

    def solve_ss(self, inlet: Port) -> Port:
        """
        Compute pump outlet state for steady-state operation.

        Parameters
        ----------
        inlet : Port
            Inlet port.  Must carry pure subcooled liquid (x ≤ 0).
            mdot [kg/s] must be > 0.

        Returns
        -------
        Port
            Outlet port with P_out = P_in + ΔP_pump and h_out = h_in + Δh.
        """
        self.inlet = inlet
        mdot = inlet.mdot

        # -- input validation --
        if mdot <= 0.0:
            raise ComponentError(self, f"mdot must be > 0; got {mdot:.5e} kg/s")
        if inlet.x > 1e-4:
            raise ComponentError(
                self,
                f"Pump inlet has vapour quality x = {inlet.x:.4f}. "
                "Two-phase pumping is not modelled. "
                "Ensure the pump is located downstream of the condenser subcooling zone."
            )

        # -- NPSH check --
        self._npsh_check(inlet)

        # -- pump curve --
        dp = self._dp(mdot)
        eta = self._eta(mdot)

        # -- thermodynamics --
        rho_l = inlet.rho                        # liquid density at inlet [kg/m³]
        dh = dp / (rho_l * eta)                  # enthalpy rise [J/kg]
        h_out = inlet.h + dh
        P_out = inlet.P + dp

        # -- cache --
        self._last_dP = -dp           # pump adds pressure → negative "drop"
        self._last_Q = 0.0            # adiabatic pump
        self._last_dp_positive = dp   # keep positive for W_shaft
        self._last_eta = eta
        self._last_dh = dh

        # -- outlet FluidState --
        state_out = FluidState.from_Ph(fluid=self.fluid, P=P_out, h=h_out)
        self.outlet = Port(state=state_out, mdot=mdot)
        return self.outlet

    def pressure_drop(self) -> float:
        """
        Pressure drop [Pa].

        Convention: negative for a pump (pressure *rises* in flow direction).
        ΔP = P_in − P_out = −ΔP_pump
        """
        return self._last_dP

    def heat_transfer(self) -> float:
        """Heat added to fluid [W].  Always 0 (adiabatic pump model)."""
        return self._last_Q

    # ------------------------------------------------------------------ #
    #  Derived quantities                                                  #
    # ------------------------------------------------------------------ #

    @property
    def W_shaft(self) -> float:
        """Shaft power consumed [W]  (after last solve_ss)."""
        if self.inlet is None:
            return 0.0
        dp = self._last_dp_positive
        eta = self._last_eta
        rho_l = self.inlet.rho
        mdot = self.inlet.mdot
        return mdot * dp / (rho_l * eta)

    @property
    def dp_pump(self) -> float:
        """Pump pressure rise [Pa]  (positive; after last solve_ss)."""
        return getattr(self, "_last_dp_positive", 0.0)

    def operating_point_curve(
        self,
        mdot_range: Sequence[float],
    ) -> tuple[list[float], list[float]]:
        """
        Evaluate the pump curve over a range of mass flow rates.

        Parameters
        ----------
        mdot_range : sequence of float
            Mass flow rates [kg/s].

        Returns
        -------
        (mdot_list, dp_list) : tuple of lists
            ΔP [Pa] for each mdot.
        """
        dps = []
        for m in mdot_range:
            try:
                dps.append(self._dp(m))
            except ComponentError:
                dps.append(float("nan"))
        return list(mdot_range), dps

    def __repr__(self) -> str:  # type: ignore[override]
        eta_str = (
            f"{self.eta:.3f}" if not callable(self.eta) else "callable"
        )
        return (
            f"Pump(name={self.name!r}, fluid={self.fluid!r}, "
            f"eta={eta_str}, npsh_req={self.npsh_required})"
        )


# ---------------------------------------------------------------------------
# PumpFixed — simplified pump with prescribed ΔP  (for loop solver use)
# ---------------------------------------------------------------------------

@dataclass
class PumpFixed(Component):
    """
    Simplified pump with a prescribed pressure rise ΔP_set.

    Used by the Newton-Raphson loop solver (loop.py) where the pump pressure
    is an iteration variable rather than a function of flow rate.

    Parameters
    ----------
    dp_set : float
        Prescribed pump pressure rise [Pa].
    eta : float
        Constant isentropic efficiency [-].
    fluid : str
        CoolProp fluid identifier.
    name : str
        Component label.
    """

    dp_set:   float
    eta:      float
    fluid:    str
    name:     str = field(default="PumpFixed")

    def __post_init__(self) -> None:
        Component.__init__(self, name=self.name)
        if self.dp_set < 0:
            raise ValueError(f"PumpFixed.dp_set must be ≥ 0; got {self.dp_set}")
        if not (0.0 < self.eta <= 1.0):
            raise ValueError(f"PumpFixed.eta must be in (0, 1]; got {self.eta}")

    def solve_ss(self, inlet: Port) -> Port:
        self.inlet = inlet
        mdot = inlet.mdot
        if inlet.x > 1e-4:
            raise ComponentError(
                self,
                f"PumpFixed inlet quality x = {inlet.x:.4f} > 0. "
                "Pump must handle subcooled liquid."
            )
        rho_l = inlet.rho
        dh = self.dp_set / (rho_l * self.eta)
        h_out = inlet.h + dh
        P_out = inlet.P + self.dp_set
        self._last_dP = -self.dp_set
        self._last_Q = 0.0
        state_out = FluidState.from_Ph(fluid=self.fluid, P=P_out, h=h_out)
        self.outlet = Port(state=state_out, mdot=mdot)
        return self.outlet

    def pressure_drop(self) -> float:
        return self._last_dP

    def heat_transfer(self) -> float:
        return self._last_Q

    @property
    def W_shaft(self) -> float:
        """Shaft power [W] after last solve_ss."""
        if self.inlet is None:
            return 0.0
        return self.inlet.mdot * self.dp_set / (self.inlet.rho * self.eta)

    def __repr__(self) -> str:  # type: ignore[override]
        return (
            f"PumpFixed(name={self.name!r}, dp_set={self.dp_set/1e3:.2f} kPa, "
            f"eta={self.eta:.3f}, fluid={self.fluid!r})"
        )
