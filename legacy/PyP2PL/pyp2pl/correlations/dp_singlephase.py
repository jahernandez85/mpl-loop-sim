"""
pyp2pl.correlations.dp_singlephase
====================================
Single-phase pressure drop — Darcy-Weisbach equation with Churchill (1977)
friction factor (valid for laminar, transition, and turbulent, any roughness).

Used for:
  - Connecting pipes (liquid lines)
  - Subcooling section of condenser
  - Preheater (single-phase)

Reference:
  Churchill, S.W. (1977). Friction-factor equation spans all fluid-flow regimes.
  Chemical Engineering, 84(24), 91–92.
"""

import math
from dataclasses import dataclass


@dataclass
class SinglePhaseDPResult:
    """Pressure drop for a single-phase pipe segment."""
    dP:    float   # Pa   total pressure drop
    f:     float   # –    Darcy-Weisbach friction factor
    Re:    float   # –    Reynolds number
    u:     float   # m/s  mean flow velocity


def churchill_friction_factor(Re: float, roughness_ratio: float = 0.0) -> float:
    """
    Churchill (1977) explicit friction factor for all flow regimes.

    Parameters
    ----------
    Re              : Reynolds number (–)
    roughness_ratio : relative roughness e/D (–), default 0 (smooth)

    Returns
    -------
    f : Darcy-Weisbach friction factor (–)
    """
    if Re < 1e-6:
        return 0.0

    # Laminar limit: f = 64/Re
    if Re < 2100.0:
        return 64.0 / Re

    A = (2.457 * math.log(1.0 / ((7.0 / Re)**0.9 + 0.27 * roughness_ratio)))**16
    B = (37530.0 / Re)**16

    f = 8.0 * ((8.0 / Re)**12.0 + (A + B)**(-1.5))**(1.0 / 12.0)
    return f


def single_phase_dp(
    m_dot: float,
    L: float,
    D: float,
    rho: float,
    mu: float,
    roughness: float = 0.0,
    A_cross: float = None,
) -> SinglePhaseDPResult:
    """
    Darcy-Weisbach pressure drop for a single-phase circular pipe or duct.

    dP = f * (L/D) * rho * u² / 2

    Parameters
    ----------
    m_dot    : kg/s   mass flow rate
    L        : m      pipe length
    D        : m      hydraulic diameter
    rho      : kg/m³  fluid density
    mu       : Pa·s   dynamic viscosity
    roughness: m      absolute roughness (default 0 = smooth)
    A_cross  : m²     cross-sectional area (if None, computed from D for circular)

    Returns
    -------
    SinglePhaseDPResult
    """
    if A_cross is None:
        A_cross = math.pi * D**2 / 4.0

    u  = m_dot / (rho * A_cross)
    Re = rho * u * D / mu
    roughness_ratio = roughness / D if D > 0 else 0.0

    f  = churchill_friction_factor(Re, roughness_ratio)
    dP = f * (L / D) * rho * u**2 / 2.0

    return SinglePhaseDPResult(dP=dP, f=f, Re=Re, u=u)
