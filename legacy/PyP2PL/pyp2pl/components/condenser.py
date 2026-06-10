"""
pyp2pl.components.condenser
============================
Flat-plate condenser for a pumped two-phase loop.

Physics model
-------------
  Two sections in series:
    1. Condensation section  : two-phase fluid condenses at T_sat
       - HTC from Yan et al. (1999) for plate HX
       - ΔP from Yan friction correlation
    2. Subcooling section    : single-phase liquid cools below T_sat
       - HTC from Kumar (1984) for plate HX
       - ΔP from Kumar friction correlation
       - NTU-effectiveness method (counter-flow)

  The chiller loop (coolant side) is modelled as a constant-temperature
  or finite-capacity stream depending on user input.

Governing equations  (Kokate PhD 2024, Eqs. 2.9–2.12 / Kokate 2023, Eqs. 8–12)
-------------------
  Condensation section (two-phase → saturated liquid):
      q_cond = m_dot * (h_in - h_l)   = m_dot * x_in * h_fg

  Subcooling section (NTU-effectiveness):
      epsilon = 1 - exp(-NTU_cl)           [Cr → 0, condensation limit]
      epsilon = (1 - exp[-NTU(1-Cr)]) / (1 - Cr*exp[-NTU(1-Cr)])   [general]
      NTU     = alpha * As / C_min
      q_subcool = epsilon * C_min * (T_sat - T_cl_in)

  Total heat rejection:
      q_total = q_cond + q_subcool

Reference
---------
  Kokate & Park, Appl. Therm. Eng. 229 (2023), Eqs. 8–12 + Appendix
  Kokate PhD Thesis (2024), Sec. 2.2, Eqs. 2.9–2.12
"""

import math
from dataclasses import dataclass
from typing import Optional

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pyp2pl.components.base import BaseComponent, PortState, ComponentResult
from pyp2pl.correlations.dp_plate import yan_condensation, kumar_plate
import CoolProp.CoolProp as CP


@dataclass
class CondenserGeometry:
    """
    Flat-plate condenser geometry.
    Defaults match Kokate's condenser (McMaster-Carr 8546T12).
    See Kokate PhD (2024), Table 2.3.
    """
    N_plates:    int   = 30        # total number of plates
    L_plate:     float = 0.119     # m  active plate length
    W_plate:     float = 0.043     # m  plate width
    gap:         float = 2.0e-3    # m  channel gap between plates
    plate_angle: float = 60.0      # °  chevron angle

    @property
    def N_ch(self) -> int:
        """Number of channels on the refrigerant side."""
        return max(1, self.N_plates - 1)

    @property
    def Dh(self) -> float:
        """Hydraulic diameter [m] of a plate channel ≈ 2 * gap."""
        return 2.0 * self.gap

    @property
    def Ac_ch(self) -> float:
        """Cross-section area [m²] per channel."""
        return self.W_plate * self.gap

    @property
    def As_per_ch(self) -> float:
        """Heat transfer area [m²] per channel (one plate face)."""
        return self.L_plate * self.W_plate

    @property
    def As_total(self) -> float:
        """Total heat transfer area [m²] on refrigerant side."""
        return self.N_ch * self.As_per_ch


