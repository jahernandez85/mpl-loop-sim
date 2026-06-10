"""
pyp2pl.fluid.fluid
==================
Thin CoolProp wrapper that returns FluidState dataclasses.

All physical quantities use SI units:
  - Pressure       : Pa
  - Temperature    : K
  - Enthalpy       : J/kg
  - Entropy        : J/(kg·K)
  - Density        : kg/m³
  - Dynamic viscosity : Pa·s
  - Thermal conductivity : W/(m·K)
  - Surface tension : N/m
  - Specific heat   : J/(kg·K)
  - Vapor quality   : dimensionless [0, 1]

Usage
-----
    from pyp2pl.fluid.fluid import FluidProperties

    fp = FluidProperties('R134a')

    # Saturated state at given pressure
    state = fp.saturated(P=500e3)
    print(state.T_sat, state.h_l, state.h_v)

    # State given T and P (subcooled or superheated)
    state = fp.state_TP(T=280.0, P=600e3)
    print(state.rho, state.cp)
"""

from dataclasses import dataclass, field
from typing import Optional
import CoolProp.CoolProp as CP


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SatState:
    """
    Saturated fluid properties at a given pressure (or temperature).
    Subscripts: _l = saturated liquid, _v = saturated vapor.
    """
    fluid: str
    P_sat: float       # Pa
    T_sat: float       # K

    # Liquid phase
    rho_l: float       # kg/m³
    h_l: float         # J/kg
    cp_l: float        # J/(kg·K)
    mu_l: float        # Pa·s
    k_l: float         # W/(m·K)
    Pr_l: float        # –

    # Vapor phase
    rho_v: float       # kg/m³
    h_v: float         # J/kg
    cp_v: float        # J/(kg·K)
    mu_v: float        # Pa·s
    k_v: float         # W/(m·K)
    Pr_v: float        # –

    # Common
    h_fg: float        # J/kg  (latent heat = h_v - h_l)
    sigma: float       # N/m   (surface tension)


