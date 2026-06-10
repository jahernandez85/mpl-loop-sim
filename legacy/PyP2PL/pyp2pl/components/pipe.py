"""
pyp2pl.components.pipe
=======================
Single-phase liquid pipe connecting components in the P2PL.

Models connecting tubes using the Darcy-Weisbach equation with the
Churchill (1977) friction factor.  Heat loss to ambient is neglected
by default (Kokate assumption — perfectly insulated).

Reference
---------
  Kokate PhD Thesis (2024), Sec. 2.2, Table 2.4 (pipe dimensions).
"""

from dataclasses import dataclass

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult
from pyp2pl.correlations.dp_singlephase import single_phase_dp
import CoolProp.CoolProp as CP


@dataclass
class PipeGeometry:
    """
    Circular pipe geometry.
    Defaults approximate Kokate's connecting tubes (Table 2.4).
    """
    L:         float = 0.3      # m    pipe length
    D:         float = 6.35e-3  # m    inner diameter (1/4 inch tube — common in lab)
    roughness: float = 1.5e-6   # m    drawn copper roughness (~1.5 µm)


class Pipe(BaseComponent):
    """
    Single-phase liquid pipe.

    Parameters
    ----------
    fluid : str
    geometry : PipeGeometry, optional

    Example
    -------
    >>> from pyp2pl.components.pipe import Pipe
    >>> from pyp2pl.components.base import PortState
    >>> pipe = Pipe(fluid='R134a', geometry=PipeGeometry(L=0.5, D=6e-3))
    >>> sat = pipe._fp.saturated(P=572.2e3)
    >>> inlet = PortState(P=sat.P_sat, h=sat.h_l, m_dot=5e-3, fluid='R134a')
    >>> result = pipe.compute(inlet)
    >>> print(result.metrics)
    """

    def __init__(self, fluid: str = 'R134a', geometry: PipeGeometry = None):
        super().__init__(fluid)
        self.geo = geometry or PipeGeometry()

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute pipe outlet state.

        Enthalpy is conserved (adiabatic).  Pressure drops by the
        Darcy-Weisbach friction loss.

        Returns
        -------
        ComponentResult with metrics:
            delta_P_Pa  [Pa]   pressure drop
            Re          [-]    Reynolds number
            f           [-]    Darcy friction factor
            u           [m/s]  mean flow velocity
        """
        warnings = []
        P_in  = inlet.P
        h_in  = inlet.h
        m_dot = inlet.m_dot
        geo   = self.geo

        # Liquid properties from CoolProp
        rho = CP.PropsSI('D', 'P', P_in, 'H', h_in, self.fluid)
        mu  = CP.PropsSI('V', 'P', P_in, 'H', h_in, self.fluid)

        dp_result = single_phase_dp(
            m_dot=m_dot, L=geo.L, D=geo.D,
            rho=rho, mu=mu, roughness=geo.roughness,
        )
        delta_P = dp_result.dP

        if dp_result.Re < 2300:
            pass  # laminar — fine
        elif dp_result.Re > 1e5:
            warnings.append(f"High Re={dp_result.Re:.0f}: verify turbulence assumption.")

        P_out  = P_in - delta_P
        h_out  = h_in   # adiabatic

        outlet = PortState(P=P_out, h=h_out, m_dot=m_dot, fluid=self.fluid)

        metrics = {
            'delta_P_Pa':  delta_P,
            'delta_P_kPa': delta_P / 1e3,
            'Re':          dp_result.Re,
            'f':           dp_result.f,
            'u_m_s':       dp_result.u,
        }

        return ComponentResult(outlet=outlet, metrics=metrics, warnings=warnings)
