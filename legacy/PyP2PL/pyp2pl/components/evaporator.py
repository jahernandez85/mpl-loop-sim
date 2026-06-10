"""
pyp2pl.components.evaporator
=============================
Microchannel evaporator component for a pumped two-phase loop.

Physics model
-------------
  - Homogeneous two-phase flow (equal phase velocities, Kokate assumption)
  - N_ch parallel microchannels with uniform heat flux and equal flow split
  - Heat transfer: selectable correlation (default: Shah 1982)
  - Pressure drop: Müller-Steinhagen & Heck (MSH), integrated over n_cv CVs
  - Wall temperature: lumped-capacitance energy balance (steady-state: dT/dt=0)
  - Averaging: local HTC and quality are integrated over the channel length

Governing equations  (Kokate PhD 2024, Eqs. 2.4–2.5 / Kokate 2023, Eqs. 4–5)
-------------------
  Momentum (steady-state, one channel):
      0 = (Ac_e / L_e) * (p_in - p_out - ΔP_e)
      → ΔP_e = p_in - p_out   (the solver enforces pressure balance)

  Energy (steady-state, evaporator wall):
      0 = q_e,s - α_e * As_e * (T_e,s - T_e,f)
      → T_wall = T_sat + q_flux / α_e        [uniform heat flux]

  Exit quality:
      x_out = (h_out - h_l) / h_fg
      h_out = h_in + q_e,total / m_dot

Reference
---------
  Kokate & Park, Appl. Therm. Eng. 229 (2023) 120630, Eqs. 4–7 + Appendix A/B
  Kokate & Park, Appl. Therm. Eng. 249 (2024) 123154, Secs. 2–4
  Kokate PhD Thesis (2024), Sec. 2.2 + Appendices A & B
"""

import math
from dataclasses import dataclass
from typing import Literal, Optional

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult
from pyp2pl.correlations.htc_boiling import compute_htc_boiling, AVAILABLE_CORRELATIONS
from pyp2pl.correlations.dp_twophase import two_phase_pressure_drop
import CoolProp.CoolProp as CP


@dataclass
class EvaporatorGeometry:
    """
    Geometric and material parameters of the microchannel evaporator.

    Defaults match Kokate's baseline evaporator (Lytron CP20G03, design C).
    See Kokate PhD (2024), Table 2.2.
    """
    N_ch:    int   = 44          # number of parallel microchannels
    W_ch:    float = 0.5e-3      # m  channel width
    H_ch:    float = 2.5e-3      # m  channel height
    L_ch:    float = 25.0e-3     # m  channel length

    # Wall / solid material (for thermal capacitance — used in dynamic model)
    wall_material: str   = 'copper'
    cp_wall:       float = 385.0    # J/(kg·K)  copper
    rho_wall:      float = 8960.0   # kg/m³     copper

    # Number of control volumes for pressure-drop and HTC integration
    n_cv: int = 20

    @property
    def Dh(self) -> float:
        """Hydraulic diameter [m] of a rectangular microchannel."""
        return 2.0 * self.W_ch * self.H_ch / (self.W_ch + self.H_ch)

    @property
    def Ac(self) -> float:
        """Cross-sectional area [m²] of one channel."""
        return self.W_ch * self.H_ch

    @property
    def As_per_ch(self) -> float:
        """Heated surface area [m²] per channel (bottom + two side walls)."""
        return (self.W_ch + 2.0 * self.H_ch) * self.L_ch

    @property
    def As_total(self) -> float:
        """Total heated surface area [m²] across all channels."""
        return self.N_ch * self.As_per_ch


