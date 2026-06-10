"""
pyp2pl.components.preheater
============================
Preheater for a pumped two-phase loop.

Raises subcooled liquid from pump outlet temperature to saturation temperature
(or to a user-specified subcooling level) before the evaporator inlet.

Physics model
-------------
  NTU-effectiveness method (parallel-flow or counter-flow HX).
  The heating medium is an electrical heater (constant heat input) in
  Kokate's experimental setup, modelled as a wall at fixed temperature.
  In the numerical model (Kokate 2023, Eq. 15), it is treated as a
  single-stream HX with a known UA.

  Steady-state energy balance (Kokate PhD 2024, Eq. 2.6):
      0 = q_ph,s - ε_ph * C_min,ph * (T_ph,s - T_ph,f,i)
      → q_to_fluid = ε_ph * C_min,ph * (T_wall - T_in)

  Target: bring fluid to x = 0 (saturated liquid) at the outlet,
          or to a specified subcooling ΔT_sub below T_sat.

Reference
---------
  Kokate & Park, Appl. Therm. Eng. 229 (2023), Eq. 15
  Kokate PhD Thesis (2024), Eq. 2.6
"""

import math
from dataclasses import dataclass
from typing import Optional

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult
import CoolProp.CoolProp as CP


@dataclass
class PreheaterGeometry:
    """
    Preheater dimensions.
    Defaults match Kokate's preheater (Lytron CP30G01).
    See Kokate PhD (2024), Table 2.3.
    """
    UA:          float = 150.0    # W/K  overall heat transfer * area product
    # Alternatively, the user can specify plate geometry and let the code
    # compute UA from Kumar correlation (future extension).


class Preheater(BaseComponent):
    """
    Steady-state preheater model.

    Brings subcooled liquid to saturation (or a specified subcooling) using
    an NTU-effectiveness model.

    Two operating modes
    -------------------
    'target_sat' (default)
        The preheater delivers exactly enough heat to reach x=0 at the outlet,
        regardless of UA. This is Kokate's assumption: the preheater is
        always sized/controlled to deliver saturated liquid. In this mode,
        q_input is computed from the energy balance, not from UA.

    'fixed_UA'
        The preheater uses its fixed UA and a known wall/secondary-fluid
        temperature to compute the actual heat delivered. The outlet may
        be subcooled or (if over-powered) slightly superheated.

    Parameters
    ----------
    fluid : str
    mode  : 'target_sat' | 'fixed_UA'
    UA    : float [W/K]   only used in 'fixed_UA' mode
    T_source : float [K]  heat source temperature (wall or secondary fluid)
                          only used in 'fixed_UA' mode
    subcooling_target_K : float [K]
        Desired subcooling at outlet (default 0 = saturated liquid).
        Only used in 'target_sat' mode.

    Example
    -------
    >>> from pyp2pl.components.preheater import Preheater
    >>> from pyp2pl.components.base import PortState
    >>> preh = Preheater(fluid='R134a', mode='target_sat')
    >>> fp = preh._fp
    >>> sat = fp.saturated(P=572.2e3)
    >>> # Inlet: subcooled liquid at 15°C
    >>> h_sub = CP.PropsSI('H','T',288.15,'P',sat.P_sat,'R134a')
    >>> inlet = PortState(P=sat.P_sat, h=h_sub, m_dot=5e-3, fluid='R134a')
    >>> result = preh.compute(inlet)
    >>> print(result.summary())
    """

    def __init__(
        self,
        fluid:                  str   = 'R134a',
        mode:                   str   = 'target_sat',
        UA:                     float = 150.0,
        T_source:               float = 310.0,   # K
        subcooling_target_K:    float = 0.0,
    ):
        super().__init__(fluid)
        self.mode                = mode.lower()
        self.UA                  = UA
        self.T_source            = T_source
        self.subcooling_target_K = subcooling_target_K

        if self.mode not in ('target_sat', 'fixed_ua'):
            raise ValueError("mode must be 'target_sat' or 'fixed_UA'")

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute preheater outlet state.

        Parameters
        ----------
        inlet : PortState
            Subcooled liquid from pump outlet or reservoir.

        Returns
        -------
        ComponentResult with metrics:
            q_input_W    [W]    heat delivered to fluid
            T_in_C       [°C]   inlet temperature
            T_out_C      [°C]   outlet temperature
            subcooling_K [K]    subcooling at outlet (0 = saturated)
            delta_P_Pa   [Pa]   pressure drop (assumed negligible, = 0)
        """
        warnings = []
        P_in  = inlet.P
        h_in  = inlet.h
        m_dot = inlet.m_dot

        sat = self._sat(P=P_in)

        # Inlet temperature
        T_in = CP.PropsSI('T', 'P', P_in, 'H', h_in, self.fluid)

        if self.mode == 'target_sat':
            # Deliver exactly enough heat to reach h_l (± subcooling target)
            h_target = sat.h_l - m_dot * sat.cp_l * self.subcooling_target_K / m_dot \
                       if self.subcooling_target_K > 0 else sat.h_l
            # Clamp: if inlet is already at or above saturation, no heat needed
            h_target = max(h_in, h_target)
            q_input  = m_dot * (h_target - h_in)
            h_out    = h_target

        else:  # fixed_UA mode
            # NTU-effectiveness: single fluid stream, wall at T_source
            cp = sat.cp_l
            C  = m_dot * cp
            NTU = self.UA / C
            epsilon = 1.0 - math.exp(-NTU)
            q_input = epsilon * C * (self.T_source - T_in)
            q_input = max(0.0, q_input)
            h_out   = h_in + q_input / m_dot

        # Outlet temperature and subcooling
        T_out = CP.PropsSI('T', 'P', P_in, 'H', h_out, self.fluid)
        subcooling = sat.T_sat - T_out

        # Pressure drop across preheater is neglected (Kokate assumption)
        delta_P = 0.0
        P_out   = P_in

        outlet = PortState(P=P_out, h=h_out, m_dot=m_dot, fluid=self.fluid)

        metrics = {
            'q_input_W':    q_input,
            'T_in_C':       T_in  - 273.15,
            'T_out_C':      T_out - 273.15,
            'T_sat_C':      sat.T_sat - 273.15,
            'subcooling_K': subcooling,
            'delta_P_Pa':   delta_P,
        }

        return ComponentResult(outlet=outlet, metrics=metrics, warnings=warnings)
