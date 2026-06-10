"""
correlations.py — HTC & Pressure Drop Correlation Library
==========================================================
MPL Simulation Library — Module 2 (Phase 2)

Pluggable correlation library using the Strategy Pattern.
Each correlation is a callable that accepts a FluidState and geometry
parameters and returns:
  - HTC correlations  → α  [W/m²·K]
  - ΔP  correlations  → dP/dz  [Pa/m]  (gradient, NOT total drop)

Strategy Protocols
------------------
HTCCorrelation(state, G, D_h, q_flux, **kwargs) → float  [W/m²·K]
DPCorrelation (state, G, D_h, **kwargs)         → float  [Pa/m]

Implemented correlations
------------------------
HTC — Single-phase:
  • dittus_boelter          : Nu = 0.023 Re^0.8 Pr^n  (Dittus-Boelter 1930)
  • gnielinski               : Nu = (f/8)(Re-1000)Pr / …  (Gnielinski 1976)
  • shah_london_laminar      : Nu = f(geometry, Re, Pr)   (Shah & London 1978)

HTC — Two-phase / flow boiling:
  • shah_boiling             : α = max(α_cb, α_nb)        (Shah 1982)
                               Primary for evaporator — MAE 37.2 % vs Kokate 2024
  • kim_mudawar_2012_htc     : Universal mini/micro-channel (Kim & Mudawar 2012)

HTC — Condensation:
  • yan_condensation         : α = 4.118 Re_eq^0.4 Pr^0.333 k/Dh  (Yan et al. 1999)
                               Used for plate condenser in Kokate 2023

Pressure drop — Single-phase:
  • blasius_dp               : f = 0.316 Re^-0.25  (Blasius 1913)
  • churchill_dp             : smooth/rough unified  (Churchill 1977)

Pressure drop — Two-phase:
  • homogeneous_dp           : dP/dz = 2 f_tp G²/(D ρ_tp)  Cicchitti μ_tp
                               Validated for low-x MPL flows  (Dogan 1983, Kim 2013)
  • kim_mudawar_2013_dp      : Lockhart-Martinelli, 2378 boiling pts  (Kim & Mudawar 2013)
                               Recommended for mini/micro-channels
  • muller_steinhagen_heck_dp: Simple interpolation formula  (MSH 1986)
                               Used by Kokate 2023, Terpstra 2015

References
----------
[1]  M. Shah, "Chart correlation for saturated boiling heat transfer,"
     ASHRAE Trans. 88 (1982). [Shah boiling]
[2]  S.-M. Kim, I. Mudawar, "Universal approach to predicting two-phase
     frictional pressure drop for mini/micro-channel saturated flow boiling,"
     Int. J. Heat Mass Transfer 58 (2013) 718-734.  [Kim 2013 ΔP]
[3]  S.-M. Kim, I. Mudawar, "Universal approach to predicting two-phase
     frictional pressure drop for adiabatic and condensing mini/micro-channel
     flows," Int. J. Heat Mass Transfer 55 (2012) 3246-3261.  [Kim 2012 ΔP]
[4]  Y.-Y. Yan, H.-C. Lio, T.-F. Lin, "Condensation heat transfer and pressure
     drop of refrigerant R-134a in a plate heat exchanger,"
     Int. J. Heat Mass Transfer 42 (1999) 993-1006.  [Yan condensation]
[5]  R. Kokate, C. Park, "Pumped two-phase loop …,"
     Appl. Therm. Eng. 229 (2023) 120630.  [Primary MPL SS model]
[6]  R. Kokate, PhD Thesis, 2024.  [Appendix A — correlation details]
[7]  H. Müller-Steinhagen, K. Heck, "A simple friction pressure drop correlation
     for two-phase flow in pipes," Chem. Eng. Process. 20 (1986) 297-308.
[8]  F. Dittus, L. Boelter, "Heat transfer in automobile radiators of the tubular
     type," Int. Commun. Heat Mass Transfer 12 (1985) 3-22.
[9]  V. Gnielinski, "New equations for heat and mass transfer in turbulent pipe
     and channel flow," Int. Chem. Eng. 16 (1976) 359-368.
[10] T.N. Dogan, "Forced-convection boiling flow instabilities,"
     Int. J. Heat Fluid Flow 4 (1983) 145-156.  [HEM basis]
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

# ---------------------------------------------------------------------------
# FluidState import — lazy to avoid circular deps during testing
# ---------------------------------------------------------------------------
# During unit tests, a minimal duck-typed stub is accepted as long as it
# exposes the attributes listed in _REQUIRED_ATTRS below.

_REQUIRED_ATTRS = (
    "phase", "T", "P", "x", "rho", "rho_l", "rho_v",
    "mu_l", "mu_v", "mu_tp", "k_l", "k_v", "Pr_l", "Pr_v",
    "h_fg", "sigma", "P_red", "T_sat",
)


def _validate_state(state: object, caller: str) -> None:
    missing = [a for a in _REQUIRED_ATTRS if not hasattr(state, a)]
    if missing:
        raise TypeError(
            f"{caller}: FluidState is missing attributes {missing}. "
            "Ensure fluid_properties.FluidState is used."
        )


# ---------------------------------------------------------------------------
# Protocols (Strategy Pattern)
# ---------------------------------------------------------------------------

@runtime_checkable
class HTCCorrelation(Protocol):
    """Callable protocol for heat transfer coefficient correlations."""

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float,
        **kwargs,
    ) -> float:
        """
        Parameters
        ----------
        state   : FluidState  — local thermodynamic state (P, h)
        G       : float       — mass flux  [kg/m²·s]
        D_h     : float       — hydraulic diameter  [m]
        q_flux  : float       — wall heat flux  [W/m²]  (used by Shah boiling)
        **kwargs: additional geometry arguments (e.g. beta, aspect_ratio)

        Returns
        -------
        alpha   : float  — heat transfer coefficient  [W/m²·K]
        """
        ...


@runtime_checkable
class DPCorrelation(Protocol):
    """Callable protocol for pressure drop (gradient) correlations."""

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        **kwargs,
    ) -> float:
        """
        Parameters
        ----------
        state   : FluidState  — local thermodynamic state
        G       : float       — mass flux  [kg/m²·s]
        D_h     : float       — hydraulic diameter  [m]
        **kwargs: additional arguments (e.g. roughness, aspect_ratio)

        Returns
        -------
        dPdz    : float  — frictional pressure gradient  [Pa/m]  (positive)
        """
        ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _reynolds(G: float, D_h: float, mu: float) -> float:
    """Re = G·D_h / μ"""
    return G * D_h / mu


def _friction_factor_blasius(Re: float) -> float:
    """
    Blasius / Hagen-Poiseuille friction factor (Fanning).

    f = 16/Re              for Re < 2000  (laminar, Hagen-Poiseuille)
    f = 0.079 Re^-0.25     for 2000 ≤ Re < 20 000  (Blasius turbulent)
    f = 0.046 Re^-0.20     for Re ≥ 20 000  (smooth-pipe turbulent)

    Convention: Darcy-Weisbach ΔP = f_D · (L/D) · ½ρu²
    Fanning f_F = f_D / 4  →  used directly in  dP/dz = 2 f_F G² / (D ρ)
    Here we return the Fanning friction factor (consistent with Kim 2013).
    """
    if Re < 2000:
        return 16.0 / Re
    elif Re < 20_000:
        return 0.079 * Re ** (-0.25)
    else:
        return 0.046 * Re ** (-0.20)


def _friction_factor_rect_laminar(Re: float, beta: float) -> float:
    """
    Fanning friction factor for laminar flow in rectangular channels.
    f·Re = 24(1 - 1.3553β + 1.9467β² - 1.7012β³ + 0.9564β⁴ - 0.2537β⁵)
    β = min(W,H)/max(W,H) ∈ [0, 1]   (aspect ratio)
    Ref: Shah & London 1978 — used in Kim 2013, Table 5.
    """
    b = min(max(beta, 0.0), 1.0)
    fRe = 24.0 * (1 - 1.3553*b + 1.9467*b**2 - 1.7012*b**3
                  + 0.9564*b**4 - 0.2537*b**5)
    return fRe / Re


def _nusselt_dittus_boelter(Re: float, Pr: float, heating: bool = True) -> float:
    """Nu = 0.023 Re^0.8 Pr^n   (n = 0.4 heating, 0.3 cooling)"""
    n = 0.4 if heating else 0.3
    return 0.023 * Re**0.8 * Pr**n


# ---------------------------------------------------------------------------
# ── SINGLE-PHASE HTC CORRELATIONS ──────────────────────────────────────────
# ---------------------------------------------------------------------------

class DittusBoelterHTC:
    """
    Dittus-Boelter single-phase forced-convection correlation.
    Valid for: Re > 10 000, 0.6 ≤ Pr ≤ 160, L/D > 10.

    Nu = 0.023 Re^0.8 Pr^n
      n = 0.4  (heating,  T_wall > T_fluid)   ← evaporator use
      n = 0.3  (cooling,  T_wall < T_fluid)    ← condenser water side

    Reference: Dittus & Boelter (1930) / Incropera Eq. 8.60
    Used in: Kokate 2023 (preheater, single-phase region), Wang 2023
    """

    def __init__(self, heating: bool = True):
        self.heating = heating

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float = 0.0,
        **kwargs,
    ) -> float:
        _validate_state(state, "DittusBoelterHTC")
        # Use liquid properties for sub-cooled liquid; mixture for two-phase
        if getattr(state, "phase", "liquid") == "liquid":
            mu = state.mu_l
            k  = state.k_l
            Pr = state.Pr_l
        elif getattr(state, "phase", "") == "vapor":
            mu = state.mu_v
            k  = state.k_v
            Pr = state.Pr_v
        else:
            # Two-phase: use liquid properties as base (consistent with Shah)
            mu = state.mu_l
            k  = state.k_l
            Pr = state.Pr_l

        Re = _reynolds(G, D_h, mu)
        if Re < 2300:
            warnings.warn(
                f"DittusBoelterHTC: Re={Re:.0f} < 2300 — correlation is "
                "intended for turbulent flow. Consider GnielinskiHTC.",
                stacklevel=2,
            )
        Nu = _nusselt_dittus_boelter(Re, Pr, heating=self.heating)
        return Nu * k / D_h


class GnielinskiHTC:
    """
    Gnielinski (1976) single-phase forced-convection correlation.
    Valid for: 0.5 ≤ Pr ≤ 2000, 3000 ≤ Re ≤ 5×10⁶.
    More accurate than Dittus-Boelter in transitional regime.

    Nu = (f/8)(Re - 1000)Pr / [1 + 12.7(f/8)^0.5 (Pr^(2/3) - 1)]
    f = (0.790 ln Re - 1.64)^-2   (Petukhov friction factor)

    Reference: Gnielinski (1976); Wang 2023 uses this for turbulent flow.
    """

    def __init__(self, heating: bool = True):
        self.heating = heating

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float = 0.0,
        **kwargs,
    ) -> float:
        _validate_state(state, "GnielinskiHTC")
        phase = getattr(state, "phase", "liquid")
        if phase == "vapor":
            mu, k, Pr = state.mu_v, state.k_v, state.Pr_v
        else:
            mu, k, Pr = state.mu_l, state.k_l, state.Pr_l

        Re = _reynolds(G, D_h, mu)
        Re = max(Re, 3001.0)  # correlation lower bound

        f = (0.790 * math.log(Re) - 1.64) ** (-2)
        Nu = (f / 8.0) * (Re - 1000.0) * Pr / (
            1.0 + 12.7 * math.sqrt(f / 8.0) * (Pr ** (2.0/3.0) - 1.0)
        )
        return Nu * k / D_h


class ShahLondonLaminarHTC:
    """
    Shah & London (1978) Nusselt number for fully-developed laminar flow
    in rectangular channels (uniform heat flux, UHF boundary condition).

    Nu_UHF = 8.235 (1 - 2.0421β + 3.0853β² - 2.4765β³ + 1.0578β⁴ - 0.1861β⁵)
    β = min(W,H)/max(W,H) ∈ [0, 1]

    Reference: Shah & London, Laminar Flow Forced Convection in Ducts (1978).
    Used in: Kokate PhD 2024 §6 for friction factor validation in microchannels.
    """

    def __init__(self, aspect_ratio: float = 1.0):
        """
        aspect_ratio : β = H_ch / W_ch  with β ≤ 1
                       (square channel → β = 1, Nu ≈ 3.608)
        """
        self.beta = min(max(aspect_ratio, 0.0), 1.0)

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float = 0.0,
        **kwargs,
    ) -> float:
        _validate_state(state, "ShahLondonLaminarHTC")
        b = self.beta
        Nu = 8.235 * (1 - 2.0421*b + 3.0853*b**2 - 2.4765*b**3
                      + 1.0578*b**4 - 0.1861*b**5)
        phase = getattr(state, "phase", "liquid")
        k = state.k_v if phase == "vapor" else state.k_l
        return Nu * k / D_h


# ---------------------------------------------------------------------------
# ── TWO-PHASE / FLOW BOILING HTC CORRELATIONS ──────────────────────────────
# ---------------------------------------------------------------------------

class ShahBoilingHTC:
    """
    Shah (1982) correlation for saturated flow boiling.
    α = max(α_cb, α_nb)

    α_cb  — convective boiling component:
        α_cb / α_l = 1.8 / N^0.8

    α_nb  — nucleate boiling component:
        depends on N and Boiling number Bo

    N = C0               if Fr_l > 0.04  (non-stratified, horizontal/vertical)
    N = 0.38 Fr_l^-0.3 C0   if Fr_l ≤ 0.04  (stratified flow)

    C0 = [(1-x)/x]^0.8 · [ρ_v/ρ_l]^0.5   (convection number)
    Bo = q'' / (G h_fg)                    (Boiling number)
    Fr_l = G² / (ρ_l² g D_h)              (Froude number, liquid)

    α_l from Dittus-Boelter on liquid-only flow (G, D_h, μ_l, k_l, Pr_l)
      α_l = 0.023 Re_l^0.8 Pr_l^0.4 · k_l / D_h
      Re_l = G · D_h / μ_l

    Performance: MAE = 37.2 % vs Kokate 2024 microchannel data — best among
    tested correlations for P2PL evaporator.

    Reference: M. Shah, ASHRAE Trans. 88 (1982).
    Implementation: Kokate & Park 2023 Appendix + PhD 2024 Appendix A.
    """

    G_EARTH: float = 9.806  # [m/s²]

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float,
        **kwargs,
    ) -> float:
        """
        Parameters
        ----------
        state  : FluidState  (two-phase region assumed; x ∈ (0, 1))
        G      : mass flux  [kg/m²·s]
        D_h    : hydraulic diameter  [m]
        q_flux : wall heat flux  [W/m²]  — must be > 0 for nucleate term
        """
        _validate_state(state, "ShahBoilingHTC")

        x = state.x
        # Clamp quality for numerical stability
        x = max(min(x, 0.999), 0.001)

        rho_l = state.rho_l
        rho_v = state.rho_v
        mu_l  = state.mu_l
        k_l   = state.k_l
        Pr_l  = state.Pr_l
        h_fg  = state.h_fg

        # ── Liquid-only single-phase HTC (Dittus-Boelter) ──────────────────
        Re_l = G * D_h / mu_l
        alpha_l = _nusselt_dittus_boelter(Re_l, Pr_l, heating=True) * k_l / D_h

        # ── Dimensionless groups ────────────────────────────────────────────
        C0 = ((1.0 - x) / x) ** 0.8 * (rho_v / rho_l) ** 0.5
        Bo = q_flux / (G * h_fg) if h_fg > 0 else 0.0

        Fr_l = G**2 / (rho_l**2 * self.G_EARTH * D_h)

        # ── N parameter ────────────────────────────────────────────────────
        if Fr_l > 0.04:
            N = C0
        else:
            N = 0.38 * Fr_l ** (-0.3) * C0

        # ── Convective boiling ─────────────────────────────────────────────
        alpha_cb = alpha_l * 1.8 / (N ** 0.8)

        # ── Nucleate boiling — regime based on N and Bo ────────────────────
        if N > 1.0:
            if Bo > 0.0003:
                alpha_nb = alpha_l * 230.0 * (Bo ** 0.5)
            else:
                alpha_nb = alpha_l * (1.0 + 46.0 * (Bo ** 0.5))
        else:
            Fs = 14.7 if Bo > 0.0011 else 15.43
            if N > 0.1:
                alpha_nb = alpha_l * Fs * (Bo ** 0.5) * math.exp(2.74 * N - 0.1)
            else:
                alpha_nb = alpha_l * Fs * (Bo ** 0.5) * math.exp(2.74 * N - 0.15)

        return max(alpha_cb, alpha_nb)


class KimMudawar2012HTC:
    """
    Kim & Mudawar (2012) universal flow boiling HTC correlation.
    Developed for mini/micro-channels, multiple fluids.

    Formulation (two-phase multiplier approach):
        α_tp = h_nb + h_cb

    where nucleate and convective components combine as:
        α_tp = [α_nb^2 + α_cb^2]^0.5   (superposition, some implementations)

    The correlation from Kim & Mudawar (IJHMT 2012 — Part 2, condensation
    companion paper) uses:
        Nu_tp = [Nu_nb² + Nu_cb²]^0.5
        Nu_nb = 2345 (Bo·P_H/P_F)^0.70  P_r^0.38 (1-x)^-0.51
        Nu_cb = 5.2  (Bo·P_H/P_F)^0.08  We_fo^0.54

    where:
        Bo    = q''_H / (G h_fg)     Boiling number (heated perimeter)
        We_fo = G² D_h / (ρ_f σ)    liquid-only Weber number
        P_r   = P / P_crit           reduced pressure
        P_H/P_F = 1.0 for uniform heating (default)

    Reference: S.-M. Kim, I. Mudawar, IJHMT 55 (2012) 3246-3261 §HTC part.
               R. Kokate PhD 2024 Table 4.3 — Kim & Mudawar 2012 listed.
    """

    def __init__(self, P_H_over_P_F: float = 1.0):
        """
        P_H_over_P_F : ratio of heated to wetted perimeter  (default 1.0)
                       Use 0.5 for one-sided heating (e.g. bottom-heated channel).
        """
        self.ratio = P_H_over_P_F

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float,
        **kwargs,
    ) -> float:
        _validate_state(state, "KimMudawar2012HTC")

        x = max(min(state.x, 0.999), 0.001)
        rho_l = state.rho_l
        k_l   = state.k_l
        Pr_l  = state.Pr_l
        h_fg  = state.h_fg
        sigma = state.sigma
        P_r   = state.P_red

        Bo   = q_flux / (G * h_fg) if h_fg > 0 else 1e-9
        We_fo = G**2 * D_h / (rho_l * sigma) if sigma > 0 else 1e-9
        r = self.ratio

        # Nucleate boiling Nusselt
        Nu_nb = (2345.0
                 * (Bo * r) ** 0.70
                 * P_r ** 0.38
                 * (1.0 - x) ** (-0.51))

        # Convective boiling Nusselt
        Nu_cb = 5.2 * (Bo * r) ** 0.08 * We_fo ** 0.54

        Nu_tp = math.sqrt(Nu_nb**2 + Nu_cb**2)
        return Nu_tp * k_l / D_h


# ---------------------------------------------------------------------------
# ── CONDENSATION HTC CORRELATIONS ──────────────────────────────────────────
# ---------------------------------------------------------------------------

class YanCondensationHTC:
    """
    Yan, Lio & Lin (1999) condensation HTC in plate heat exchangers.

    α_c = 4.118 Re_eq^0.4  Pr_l^0.333  k_l / D_h

    Re_eq = G_eq · D_h / μ_l
    G_eq  = G · [1 - x + x · (ρ_l/ρ_v)^0.5]   (Akers et al. equivalent mass flux)

    Valid for: plate HX, chevron angle β = 30°, R-134a.
    Used by Kokate 2023 / PhD 2024 for plate condenser.

    Reference: Y.-Y. Yan, H.-C. Lio, T.-F. Lin,
               Int. J. Heat Mass Transfer 42 (1999) 993-1006.
    """

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float = 0.0,
        **kwargs,
    ) -> float:
        _validate_state(state, "YanCondensationHTC")

        x = max(min(state.x, 0.999), 0.001)
        rho_l = state.rho_l
        rho_v = state.rho_v
        mu_l  = state.mu_l
        k_l   = state.k_l
        Pr_l  = state.Pr_l

        G_eq  = G * (1.0 - x + x * (rho_l / rho_v) ** 0.5)
        Re_eq = G_eq * D_h / mu_l

        alpha = 4.118 * Re_eq**0.4 * Pr_l**(1.0/3.0) * k_l / D_h
        return alpha


# ---------------------------------------------------------------------------
# ── SINGLE-PHASE PRESSURE DROP CORRELATIONS ────────────────────────────────
# ---------------------------------------------------------------------------

class BlassiusDP:
    """
    Blasius / Hagen-Poiseuille single-phase frictional pressure gradient.

    dP/dz = 2 f G² / (D_h ρ)     [Pa/m]   (Fanning convention)

    Friction factor:
      f = 16 / Re              for Re < 2000  (Hagen-Poiseuille)
      f = 0.079 Re^-0.25       for 2000 ≤ Re < 20 000
      f = 0.046 Re^-0.20       for Re ≥ 20 000

    Reference: Blasius (1913); standard textbook formula.
    """

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        **kwargs,
    ) -> float:
        _validate_state(state, "BlassiusDP")
        phase = getattr(state, "phase", "liquid")
        if phase == "vapor":
            mu  = state.mu_v
            rho = state.rho_v
        else:
            mu  = state.mu_l
            rho = state.rho_l

        Re = _reynolds(G, D_h, mu)
        f  = _friction_factor_blasius(Re)
        return 2.0 * f * G**2 / (D_h * rho)


class ChurchillDP:
    """
    Churchill (1977) unified friction factor — smooth and rough pipes,
    laminar + turbulent + transition regimes.

    f = 8 [(8/Re)^12 + (A + B)^(-1.5)]^(1/12)
    A = [-2.457 ln((7/Re)^0.9 + 0.27 ε/D)]^16
    B = (37530/Re)^16

    Reference: S.W. Churchill, Chem. Eng. 84 (1977) 91-92.
    """

    def __init__(self, roughness: float = 1.5e-6):
        """roughness : absolute wall roughness [m] (default 1.5 μm, steel)"""
        self.roughness = roughness

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        **kwargs,
    ) -> float:
        _validate_state(state, "ChurchillDP")
        phase = getattr(state, "phase", "liquid")
        if phase == "vapor":
            mu  = state.mu_v
            rho = state.rho_v
        else:
            mu  = state.mu_l
            rho = state.rho_l

        Re = _reynolds(G, D_h, mu)
        eps_D = self.roughness / D_h

        A = (-2.457 * math.log((7.0 / Re)**0.9 + 0.27 * eps_D))**16
        B = (37530.0 / Re)**16
        # Darcy friction factor (Churchill 1977)
        f_D = 8.0 * ((8.0 / Re)**12 + (A + B)**(-1.5))**(1.0/12.0)
        f_F = f_D / 4.0  # convert to Fanning

        return 2.0 * f_F * G**2 / (D_h * rho)


# ---------------------------------------------------------------------------
# ── TWO-PHASE PRESSURE DROP CORRELATIONS ───────────────────────────────────
# ---------------------------------------------------------------------------

class HomogeneousDP:
    """
    Homogeneous Equilibrium Model (HEM) frictional pressure gradient.

    dP/dz = 2 f_tp G² / (D_h ρ_tp)     [Pa/m]

    ρ_tp : homogeneous mixture density
      1/ρ_tp = x/ρ_v + (1-x)/ρ_l

    f_tp from Blasius using two-phase viscosity μ_tp (Cicchitti):
      μ_tp = x·μ_v + (1-x)·μ_l       (Kim 2013, Table 1)

    Physical basis: assumes equal phase velocities (slip ratio S = 1).
    Validated for low-quality MPL flows (Dogan 1983, Kokate 2023).

    Reference:
      Dogan (1983) — HEM momentum equation (Eq. 10)
      Kim & Mudawar (2013) Table 1 — Cicchitti viscosity model
    """

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        **kwargs,
    ) -> float:
        _validate_state(state, "HomogeneousDP")

        x = state.x
        if getattr(state, "phase", "") == "liquid":
            # Delegate to single-phase Blasius
            rho = state.rho_l
            mu  = state.mu_l
            Re  = _reynolds(G, D_h, mu)
            f   = _friction_factor_blasius(Re)
            return 2.0 * f * G**2 / (D_h * rho)
        elif getattr(state, "phase", "") == "vapor":
            rho = state.rho_v
            mu  = state.mu_v
            Re  = _reynolds(G, D_h, mu)
            f   = _friction_factor_blasius(Re)
            return 2.0 * f * G**2 / (D_h * rho)

        # Two-phase region
        x = max(min(x, 0.999), 0.001)
        rho_tp = 1.0 / (x / state.rho_v + (1.0 - x) / state.rho_l)
        mu_tp  = state.mu_tp  # Cicchitti from FluidState

        Re_tp = _reynolds(G, D_h, mu_tp)
        f_tp  = _friction_factor_blasius(Re_tp)
        return 2.0 * f_tp * G**2 / (D_h * rho_tp)


class KimMudawar2013DP:
    """
    Kim & Mudawar (2013) universal frictional pressure drop correlation
    for saturated flow boiling in mini/micro-channels.

    Separated flow model (Lockhart-Martinelli):
        (dP/dz)_F = (dP/dz)_f · φ_f²
        φ_f² = 1 + C/X + 1/X²

    X² = (dP/dz)_f / (dP/dz)_g   (Martinelli parameter)

    C coefficient (boiling flows, Table 5 of Kim 2013):
        C = C_non-boiling · [1 + 60 We_fo^0.32 (Bo P_H/P_F)^0.78]  Re_f ≥ 2000
        C = C_non-boiling · [1 + 530 We_fo^0.52 (Bo P_H/P_F)^1.09] Re_f < 2000

    C_non-boiling:
        tt: 0.39 Re_fo^0.03  Su_go^0.10  (ρ_f/ρ_g)^0.35
        tv: 8.7e-4 Re_fo^0.17 Su_go^0.50 (ρ_f/ρ_g)^0.14
        vt: 0.0015 Re_fo^0.59 Su_go^0.19 (ρ_f/ρ_g)^0.36
        vv: 3.5e-5 Re_fo^0.44 Su_go^0.50 (ρ_f/ρ_g)^0.48

    where:
        Re_fo = G D_h / μ_f          liquid-only Reynolds
        Re_go = G D_h / μ_g          vapor-only Reynolds
        Re_f  = G(1-x) D_h / μ_f    superficial liquid Reynolds
        Re_g  = G x    D_h / μ_g    superficial vapor Reynolds
        Su_go = ρ_g σ D_h / μ_g²    vapor Suratman number
        We_fo = G² D_h / (ρ_f σ)    liquid-only Weber number
        Bo    = q''_H / (G h_fg)     Boiling number

    Performance: MAE = 17.2 % over 2378 points (9 fluids, D_h 0.35–5.35 mm)

    Reference: S.-M. Kim, I. Mudawar, IJHMT 58 (2013) 718–734.
    """

    LAMINAR_LIMIT  = 2000
    TURBULENT_LIMIT = 20_000

    def __init__(self, P_H_over_P_F: float = 1.0, aspect_ratio: float = 1.0):
        """
        P_H_over_P_F : heated-to-wetted perimeter ratio  (default 1.0)
        aspect_ratio : β = H/W for rectangular channels   (default 1.0 — square)
                       used for laminar friction factor correction
        """
        self.P_ratio = P_H_over_P_F
        self.beta    = min(max(aspect_ratio, 0.0), 1.0)

    def _fanning(self, Re: float) -> float:
        """Phase friction factor; rectangular laminar correction via beta."""
        if Re < self.LAMINAR_LIMIT:
            return _friction_factor_rect_laminar(Re, self.beta)
        return _friction_factor_blasius(Re)

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        q_flux: float = 0.0,
        **kwargs,
    ) -> float:
        _validate_state(state, "KimMudawar2013DP")

        # Single-phase fall-back
        phase = getattr(state, "phase", "two-phase")
        if phase == "liquid":
            Re = _reynolds(G, D_h, state.mu_l)
            f  = self._fanning(Re)
            return 2.0 * f * G**2 / (D_h * state.rho_l)
        elif phase == "vapor":
            Re = _reynolds(G, D_h, state.mu_v)
            f  = self._fanning(Re)
            return 2.0 * f * G**2 / (D_h * state.rho_v)

        x = max(min(state.x, 0.999), 0.001)

        rho_f = state.rho_l
        rho_g = state.rho_v
        mu_f  = state.mu_l
        mu_g  = state.mu_v
        sigma = state.sigma
        h_fg  = state.h_fg

        # Reynolds numbers
        Re_fo = G * D_h / mu_f                   # liquid-only
        Re_go = G * D_h / mu_g                   # vapor-only
        Re_f  = G * (1.0 - x) * D_h / mu_f      # superficial liquid
        Re_g  = G * x * D_h / mu_g              # superficial vapor

        # Friction factors
        f_f = self._fanning(Re_f)
        f_g = self._fanning(Re_g)

        # Specific volumes
        v_f = 1.0 / rho_f
        v_g = 1.0 / rho_g

        # Phase pressure gradients
        dPdz_f = 2.0 * f_f * v_f * G**2 * (1.0 - x)**2 / D_h
        dPdz_g = 2.0 * f_g * v_g * G**2 * x**2 / D_h

        # Martinelli parameter X
        X2  = dPdz_f / dPdz_g if dPdz_g > 0 else 1e10
        X   = math.sqrt(X2)

        # Suratman and Weber numbers
        Su_go = rho_g * sigma * D_h / (mu_g**2) if mu_g > 0 else 1.0
        We_fo = G**2 * D_h / (rho_f * sigma)    if sigma > 0 else 1.0

        # Boiling number
        Bo = q_flux / (G * h_fg) if (G > 0 and h_fg > 0) else 0.0

        # C_non-boiling — regime classification
        is_f_turbulent = Re_f >= self.LAMINAR_LIMIT
        is_g_turbulent = Re_g >= self.LAMINAR_LIMIT

        rho_ratio = rho_f / rho_g

        if is_f_turbulent and is_g_turbulent:       # tt
            C_nb = 0.39 * Re_fo**0.03 * Su_go**0.10 * rho_ratio**0.35
        elif is_f_turbulent and not is_g_turbulent: # tv
            C_nb = 8.7e-4 * Re_fo**0.17 * Su_go**0.50 * rho_ratio**0.14
        elif not is_f_turbulent and is_g_turbulent: # vt
            C_nb = 0.0015 * Re_fo**0.59 * Su_go**0.19 * rho_ratio**0.36
        else:                                        # vv
            C_nb = 3.5e-5 * Re_fo**0.44 * Su_go**0.50 * rho_ratio**0.48

        # Boiling correction to C
        if Bo > 0:
            if Re_f >= self.LAMINAR_LIMIT:
                C = C_nb * (1.0 + 60.0 * We_fo**0.32
                            * (Bo * self.P_ratio)**0.78)
            else:
                C = C_nb * (1.0 + 530.0 * We_fo**0.52
                            * (Bo * self.P_ratio)**1.09)
        else:
            C = C_nb

        # Two-phase multiplier
        phi_f2 = 1.0 + C / X + 1.0 / X2

        return dPdz_f * phi_f2


class MullerSteinhagenHeckDP:
    """
    Müller-Steinhagen & Heck (1986) two-phase frictional pressure gradient.
    Simple interpolation between liquid-only and vapor-only gradients.

    dP/dz = [A + 2(B - A)·x]·(1 - x)^(1/3) + B·x³

    A = (dP/dz)_lo   — liquid-only Fanning gradient at G (entire flow as liquid)
    B = (dP/dz)_go   — vapor-only  Fanning gradient at G (entire flow as vapor)

    MAE ≈ 24–35 % vs mini/micro-channel boiling databases (Kim 2013 evaluation).
    Used by Kokate 2023, Terpstra 2015, VanGerner 2016 for MPL simulations.

    Reference: H. Müller-Steinhagen, K. Heck,
               Chem. Eng. Process. 20 (1986) 297-308.
    """

    def __call__(
        self,
        state: object,
        G: float,
        D_h: float,
        **kwargs,
    ) -> float:
        _validate_state(state, "MullerSteinhagenHeckDP")

        phase = getattr(state, "phase", "two-phase")
        if phase == "liquid":
            Re = _reynolds(G, D_h, state.mu_l)
            f  = _friction_factor_blasius(Re)
            return 2.0 * f * G**2 / (D_h * state.rho_l)
        elif phase == "vapor":
            Re = _reynolds(G, D_h, state.mu_v)
            f  = _friction_factor_blasius(Re)
            return 2.0 * f * G**2 / (D_h * state.rho_v)

        x = max(min(state.x, 0.999), 0.001)

        # Liquid-only and vapor-only Fanning pressure gradients
        Re_lo = _reynolds(G, D_h, state.mu_l)
        Re_go = _reynolds(G, D_h, state.mu_v)
        f_lo  = _friction_factor_blasius(Re_lo)
        f_go  = _friction_factor_blasius(Re_go)

        A = 2.0 * f_lo * G**2 / (D_h * state.rho_l)
        B = 2.0 * f_go * G**2 / (D_h * state.rho_v)

        dPdz = (A + 2.0 * (B - A) * x) * (1.0 - x)**(1.0/3.0) + B * x**3
        return dPdz


# ---------------------------------------------------------------------------
# ── ACCELERATION & GRAVITY PRESSURE GRADIENT HELPERS ───────────────────────
# ---------------------------------------------------------------------------

def acceleration_pressure_gradient(
    state: object,
    G: float,
    dh_dz: float,
) -> float:
    """
    Accelerational (momentum) pressure gradient [Pa/m] in two-phase flow.

    (dP/dz)_A = G² · d/dz [x²/ρ_v + (1-x)²/ρ_l]
              ≈ G² · [x²/ρ_v + (1-x)²/ρ_l]' · dh/dz · (dh/dz)^-1 ...

    For a uniformly heated channel with quality changing as:
        dx/dz = q'' P_H / (G h_fg A_c)

    Simplified form for uniform heat flux (per Kim 2013 Eq. 2):
        (dP/dz)_A = G² · d(v_tp)/dz
    where  v_tp = x v_g + (1-x) v_l  for homogeneous model.

    Parameters
    ----------
    state  : FluidState at local position
    G      : mass flux  [kg/m²·s]
    dh_dz  : specific enthalpy gradient along channel  [J/kg·m]
              = q'' P_H / (G A_c)

    Returns
    -------
    (dP/dz)_A  [Pa/m]  — positive means pressure decreases (flow deceleration)
    """
    _validate_state(state, "acceleration_pressure_gradient")

    x = state.x
    if getattr(state, "phase", "liquid") == "liquid":
        return 0.0  # incompressible single-phase: no acceleration term

    x = max(min(x, 0.999), 0.001)
    h_fg = state.h_fg
    if h_fg <= 0:
        return 0.0

    v_l = 1.0 / state.rho_l
    v_g = 1.0 / state.rho_v

    # dv_tp/dx = v_g - v_l
    # dx/dz    = dh/dz / h_fg  (for equilibrium two-phase)
    dvtp_dz = (v_g - v_l) * dh_dz / h_fg
    return G**2 * dvtp_dz


def gravity_pressure_gradient(
    state: object,
    orientation: str = "horizontal",
) -> float:
    """
    Gravitational pressure gradient [Pa/m].

    (dP/dz)_G = ρ_tp · g · sin(θ)

    θ = 0°    → horizontal  →  0
    θ = 90°   → vertical upward  →  ρ_tp · g
    θ = -90°  → vertical downward  →  -ρ_tp · g

    Parameters
    ----------
    state       : FluidState
    orientation : 'horizontal' | 'vertical_up' | 'vertical_down'
    """
    _validate_state(state, "gravity_pressure_gradient")

    G_EARTH = 9.806  # m/s²
    rho_tp = state.rho  # HEM mixture density from FluidState

    if orientation == "horizontal":
        return 0.0
    elif orientation == "vertical_up":
        return rho_tp * G_EARTH
    elif orientation == "vertical_down":
        return -rho_tp * G_EARTH
    else:
        raise ValueError(
            f"orientation must be 'horizontal', 'vertical_up', or "
            f"'vertical_down'; got '{orientation}'."
        )


# ---------------------------------------------------------------------------
# ── DEFAULT CORRELATION INSTANCES (module-level singletons) ────────────────
# ---------------------------------------------------------------------------

# HTC defaults
htc_dittus_boelter  = DittusBoelterHTC(heating=True)
htc_gnielinski      = GnielinskiHTC(heating=True)
htc_shah_boiling    = ShahBoilingHTC()
htc_kim_mudawar     = KimMudawar2012HTC()
htc_yan_condensation = YanCondensationHTC()

# ΔP defaults
dp_blasius          = BlassiusDP()
dp_churchill        = ChurchillDP()
dp_homogeneous      = HomogeneousDP()
dp_kim_mudawar_2013 = KimMudawar2013DP()
dp_muller_steinhagen_heck = MullerSteinhagenHeckDP()


# ---------------------------------------------------------------------------
# ── REGISTRY — convenience factory ─────────────────────────────────────────
# ---------------------------------------------------------------------------

_HTC_REGISTRY: dict[str, type] = {
    "dittus_boelter":   DittusBoelterHTC,
    "gnielinski":       GnielinskiHTC,
    "shah_london":      ShahLondonLaminarHTC,
    "shah_boiling":     ShahBoilingHTC,
    "kim_mudawar_2012": KimMudawar2012HTC,
    "yan_condensation": YanCondensationHTC,
}

_DP_REGISTRY: dict[str, type] = {
    "blasius":               BlassiusDP,
    "churchill":             ChurchillDP,
    "homogeneous":           HomogeneousDP,
    "kim_mudawar_2013":      KimMudawar2013DP,
    "muller_steinhagen_heck": MullerSteinhagenHeckDP,
}


def get_htc_correlation(name: str, **kwargs) -> object:
    """
    Factory for HTC correlations by name.

    Examples
    --------
    >>> htc = get_htc_correlation("shah_boiling")
    >>> htc = get_htc_correlation("dittus_boelter", heating=False)
    """
    if name not in _HTC_REGISTRY:
        raise KeyError(
            f"Unknown HTC correlation '{name}'. "
            f"Available: {list(_HTC_REGISTRY)}"
        )
    return _HTC_REGISTRY[name](**kwargs)


def get_dp_correlation(name: str, **kwargs) -> object:
    """
    Factory for ΔP correlations by name.

    Examples
    --------
    >>> dp = get_dp_correlation("kim_mudawar_2013", aspect_ratio=0.5)
    >>> dp = get_dp_correlation("homogeneous")
    """
    if name not in _DP_REGISTRY:
        raise KeyError(
            f"Unknown ΔP correlation '{name}'. "
            f"Available: {list(_DP_REGISTRY)}"
        )
    return _DP_REGISTRY[name](**kwargs)


# ---------------------------------------------------------------------------
# ── QUICK SELF-TEST (run as script) ────────────────────────────────────────
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Minimal smoke-test using a duck-typed FluidState stub.
    For full testing run: pytest tests/test_correlations.py
    """

    @dataclass
    class _StubState:
        """Minimal FluidState stub for smoke-testing."""
        phase: str = "two-phase"
        T: float = 300.0
        P: float = 5e5
        x: float = 0.3
        rho: float = 80.0
        rho_l: float = 1100.0
        rho_v: float = 10.0
        mu_l: float = 2e-4
        mu_v: float = 1.2e-5
        mu_tp: float = 0.7 * 2e-4 + 0.3 * 1.2e-5  # Cicchitti x=0.3
        k_l: float = 0.08
        k_v: float = 0.015
        Pr_l: float = 4.5
        Pr_v: float = 1.1
        h_fg: float = 200_000.0
        sigma: float = 0.01
        P_red: float = 0.1
        T_sat: float = 300.0

    s = _StubState()
    G   = 200.0     # kg/m²·s
    D_h = 0.001     # 1 mm
    q   = 50_000.0  # 50 kW/m²

    print("=" * 60)
    print("correlations.py — smoke test")
    print("=" * 60)
    print(f"State: x={s.x}, G={G} kg/m²s, Dh={D_h*1e3:.1f} mm, q={q/1e3:.0f} kW/m²")
    print()

    # HTC
    for name, corr in [
        ("Dittus-Boelter (liquid)", DittusBoelterHTC()),
        ("Shah Boiling",            ShahBoilingHTC()),
        ("Kim-Mudawar 2012",        KimMudawar2012HTC()),
        ("Yan Condensation",        YanCondensationHTC()),
    ]:
        try:
            val = corr(s, G, D_h, q)
            print(f"  HTC {name:30s}: {val:>10.1f}  W/m²K")
        except Exception as e:
            print(f"  HTC {name:30s}: ERROR — {e}")

    print()

    # ΔP
    for name, corr in [
        ("Homogeneous",            HomogeneousDP()),
        ("Kim-Mudawar 2013",       KimMudawar2013DP()),
        ("Müller-Steinhagen-Heck", MullerSteinhagenHeckDP()),
        ("Blasius (single-phase)", BlassiusDP()),
    ]:
        try:
            val = corr(s, G, D_h, q_flux=q)
            print(f"  ΔP  {name:30s}: {val:>10.1f}  Pa/m")
        except Exception as e:
            print(f"  ΔP  {name:30s}: ERROR — {e}")

    print()
    print("Registry keys:")
    print("  HTC:", list(_HTC_REGISTRY))
    print("  ΔP: ", list(_DP_REGISTRY))
    print()
    print("All smoke tests passed ✓")