class FlatPlateCondenser(BaseComponent):
    """
    Steady-state flat-plate condenser model.

    Parameters
    ----------
    fluid : str
        CoolProp fluid name for the refrigerant.
    T_coolant_in : float
        Chiller loop coolant inlet temperature [K].
    m_dot_coolant : float, optional
        Coolant mass flow rate [kg/s].  If None, an 'infinite capacity'
        coolant is assumed (T_coolant = const = T_coolant_in throughout).
    coolant_fluid : str
        CoolProp name for the coolant (default 'Water').
        Kokate uses 50/50 EGW; use 'INCOMP::MEG[0.5]' for that mixture.
    geometry : CondenserGeometry, optional
        Plate dimensions. Defaults to Kokate baseline condenser.
    subcooling_K : float
        Target subcooling [K] at condenser outlet. Set to 0 for saturated
        liquid outlet. The model calculates the achievable subcooling
        given the coolant conditions.

    Example
    -------
    >>> from pyp2pl.components.condenser import FlatPlateCondenser
    >>> from pyp2pl.components.base import PortState
    >>> cond = FlatPlateCondenser(fluid='R134a', T_coolant_in=278.15)
    >>> sat = cond._fp.saturated(P=572.2e3)
    >>> inlet = PortState(P=sat.P_sat, h=sat.h_v, m_dot=5e-3, fluid='R134a')
    >>> result = cond.compute(inlet)
    >>> print(result.summary())
    """

    def __init__(
        self,
        fluid:          str   = 'R134a',
        T_coolant_in:   float = 278.15,     # K  (5°C — Kokate baseline)
        m_dot_coolant:  Optional[float] = None,
        coolant_fluid:  str   = 'Water',
        geometry:       CondenserGeometry = None,
        subcooling_K:   float = 0.0,
    ):
        super().__init__(fluid)
        self.T_cl_in       = T_coolant_in
        self.m_dot_coolant = m_dot_coolant
        self.coolant_fluid = coolant_fluid
        self.geo           = geometry or CondenserGeometry()
        self.subcooling_K  = subcooling_K

    # ------------------------------------------------------------------
    # Main compute method
    # ------------------------------------------------------------------

    def compute(self, inlet: PortState) -> ComponentResult:
        """
        Compute steady-state condenser outlet state.

        Splits the condenser into condensation + subcooling sections.
        Uses NTU-effectiveness for the subcooling section.

        Parameters
        ----------
        inlet : PortState
            Two-phase (or slightly superheated) refrigerant at condenser inlet.

        Returns
        -------
        ComponentResult with metrics:
            q_cond_W       [W]   heat removed in condensation section
            q_subcool_W    [W]   heat removed in subcooling section
            q_total_W      [W]   total heat rejected
            T_out_C        [°C]  refrigerant outlet temperature
            subcooling_K   [K]   actual subcooling achieved
            T_wall_cond_C  [°C]  avg wall temperature in condensation section
            delta_P_Pa     [Pa]  total refrigerant-side pressure drop
            x_in           [-]   inlet vapor quality
        """
        warnings = []
        geo   = self.geo
        P_in  = inlet.P
        h_in  = inlet.h
        m_dot = inlet.m_dot

        # Saturation properties at inlet pressure
        sat = self._sat(P=P_in)

        # Per-channel mass flux
        m_dot_ch = m_dot / geo.N_ch
        G_ch     = m_dot_ch / geo.Ac_ch

        # Inlet quality
        x_in = max(0.0, min(1.0, (h_in - sat.h_l) / sat.h_fg))

        # ---- Section 1: Condensation (two-phase → saturated liquid) --------
        q_cond = m_dot * x_in * sat.h_fg   # [W]
        h_after_cond = sat.h_l             # saturated liquid

        # Condensation HTC and ΔP (Yan correlation)
        yan_htc, yan_dp = yan_condensation(
            G=G_ch, x_in=x_in, x_out=0.0,
            Dh=geo.Dh, L_plate=geo.L_plate,
            rho_l=sat.rho_l, rho_v=sat.rho_v,
            mu_l=sat.mu_l, mu_v=sat.mu_v,
            k_l=sat.k_l, cp_l=sat.cp_l,
            h_fg=sat.h_fg, P=P_in,
        )
        alpha_cond = yan_htc.alpha
        dP_cond    = yan_dp.dP * geo.N_ch  # total across all channels

        # Wall temperature in condensation section
        # q" = alpha_cond * (T_wall - T_sat)  → T_wall = T_sat + q"/alpha
        q_flux_cond = q_cond / geo.As_total if geo.As_total > 0 else 0.0
        T_wall_cond = sat.T_sat + q_flux_cond / alpha_cond if alpha_cond > 0 else sat.T_sat

        # ---- Section 2: Subcooling (single-phase liquid below T_sat) -------
        P_after_cond = P_in - dP_cond

        # Coolant capacity
        if self.m_dot_coolant is not None:
            try:
                cp_cl = CP.PropsSI('C', 'T', self.T_cl_in, 'P', 101325, self.coolant_fluid)
            except Exception:
                cp_cl = 4000.0  # fallback for EGW
            C_cl = self.m_dot_coolant * cp_cl
        else:
            C_cl = 1e12   # infinite coolant capacity

        # Refrigerant capacity in subcooling section (liquid)
        cp_l = sat.cp_l
        C_ref = m_dot * cp_l

        C_min = min(C_ref, C_cl)
        C_max = max(C_ref, C_cl)
        Cr    = C_min / C_max if C_max > 0 else 0.0

        # Kumar HTC for subcooling section
        # Use liquid properties at roughly T_sat (conservative)
        kumar_htc, kumar_dp_result = kumar_plate(
            m_dot_ch=m_dot_ch,
            Dh=geo.Dh,
            A_ch=geo.Ac_ch,
            rho=sat.rho_l,
            mu=sat.mu_l,
            k=sat.k_l,
            Pr=sat.Pr_l,
            L_plate=geo.L_plate,
            plate_angle_deg=geo.plate_angle,
        )
        alpha_subcool = kumar_htc.alpha

        # NTU-effectiveness (counter-flow)
        NTU = alpha_subcool * geo.As_total / C_min if C_min > 0 else 0.0
        epsilon = self._ntu_effectiveness(NTU, Cr)

        # Achievable subcooling heat transfer
        q_subcool = epsilon * C_min * (sat.T_sat - self.T_cl_in)
        q_subcool = max(0.0, q_subcool)

        # Outlet enthalpy of refrigerant
        h_out = h_after_cond - q_subcool / m_dot

        # Actual subcooling
        T_out   = sat.T_sat - q_subcool / C_ref
        subcool = sat.T_sat - T_out

        # Total pressure drop
        dP_subcool = kumar_dp_result.dP * geo.N_ch
        delta_P    = dP_cond + dP_subcool

        P_out = P_in - delta_P
        outlet = PortState(P=P_out, h=h_out, m_dot=m_dot, fluid=self.fluid)

        metrics = {
            'q_cond_W':      q_cond,
            'q_subcool_W':   q_subcool,
            'q_total_W':     q_cond + q_subcool,
            'T_out_C':       T_out - 273.15,
            'T_sat_C':       sat.T_sat - 273.15,
            'subcooling_K':  subcool,
            'T_wall_cond_C': T_wall_cond - 273.15,
            'HTC_cond':      alpha_cond,
            'HTC_subcool':   alpha_subcool,
            'delta_P_Pa':    delta_P,
            'delta_P_kPa':   delta_P / 1e3,
            'dP_cond_Pa':    dP_cond,
            'dP_subcool_Pa': dP_subcool,
            'x_in':          x_in,
            'NTU':           NTU,
            'epsilon':       epsilon,
            'G_ch':          G_ch,
        }

        return ComponentResult(outlet=outlet, metrics=metrics, warnings=warnings)

    # ------------------------------------------------------------------
    # NTU-effectiveness for counter-flow HX
    # ------------------------------------------------------------------

    @staticmethod
    def _ntu_effectiveness(NTU: float, Cr: float) -> float:
        """
        Counter-flow heat exchanger effectiveness.

        Eq. 2.7 in Kokate PhD (2024):
            ε = (1 - exp[-NTU(1-Cr)]) / (1 - Cr·exp[-NTU(1-Cr)])

        For Cr → 0 (condensation):
            ε = 1 - exp(-NTU)
        """
        if NTU <= 0:
            return 0.0
        if Cr < 1e-6:
            return 1.0 - math.exp(-NTU)
        num = 1.0 - math.exp(-NTU * (1.0 - Cr))
        den = 1.0 - Cr * math.exp(-NTU * (1.0 - Cr))
        return num / den if abs(den) > 1e-12 else 1.0
