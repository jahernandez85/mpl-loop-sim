"""
pyp2pl.components.reservoir
============================
Reservoir (accumulator/buffer tank with partial charge) for a P2PL.

The reservoir stores the vapor-filled void volume that accommodates
fluid expansion during boiling.  The liquid is subcooled and incompressible;
the vapor undergoes a polytropic process.

This is the compressibility element in Kokate's reference loop (no separate
accumulator — the reservoir IS the compressibility source).

Physics  (Kokate PhD 2024, Eqs. 2.13–2.16 / Kokate 2023, Eqs. 13–16)
-------
  Charge ratio:
      CR = V_liquid / V_total           [dimensionless, e.g. 0.70]

  Vapor volume:
      V_v = V_total * (1 - CR)

  Polytropic vapor compression/expansion:
      p_v * V_v^n = const               (n = cp/cv for isentropic ideal gas)

  Mass balance (steady-state):
      m_dot_in = m_dot_out              (no mass accumulation)

  The reservoir does not change the enthalpy of the passing liquid stream.
  It only affects the system pressure through the polytropic vapor buffer.

  At steady state the reservoir is transparent: inlet = outlet.
  Its role becomes active in the dynamic model (Phase 6).

Reference
---------
  Kokate & Park, Appl. Therm. Eng. 229 (2023), Eqs. 13–16
  Kokate PhD Thesis (2024), Eqs. 2.13–2.16
"""

from dataclasses import dataclass

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult


@dataclass
class ReservoirGeometry:
    """
    Reservoir dimensions and initial conditions.
    Defaults match Kokate's system (PhD 2024, Table 2.3).
    """
    V_total:      float = 780e-6    # m³   total internal volume
    charge_ratio: float = 0.70      # –    liquid volume / total volume
    polytropic_n: float = 1.4       # –    n = cp/cv (isentropic ideal gas)
    T_reservoir:  float = 293.15    # K    reservoir temperature (isothermal assumption)

    @property
    def V_liquid_init(self) -> float:
        return self.V_total * self.charge_ratio

    @property
    def V_vapor_init(self) -> float:
        return self.V_total * (1.0 - self.charge_ratio)


class Reservoir(BaseComponent):
    """
    Reservoir model.

    At steady state: the fluid passes through unchanged (P, h, m_dot conserved).
    The reservoir sets the reference pressure level of the loop.

    The polytropic vapor state is tracked for use by the dynamic model
    and for computing the system compliance (∂V/∂P).

    Parameters
    ----------
    fluid : str
    geometry : ReservoirGeometry, optional

    Example
    -------
    >>> from pyp2pl.components.reservoir import Reservoir
    >>> from pyp2pl.components.base import PortState
    >>> res = Reservoir(fluid='R134a')
    >>> inlet = PortState(P=572.2e3, h=2.5e5, m_dot=5e-3, fluid='R134a')
    >>> result = res.compute(inlet)
    >>> print(result.summary())
    """

    def __init__(self, fluid: str = 'R134a', geometry: ReservoirGeometry = None):
        super().__init__(fluid)
        self.geo = geometry or ReservoirGeometry()

        # Initial vapor state (reference for polytropic process)
        self._P_v_ref = None    # set on first call or explicitly
        self._V_v_ref = self.geo.V_vapor_init

    def set_reference_pressure(self, P_ref: float):
        """
        Set the reference vapor pressure [Pa] for the polytropic model.
        Called by the Loop solver when initialising the system pressure.
        """
        self._P_v_ref = P_ref

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute reservoir outlet state (steady-state: pass-through).

        At steady state the liquid passes through the reservoir without
        pressure or enthalpy change.  Performance metrics report the
        vapor buffer state.

        Parameters
        ----------
        inlet : PortState

        Returns
        -------
        ComponentResult with metrics:
            V_vapor_m3       [m³]   current vapor volume
            V_liquid_m3      [m³]   current liquid volume
            charge_ratio     [-]    current charge ratio
            P_vapor_Pa       [Pa]   vapor pressure
            compliance_m3Pa  [m³/Pa] dV/dP of vapor buffer
        """
        geo = self.geo
        P_in = inlet.P

        # Reference vapor pressure = inlet pressure if not set
        if self._P_v_ref is None:
            self._P_v_ref = P_in

        # Current vapor volume from polytropic relation:
        # p_v * V_v^n = p_ref * V_ref^n
        n = geo.polytropic_n
        V_v = geo.V_vapor_init * (self._P_v_ref / P_in) ** (1.0 / n)
        V_l = geo.V_total - V_v
        CR  = V_l / geo.V_total if geo.V_total > 0 else 0.0

        # System compliance: dV_v/dP = -V_v / (n * P_v)
        compliance = -V_v / (n * P_in) if P_in > 0 else 0.0

        # Steady-state: outlet = inlet (no pressure drop, no heat transfer)
        outlet = PortState(P=inlet.P, h=inlet.h, m_dot=inlet.m_dot, fluid=self.fluid)

        metrics = {
            'V_vapor_m3':       V_v,
            'V_liquid_m3':      V_l,
            'charge_ratio':     CR,
            'P_vapor_Pa':       P_in,
            'compliance_m3Pa':  compliance,
            'delta_P_Pa':       0.0,
        }

        return ComponentResult(outlet=outlet, metrics=metrics)
