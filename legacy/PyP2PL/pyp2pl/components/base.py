"""
pyp2pl.components.base
======================
Abstract base class for all P2PL components.

Every component receives an inlet FluidState and returns an outlet FluidState
plus a ComponentResult with performance metrics.  The same interface will be
reused by the dynamic model (Phase 6) through the time_derivatives() method.

Design contract
---------------
- compute() is the only method the Loop solver calls.
- All components are stateless between calls (pure functions of their inputs).
- Geometry / material parameters are set once at construction.
- fluid property calls go through self._fp (a FluidProperties instance).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.fluid.fluid import FluidProperties, FluidState


@dataclass
class PortState:
    """
    Minimal description of a fluid port (inlet or outlet of a component).
    This is what gets passed between components around the loop.
    """
    P:     float          # Pa    pressure
    h:     float          # J/kg  specific enthalpy
    m_dot: float          # kg/s  mass flow rate
    fluid: str = 'R134a'  # CoolProp fluid name

    @property
    def T(self) -> float:
        """Temperature [K], computed from P and h via CoolProp."""
        import CoolProp.CoolProp as CP
        return CP.PropsSI('T', 'P', self.P, 'H', self.h, self.fluid)

    @property
    def x(self) -> float:
        """Vapor quality [-]. Returns -1 for single-phase."""
        import CoolProp.CoolProp as CP
        try:
            phase = CP.PhaseSI('P', self.P, 'H', self.h, self.fluid)
            if phase in ('twophase', 'two-phase'):
                return float(CP.PropsSI('Q', 'P', self.P, 'H', self.h, self.fluid))
        except Exception:
            pass
        return -1.0


@dataclass
class ComponentResult:
    """
    Output of component.compute().
    Contains the outlet port state and a dictionary of performance metrics.
    """
    outlet:   PortState
    metrics:  Dict[str, Any] = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"  P_out  = {self.outlet.P/1e3:8.2f} kPa",
                 f"  h_out  = {self.outlet.h/1e3:8.2f} kJ/kg",
                 f"  m_dot  = {self.outlet.m_dot*1e3:8.3f} g/s",
                 f"  T_out  = {self.outlet.T-273.15:8.2f} °C",
                 f"  x_out  = {self.outlet.x:8.3f}"]
        for k, v in self.metrics.items():
            if isinstance(v, float):
                lines.append(f"  {k:<12s} = {v:.4g}")
            else:
                lines.append(f"  {k:<12s} = {v}")
        if self.warnings:
            lines.append("  WARNINGS:")
            for w in self.warnings:
                lines.append(f"    ! {w}")
        return "\n".join(lines)


class BaseComponent(ABC):
    """
    Abstract base for all P2PL components.

    Subclasses must implement:
        compute(inlet: PortState) -> ComponentResult
    """

    def __init__(self, fluid: str):
        self.fluid = fluid
        self._fp = FluidProperties(fluid)

    # ------------------------------------------------------------------
    # Must implement
    # ------------------------------------------------------------------

    @abstractmethod
    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute steady-state outlet state and performance metrics.

        Parameters
        ----------
        inlet : PortState  —  pressure, enthalpy, mass flow rate at inlet

        Returns
        -------
        ComponentResult  —  outlet PortState + metrics dict
        """

    # ------------------------------------------------------------------
    # Reserved for dynamic extension (Phase 6)
    # ------------------------------------------------------------------

    def time_derivatives(self, state: dict, t: float, inlet: PortState) -> dict:
        """
        Returns time derivatives of internal state variables.
        Not implemented in Phase 2 — raises NotImplementedError.
        Subclasses in the dynamic extension will override this.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not yet implement a dynamic model."
        )

    # ------------------------------------------------------------------
    # Helpers available to all subclasses
    # ------------------------------------------------------------------

    def _sat(self, P: float = None, T: float = None):
        """Convenience wrapper for saturation properties."""
        return self._fp.saturated(P=P, T=T)

    def _state(self, P: float, h: float):
        """Convenience wrapper: FluidState from P and h."""
        return self._fp.state_PH(P=P, h=h)

    def _warn_quality(self, x: float, location: str):
        """Return a warning string if quality is outside physical range."""
        if x < 0.0:
            return f"{location}: quality {x:.3f} < 0 (subcooled — check inlet conditions)"
        if x > 1.0:
            return f"{location}: quality {x:.3f} > 1 (superheated — reduce heat flux)"
        return None
