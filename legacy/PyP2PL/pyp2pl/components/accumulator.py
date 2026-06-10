"""
pyp2pl.components.accumulator
==============================
Accumulator with polytropic gas model (diaphragm type).

Used in fully-charged P2PLs (100% liquid charge) where no vapor void
exists in the loop — the accumulator provides the compressibility
needed to absorb fluid expansion during boiling.

Key difference from Reservoir
------------------------------
  - Reservoir: partial liquid charge, vapor in the top is the P2PL working
    fluid that can condense/evaporate.
  - Accumulator: separate gas (N₂ or air) behind an impermeable diaphragm.
    The gas is compressed/expanded polytropically. No mass transfer between
    gas and refrigerant.

The accumulator can be placed at ANY position in the loop by inserting it
at the desired index in the Loop component list.  This is the key feature
enabling the accumulator-position study.

Physics  (Kokate 2021 AIAA, Eqs. 2–5 / Kokate 2025 ATE, Eqs. 1–4)
-------
  Polytropic gas:
      p_0 * V_0^n = p_0,ref * V_0,ref^n = const

  Mass balance on liquid side (mass flow through accumulator):
      ṁ_a = -ρ_l * dV_0/dt          (dynamic; zero at steady state)

  Pressure dynamics:
      dp_0/dt = (n * p_0^(1+1/n)) / (ρ_l * p_0,ref^(1/n) * V_0,ref) * (ṁ_1 - ṁ_3)

  At steady state (ṁ_1 = ṁ_3):
      dp_0/dt = 0  → accumulator pressure is constant.
      The pressure at the accumulator node equals the local loop pressure.
      The liquid stream passes through unchanged.

  Accumulator stiffness:
      K_acc = -dP/dV = n * P_0 / V_0     [Pa/m³]
      Higher K → stiffer → stronger pressure response to flow perturbations.

Reference
---------
  Kokate & Park, J. Spacecraft Rockets / AIAA (2021), Eqs. 2–5
  Kokate & Park, Appl. Therm. Eng. 258 (2025) 124549, Sec. 2
  Kokate PhD Thesis (2024), Ch. 4
"""

from dataclasses import dataclass

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult


@dataclass
class AccumulatorGeometry:
    """
    Accumulator geometry and initial gas state.
    Defaults approximate Kokate's accumulator (Kokate 2025, Table 1).
    """
    V_gas_init:   float = 50e-6     # m³   initial gas volume
    P_gas_init:   float = 600e3     # Pa   initial gas pressure (pre-charge pressure)
    polytropic_n: float = 1.4       # –    n = cp/cv (isentropic ideal gas, N₂)
    V_total_acc:  float = 100e-6    # m³   total accumulator volume (gas + liquid)


class Accumulator(BaseComponent):
    """
    Accumulator (diaphragm type, polytropic gas).

    Can be inserted at any position in the Loop component list.
    At steady state: pass-through (inlet = outlet).

    Parameters
    ----------
    fluid : str
        Refrigerant fluid name (for liquid density in dynamic model).
    geometry : AccumulatorGeometry, optional

    Example
    -------
    >>> from pyp2pl.components.accumulator import Accumulator
    >>> from pyp2pl.components.base import PortState
    >>> acc = Accumulator(fluid='R134a')
    >>> inlet = PortState(P=600e3, h=2.5e5, m_dot=5e-3, fluid='R134a')
    >>> result = acc.compute(inlet)
    >>> print(result.metrics)
    """

    def __init__(self, fluid: str = 'R134a', geometry: AccumulatorGeometry = None):
        super().__init__(fluid)
        self.geo = geometry or AccumulatorGeometry()

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute accumulator outlet state (steady-state: pass-through).

        At steady state the liquid passes through the accumulator without
        pressure or enthalpy change.

        Returns
        -------
        ComponentResult with metrics:
            V_gas_m3         [m³]   current gas volume
            P_gas_Pa         [Pa]   current gas pressure
            stiffness_Pa_m3  [Pa/m³] accumulator stiffness K = n*P/V
            delta_P_Pa       [Pa]   pressure drop (0 at steady state)
        """
        geo  = self.geo
        P_in = inlet.P

        # Current gas volume from polytropic relation
        n = geo.polytropic_n
        V_gas = geo.V_gas_init * (geo.P_gas_init / P_in) ** (1.0 / n)
        V_gas = max(V_gas, 1e-9)   # physical lower bound

        # Stiffness: K = n * P_0 / V_0  [Pa/m³]
        stiffness = n * P_in / V_gas

        # Steady-state: pass-through
        outlet = PortState(P=inlet.P, h=inlet.h, m_dot=inlet.m_dot, fluid=self.fluid)

        metrics = {
            'V_gas_m3':        V_gas,
            'P_gas_Pa':        P_in,
            'stiffness_Pa_m3': stiffness,
            'delta_P_Pa':      0.0,
            'n':               n,
        }

        return ComponentResult(outlet=outlet, metrics=metrics)

    def stiffness(self, P: float) -> float:
        """
        Compute accumulator stiffness K = n * P / V_gas [Pa/m³] at pressure P.

        Higher stiffness = stiffer accumulator = less damping of pressure oscillations.
        This is the parameter varied in Kokate (2025) PDO study.
        """
        n     = self.geo.polytropic_n
        V_gas = self.geo.V_gas_init * (self.geo.P_gas_init / P) ** (1.0 / n)
        return n * P / max(V_gas, 1e-9)
