"""
pyp2pl.components.pump
=======================
Pump model for a pumped two-phase loop.

Two operating modes
-------------------
'ideal' (Kokate's reference model)
    The pump always delivers exactly the pressure head needed to overcome
    the total loop pressure drop.  Mass flow rate is an independent variable
    set by the solver.  This decouples the pump from the hydraulic network
    and allows the steady-state solver to use m_dot as the free variable.

'curve'
    The pump operates on a user-supplied (flow rate, pressure head) curve.
    The operating point is the intersection of the pump curve and the system
    curve.  Implemented via scipy interpolation.

Physics
-------
  Pump work (shaft work):
      W_p = V_dot * ΔP_p / η_p               (Kokate 2023, Eq. 26)

  Isentropic outlet enthalpy:
      h_out = h_in + W_p / m_dot
      (Kokate assumption: isentropic pump, work calculated from enthalpies)

  Pressure rise:
      P_out = P_in + ΔP_pump

Reference
---------
  Kokate & Park, Appl. Therm. Eng. 229 (2023), Eq. 26
  Kokate PhD Thesis (2024), Sec. 2.2
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import math

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult
import CoolProp.CoolProp as CP


class Pump(BaseComponent):
    """
    Pump model (ideal or pump-curve).

    Parameters
    ----------
    fluid : str
        CoolProp fluid name.
    eta : float
        Pump efficiency (default 0.8 — Kokate assumption).
    mode : str
        'ideal'  — pressure head equals total system ΔP (set by solver).
        'curve'  — interpolate from supplied (flow, head) data.
    delta_P_ideal : float, optional
        In 'ideal' mode, this is the pressure rise [Pa] set externally
        by the Loop solver. Updated each iteration.
    curve_flow : list of float
        Volumetric flow rates [m³/s] for the pump curve (mode='curve').
    curve_head : list of float
        Pressure heads [Pa] for the pump curve (mode='curve').

    Example — ideal mode (used by steady-state solver)
    ---------------------------------------------------
    >>> pump = Pump(fluid='R134a', eta=0.8, mode='ideal')
    >>> pump.delta_P_ideal = 50e3    # set by solver each iteration
    >>> inlet = PortState(P=400e3, h=sat.h_l, m_dot=5e-3, fluid='R134a')
    >>> result = pump.compute(inlet)
    >>> print(result.metrics['W_pump_W'], 'W')

    Example — pump curve mode
    -------------------------
    >>> pump = Pump(fluid='R134a', eta=0.8, mode='curve',
    ...             curve_flow=[0, 1e-4, 2e-4, 3e-4],
    ...             curve_head=[80e3, 70e3, 55e3, 30e3])
    """

    def __init__(
        self,
        fluid:         str   = 'R134a',
        eta:           float = 0.8,
        mode:          str   = 'ideal',
        delta_P_ideal: float = 50e3,
        curve_flow:    Optional[List[float]] = None,
        curve_head:    Optional[List[float]] = None,
    ):
        super().__init__(fluid)
        self.eta           = eta
        self.mode          = mode.lower()
        self.delta_P_ideal = delta_P_ideal    # updated by solver in 'ideal' mode

        if self.mode not in ('ideal', 'curve'):
            raise ValueError("mode must be 'ideal' or 'curve'")

        if self.mode == 'curve':
            if curve_flow is None or curve_head is None:
                raise ValueError(
                    "Pump curve mode requires curve_flow and curve_head lists."
                )
            if len(curve_flow) != len(curve_head) or len(curve_flow) < 2:
                raise ValueError(
                    "curve_flow and curve_head must have the same length (>= 2)."
                )
            self._curve_flow = curve_flow
            self._curve_head = curve_head

    # ------------------------------------------------------------------
    # Main compute method
    # ------------------------------------------------------------------

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute pump outlet state.

        In 'ideal' mode, uses self.delta_P_ideal (set externally by the
        Loop solver before each call).

        In 'curve' mode, interpolates ΔP from the pump curve given the
        current volumetric flow rate.

        Parameters
        ----------
        inlet : PortState
            Liquid refrigerant at pump inlet (from reservoir/accumulator).

        Returns
        -------
        ComponentResult with metrics:
            delta_P_Pa   [Pa]     pressure rise
            W_pump_W     [W]      shaft power consumed
            eta          [-]      pump efficiency used
            mode         str      'ideal' or 'curve'
        """
        warnings = []
        P_in  = inlet.P
        h_in  = inlet.h
        m_dot = inlet.m_dot

        # Liquid density at inlet (needed for volumetric flow)
        rho_in = CP.PropsSI('D', 'P', P_in, 'H', h_in, self.fluid)

        V_dot = m_dot / rho_in   # volumetric flow rate [m³/s]

        # --- Determine pressure rise ---
        if self.mode == 'ideal':
            delta_P = self.delta_P_ideal
        else:
            delta_P = self._interpolate_curve(V_dot)
            if delta_P < 0:
                delta_P = 0.0
                warnings.append("Operating point beyond pump curve runout — ΔP set to 0.")

        # --- Pump work (shaft power) ---
        W_pump = V_dot * delta_P / self.eta    # [W]

        # --- Outlet enthalpy (isentropic assumption) ---
        # h_out = h_in + W_pump / m_dot  (Kokate PhD, Sec. 2.2)
        h_out = h_in + W_pump / m_dot if m_dot > 0 else h_in

        P_out = P_in + delta_P

        outlet = PortState(P=P_out, h=h_out, m_dot=m_dot, fluid=self.fluid)

        metrics = {
            'delta_P_Pa':  delta_P,
            'delta_P_kPa': delta_P / 1e3,
            'W_pump_W':    W_pump,
            'eta':         self.eta,
            'mode':        self.mode,
            'V_dot_m3s':   V_dot,
            'rho_in':      rho_in,
        }

        return ComponentResult(outlet=outlet, metrics=metrics, warnings=warnings)

    # ------------------------------------------------------------------
    # Pump curve interpolation
    # ------------------------------------------------------------------

    def _interpolate_curve(self, V_dot: float) -> float:
        """
        Linear interpolation of pressure head from the pump curve.
        Returns 0 if V_dot is beyond the curve's maximum flow.
        """
        # Simple linear interpolation (no scipy dependency for robustness)
        flows = self._curve_flow
        heads = self._curve_head

        if V_dot <= flows[0]:
            return heads[0]
        if V_dot >= flows[-1]:
            return 0.0   # runout: beyond max flow, no head

        for i in range(len(flows) - 1):
            if flows[i] <= V_dot < flows[i + 1]:
                frac = (V_dot - flows[i]) / (flows[i + 1] - flows[i])
                return heads[i] + frac * (heads[i + 1] - heads[i])

        return 0.0

    # ------------------------------------------------------------------
    # Convenience: get pump curve operating point given system curve
    # ------------------------------------------------------------------

    def operating_point(self, system_dp_func) -> Tuple[float, float]:
        """
        Find pump operating point (V_dot, ΔP) by intersecting pump and
        system curves.

        Only available in 'curve' mode.

        Parameters
        ----------
        system_dp_func : callable
            A function V_dot → system_ΔP [Pa].  Typically obtained from
            Loop.system_curve().

        Returns
        -------
        (V_dot_op, delta_P_op) : operating point [m³/s, Pa]
        """
        if self.mode != 'curve':
            raise RuntimeError(
                "operating_point() is only available in 'curve' mode."
            )
        from scipy.optimize import brentq

        def residual(V):
            return self._interpolate_curve(V) - system_dp_func(V)

        V_min = self._curve_flow[0]
        V_max = self._curve_flow[-1]

        try:
            V_op = brentq(residual, V_min, V_max)
            dP_op = self._interpolate_curve(V_op)
        except ValueError:
            raise RuntimeError(
                "Could not find pump–system intersection. "
                "Check that the system curve crosses the pump curve."
            )

        return V_op, dP_op