@dataclass
class FluidState:
    """
    Single-phase (or two-phase mixture) fluid state at given T and P.
    When the fluid is two-phase, quality x is in [0,1] and rho, h, cp, mu, k
    are computed as homogeneous mixture averages.
    """
    fluid: str
    T: float           # K
    P: float           # Pa
    x: float           # vapor quality (–1 if single-phase subcooled/superheated)

    rho: float         # kg/m³
    h: float           # J/kg
    cp: float          # J/(kg·K)
    mu: float          # Pa·s
    k: float           # W/(m·K)
    Pr: float          # –

    # Saturation properties at current P (always available)
    sat: Optional[SatState] = field(default=None)


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class FluidProperties:
    """
    Wrapper around CoolProp for a specific refrigerant.

    Parameters
    ----------
    fluid : str
        CoolProp fluid name, e.g. 'R134a', 'R1234yf', 'R245fa', 'Water'.
        A full list is at http://www.coolprop.org/fluid_properties/PurePseudoPure.html
    """

    def __init__(self, fluid: str):
        # Validate the fluid name immediately
        try:
            CP.PropsSI('T', 'P', 101325, 'Q', 0, fluid)
        except Exception as e:
            raise ValueError(
                f"'{fluid}' is not a valid CoolProp fluid name.\n"
                f"Check http://www.coolprop.org/fluid_properties/PurePseudoPure.html\n"
                f"CoolProp error: {e}"
            )
        self.fluid = fluid

    # ------------------------------------------------------------------
    # Saturation properties
    # ------------------------------------------------------------------

    def saturated(self, P: float = None, T: float = None) -> SatState:
        """
        Return saturation properties at a given pressure (Pa) or temperature (K).
        Exactly one of P or T must be provided.
        """
        if (P is None) == (T is None):
            raise ValueError("Provide exactly one of P or T.")

        f = self.fluid
        Q_l, Q_v = 0.0, 1.0

        if P is not None:
            kw = {'P': P, 'Q': Q_l}
            T_sat = CP.PropsSI('T', 'P', P, 'Q', Q_l, f)
            P_sat = P
        else:
            kw = {'T': T, 'Q': Q_l}
            P_sat = CP.PropsSI('P', 'T', T, 'Q', Q_l, f)
            T_sat = T

        def _prop(name, Q):
            if P is not None:
                return CP.PropsSI(name, 'P', P, 'Q', Q, f)
            return CP.PropsSI(name, 'T', T_sat, 'Q', Q, f)

        rho_l = _prop('D', Q_l)
        h_l   = _prop('H', Q_l)
        cp_l  = _prop('C', Q_l)
        mu_l  = _prop('V', Q_l)
        k_l   = _prop('L', Q_l)
        Pr_l  = cp_l * mu_l / k_l

        rho_v = _prop('D', Q_v)
        h_v   = _prop('H', Q_v)
        cp_v  = _prop('C', Q_v)
        mu_v  = _prop('V', Q_v)
        k_v   = _prop('L', Q_v)
        Pr_v  = cp_v * mu_v / k_v

        # Surface tension: CoolProp uses 'I' for surface tension
        try:
            sigma = CP.PropsSI('surface_tension', 'T', T_sat, 'Q', 0.5, f)
        except Exception:
            sigma = 0.0  # some fluids don't have sigma in CoolProp

        return SatState(
            fluid=f, P_sat=P_sat, T_sat=T_sat,
            rho_l=rho_l, h_l=h_l, cp_l=cp_l, mu_l=mu_l, k_l=k_l, Pr_l=Pr_l,
            rho_v=rho_v, h_v=h_v, cp_v=cp_v, mu_v=mu_v, k_v=k_v, Pr_v=Pr_v,
            h_fg=h_v - h_l, sigma=sigma,
        )

    # ------------------------------------------------------------------
    # General state given T, P (single-phase or two-phase)
    # ------------------------------------------------------------------

    def state_TP(self, T: float, P: float) -> FluidState:
        """
        Compute fluid state at given temperature T [K] and pressure P [Pa].
        Works for subcooled, saturated mixture, and superheated regions.
        Vapor quality x = –1 if single-phase.
        """
        f = self.fluid

        # Determine phase and quality
        try:
            phase_code = CP.PhaseSI('T', T, 'P', P, f)
        except Exception:
            phase_code = 'unknown'

        if phase_code in ('twophase', 'two-phase'):
            # Two-phase: quality from T and P
            x = CP.PropsSI('Q', 'T', T, 'P', P, f)
            x = max(0.0, min(1.0, x))
            sat = self.saturated(P=P)
            # Homogeneous mixture properties (Kokate assumption)
            rho = 1.0 / (x / sat.rho_v + (1 - x) / sat.rho_l)
            h   = sat.h_l + x * sat.h_fg
            cp  = x * sat.cp_v + (1 - x) * sat.cp_l
            mu  = x * sat.mu_v + (1 - x) * sat.mu_l
            k   = x * sat.k_v  + (1 - x) * sat.k_l
            Pr  = cp * mu / k
        else:
            x = -1.0
            sat = self.saturated(P=P)
            rho = CP.PropsSI('D', 'T', T, 'P', P, f)
            h   = CP.PropsSI('H', 'T', T, 'P', P, f)
            cp  = CP.PropsSI('C', 'T', T, 'P', P, f)
            mu  = CP.PropsSI('V', 'T', T, 'P', P, f)
            k   = CP.PropsSI('L', 'T', T, 'P', P, f)
            Pr  = cp * mu / k

        return FluidState(
            fluid=f, T=T, P=P, x=x,
            rho=rho, h=h, cp=cp, mu=mu, k=k, Pr=Pr,
            sat=sat,
        )

    # ------------------------------------------------------------------
    # State given pressure and enthalpy  (useful for pump/valve work)
    # ------------------------------------------------------------------

    def state_PH(self, P: float, h: float) -> FluidState:
        """
        Compute fluid state at given pressure P [Pa] and enthalpy h [J/kg].
        """
        T = CP.PropsSI('T', 'P', P, 'H', h, self.fluid)
        return self.state_TP(T=T, P=P)

    # ------------------------------------------------------------------
    # Convenience: saturation pressure at given temperature
    # ------------------------------------------------------------------

    def P_sat(self, T: float) -> float:
        """Return saturation pressure [Pa] at temperature T [K]."""
        return CP.PropsSI('P', 'T', T, 'Q', 0, self.fluid)

    def T_sat(self, P: float) -> float:
        """Return saturation temperature [K] at pressure P [Pa]."""
        return CP.PropsSI('T', 'P', P, 'Q', 0, self.fluid)
