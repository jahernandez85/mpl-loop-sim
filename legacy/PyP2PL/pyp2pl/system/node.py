"""
pyp2pl.system.node
==================
Fluid state at a single node (point) in the P2PL loop.

A node is defined by its pressure P and enthalpy h.
All derived quantities (T, x, rho, ...) are computed on demand via CoolProp.

The Loop solver builds a list of nodes by marching component-by-component
around the loop.  Each component transforms one PortState into the next.
"""

from dataclasses import dataclass
import CoolProp.CoolProp as CP


@dataclass
class Node:
    """
    Fluid state at one nodal point in the P2PL loop.

    Parameters
    ----------
    P     : float   pressure [Pa]
    h     : float   specific enthalpy [J/kg]
    m_dot : float   mass flow rate [kg/s]
    fluid : str     CoolProp fluid name
    label : str     human-readable label, e.g. 'pump_outlet'
    """
    P:     float
    h:     float
    m_dot: float
    fluid: str  = 'R134a'
    label: str  = ''

    # ------------------------------------------------------------------
    # Derived properties (computed on demand, not stored)
    # ------------------------------------------------------------------

    @property
    def T(self) -> float:
        """Temperature [K]."""
        return CP.PropsSI('T', 'P', self.P, 'H', self.h, self.fluid)

    @property
    def T_C(self) -> float:
        """Temperature [°C]."""
        return self.T - 273.15

    @property
    def x(self) -> float:
        """Vapor quality [-]. Returns -1.0 for single-phase."""
        try:
            phase = CP.PhaseSI('P', self.P, 'H', self.h, self.fluid)
            if phase in ('twophase', 'two-phase'):
                return float(CP.PropsSI('Q', 'P', self.P, 'H', self.h, self.fluid))
        except Exception:
            pass
        return -1.0

    @property
    def rho(self) -> float:
        """Density [kg/m³]."""
        return CP.PropsSI('D', 'P', self.P, 'H', self.h, self.fluid)

    @property
    def phase(self) -> str:
        """Phase description string."""
        try:
            return CP.PhaseSI('P', self.P, 'H', self.h, self.fluid)
        except Exception:
            return 'unknown'

    @property
    def T_sat(self) -> float:
        """Saturation temperature [K] at this node's pressure."""
        return CP.PropsSI('T', 'P', self.P, 'Q', 0, self.fluid)

    def __repr__(self):
        x_str = f"x={self.x:.3f}" if self.x >= 0 else "subcooled"
        return (f"Node({self.label!r:20s}  "
                f"P={self.P/1e3:7.2f} kPa  "
                f"T={self.T_C:6.2f} °C  "
                f"h={self.h/1e3:7.2f} kJ/kg  "
                f"{x_str}  "
                f"ṁ={self.m_dot*1e3:.3f} g/s)")