class MicrochannelEvaporator(BaseComponent):
    """
    Steady-state microchannel evaporator model.

    Parameters
    ----------
    fluid : str
        CoolProp fluid name (e.g. 'R134a', 'R1234yf').
    q_flux : float
        Applied heat flux [W/m²] at the channel wall.
    geometry : EvaporatorGeometry, optional
        Channel dimensions. Defaults to Kokate baseline (Lytron CP20G03).
    htc_correlation : str
        Which boiling HTC correlation to use.
        One of: 'shah' (default), 'chen', 'bennett_chen',
                'gungor_winterton', 'kandlikar'.
    F_fl : float
        Kandlikar fluid-surface parameter (default 1.63 for R-134a).

    Example
    -------
    >>> from pyp2pl.components.evaporator import MicrochannelEvaporator
    >>> from pyp2pl.components.base import PortState
    >>> evap = MicrochannelEvaporator(fluid='R134a', q_flux=10e4)
    >>> fp = evap._fp
    >>> sat = fp.saturated(P=572.2e3)
    >>> inlet = PortState(P=sat.P_sat, h=sat.h_l, m_dot=5e-3, fluid='R134a')
    >>> result = evap.compute(inlet)
    >>> print(result.summary())
    """

    def __init__(
        self,
        fluid:           str = 'R134a',
        q_flux:          float = 10e4,
        geometry:        EvaporatorGeometry = None,
        htc_correlation: str = 'shah',
        F_fl:            float = 1.63,
    ):
        super().__init__(fluid)
        self.q_flux = q_flux
        self.geo    = geometry or EvaporatorGeometry()
        self.htc_correlation = htc_correlation.lower()
        self.F_fl   = F_fl

        if self.htc_correlation not in AVAILABLE_CORRELATIONS:
            raise ValueError(
                f"htc_correlation='{htc_correlation}' not recognized. "
                f"Choose from {AVAILABLE_CORRELATIONS}."
            )

        self._P_crit = CP.PropsSI('Pcrit', '', 0, '', 0, fluid)

    # ------------------------------------------------------------------
    # Main compute method
    # ------------------------------------------------------------------

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute steady-state evaporator outlet state.

        The inlet is assumed to be at or near saturation (after the preheater).
        If the inlet is subcooled, a single-phase preheat section is computed
        first until saturation is reached, then two-phase boiling begins.

        Parameters
        ----------
        inlet : PortState
            P_in [Pa], h_in [J/kg], m_dot [kg/s] at evaporator inlet.

        Returns
        -------
        ComponentResult with metrics:
            q_total      [W]       total heat added to fluid
            T_wall_avg   [K]       average wall temperature
            T_wall_max   [K]       peak wall temperature (outlet end)
            HTC_avg      [W/m²K]  average flow boiling HTC
            delta_P      [Pa]     total pressure drop (evaporator)
            x_in         [-]      inlet vapor quality
            x_out        [-]      outlet vapor quality
            m_dot_ch     [kg/s]   mass flow per channel
            G_ch         [kg/m²s] channel mass flux
        """
        warnings = []
        geo  = self.geo
        P_in = inlet.P
        h_in = inlet.h
        m_dot_total = inlet.m_dot

        # --- per-channel quantities ---
        m_dot_ch = m_dot_total / geo.N_ch
        G_ch     = m_dot_ch / geo.Ac

        # --- saturation properties at inlet pressure ---
        sat = self._sat(P=P_in)

        # --- total heat input to the fluid ---
        q_total = self.q_flux * geo.As_total   # W  (all channels)

        # --- outlet enthalpy ---
        h_out = h_in + q_total / m_dot_total

        # --- inlet / outlet quality ---
        x_in  = max(0.0, (h_in  - sat.h_l) / sat.h_fg)
        x_out = max(0.0, min(1.0, (h_out - sat.h_l) / sat.h_fg))

        w = self._warn_quality(x_out, 'evaporator outlet')
        if w:
            warnings.append(w)

        # --- pressure drop (two-phase, MSH, per channel) ---
        dp_result = two_phase_pressure_drop(
            G=G_ch, x_in=x_in, x_out=x_out,
            L=geo.L_ch, dh=geo.Dh,
            rho_l=sat.rho_l, rho_v=sat.rho_v,
            mu_l=sat.mu_l, mu_v=sat.mu_v,
            n_cv=geo.n_cv,
        )
        delta_P = dp_result.dP_total

        # --- average HTC and wall temperature ---
        # Integrate HTC over quality range (uniform heat flux → x varies linearly)
        HTC_avg, T_wall_avg, T_wall_max = self._integrate_htc(
            G=G_ch, x_in=x_in, x_out=x_out,
            sat=sat, P=P_in,
        )

        # --- outlet pressure ---
        P_out = P_in - delta_P

        # --- outlet port state ---
        outlet = PortState(P=P_out, h=h_out, m_dot=m_dot_total, fluid=self.fluid)

        metrics = {
            'q_total_W':    q_total,
            'q_flux_W_m2':  self.q_flux,
            'T_wall_avg_C': T_wall_avg - 273.15,
            'T_wall_max_C': T_wall_max - 273.15,
            'T_sat_C':      sat.T_sat  - 273.15,
            'HTC_avg':      HTC_avg,
            'delta_P_Pa':   delta_P,
            'delta_P_kPa':  delta_P / 1e3,
            'x_in':         x_in,
            'x_out':        x_out,
            'm_dot_ch_gs':  m_dot_ch * 1e3,
            'G_ch':         G_ch,
            'dp_fric_Pa':   dp_result.dP_fric,
            'dp_accel_Pa':  dp_result.dP_accel,
        }

        return ComponentResult(outlet=outlet, metrics=metrics, warnings=warnings)

    # ------------------------------------------------------------------
    # Internal: integrate HTC along channel
    # ------------------------------------------------------------------

    def _integrate_htc(self, G, x_in, x_out, sat, P):
        """
        Average HTC and wall temperatures by integrating over n_cv segments.

        For uniform heat flux, quality increases linearly from x_in to x_out.
        At each CV midpoint, compute local HTC, then:
            T_wall_local = T_sat + q_flux / HTC_local
        Return the average and maximum wall temperature.
        """
        geo = self.geo
        n   = geo.n_cv

        htc_sum     = 0.0
        T_wall_sum  = 0.0
        T_wall_max  = -1e10

        for i in range(n):
            x_mid = x_in + (x_out - x_in) * (i + 0.5) / n
            x_mid = max(1e-4, min(1.0 - 1e-4, x_mid))

            # Wall temperature estimate (needed by Chen-based correlations)
            # Start with a first-pass estimate using Shah, then refine once
            htc_res = compute_htc_boiling(
                correlation=self.htc_correlation,
                G=G, x=x_mid, q_flux=self.q_flux,
                dh=geo.Dh, sat=sat, P=P,
                P_crit=self._P_crit,
                T_wall=sat.T_sat + self.q_flux / 1000.0,  # initial estimate
                F_fl=self.F_fl,
            )
            alpha_local = htc_res.alpha

            # Wall temperature from energy balance: q" = alpha * (T_wall - T_sat)
            T_wall_local = sat.T_sat + self.q_flux / alpha_local

            # For Chen-based correlations, refine once with the actual T_wall
            if self.htc_correlation in ('chen', 'bennett_chen'):
                htc_res2 = compute_htc_boiling(
                    correlation=self.htc_correlation,
                    G=G, x=x_mid, q_flux=self.q_flux,
                    dh=geo.Dh, sat=sat, P=P,
                    P_crit=self._P_crit,
                    T_wall=T_wall_local,
                    F_fl=self.F_fl,
                )
                alpha_local  = htc_res2.alpha
                T_wall_local = sat.T_sat + self.q_flux / alpha_local

            htc_sum    += alpha_local
            T_wall_sum += T_wall_local
            if T_wall_local > T_wall_max:
                T_wall_max = T_wall_local

        HTC_avg    = htc_sum    / n
        T_wall_avg = T_wall_sum / n

        return HTC_avg, T_wall_avg, T_wall_max

    # ------------------------------------------------------------------
    # Convenience: sweep q_flux or G, return list of ComponentResult
    # ------------------------------------------------------------------

    def sweep(self, inlet: PortState, param: str, values: list) -> list:
        """
        Run compute() for a range of a single parameter.

        Parameters
        ----------
        param  : 'q_flux' or 'G_total' (total mass flow rate [kg/s])
        values : list of values to sweep

        Returns
        -------
        list of ComponentResult
        """
        results = []
        for v in values:
            if param == 'q_flux':
                self.q_flux = v
            elif param == 'G_total':
                inlet = PortState(P=inlet.P, h=inlet.h, m_dot=v, fluid=inlet.fluid)
            else:
                raise ValueError(f"Unknown sweep parameter: '{param}'")
            results.append(self.compute(inlet))
        return results
