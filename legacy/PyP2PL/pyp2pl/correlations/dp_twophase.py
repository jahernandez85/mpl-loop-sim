"""
pyp2pl.correlations.dp_twophase
================================
Two-phase pressure drop correlations.

Implemented:
  - Müller-Steinhagen & Heck (MSH, 1986) — used by Kokate for the evaporator
    and condenser two-phase sections.
    Reference: Ould Didi et al. (2002) as cited by Kokate PhD (2024), Appendix B.

The pressure drop is split into:
  - Friction (frictional)     : MSH correlation
  - Acceleration (momentum)   : two-phase momentum change
  - Hydrostatic               : zero for horizontal channels (Kokate assumption)

Units: SI throughout.
"""

import math
from dataclasses import dataclass


@dataclass
class DPResult:
    """Pressure drop components [Pa] for a single control volume."""
    dP_total:  float   # Pa  (positive = pressure drop in flow direction)
    dP_fric:   float   # Pa  friction
    dP_accel:  float   # Pa  acceleration
    dP_static: float   # Pa  hydrostatic (zero for horizontal)
    x_in:      float   # –   inlet vapor quality of this CV
    x_out:     float   # –   outlet vapor quality of this CV


# ---------------------------------------------------------------------------
# Single-phase friction factors
# ---------------------------------------------------------------------------

def _f_single_phase(Re: float, roughness_ratio: float = 0.0) -> float:
    """
    Churchill (1977) friction factor — valid for all Re and roughness.
    Smooth tube default (roughness_ratio = 0).
    """
    if Re < 1.0:
        return 64.0  # stokes limit

    # Churchill's A and B terms
    A = (2.457 * math.log(1.0 / ((7.0 / Re)**0.9 + 0.27 * roughness_ratio)))**16
    B = (37530.0 / Re)**16

    f = 8.0 * ((8.0 / Re)**12 + (A + B)**(-1.5))**(1.0 / 12.0)
    return f


# ---------------------------------------------------------------------------
# Müller-Steinhagen & Heck (MSH) frictional pressure gradient
# ---------------------------------------------------------------------------

def msh_frictional_gradient(G: float, x: float, dh: float,
                             rho_l: float, rho_v: float,
                             mu_l: float, mu_v: float) -> float:
    """
    Müller-Steinhagen & Heck (1986) two-phase frictional pressure gradient [Pa/m].

    As described by Ould Didi et al. (2002) and used in Kokate PhD (2024), Appendix B.

    The correlation interpolates between the all-liquid (x=0) and all-vapor (x=1)
    frictional gradients:

        dP/dz|_fric = G(x) * (1-x)^(1/3) + B * x^3

    where G(x) = A + 2*(B - A)*x,
          A = (dP/dz)_lo    (all-liquid frictional gradient)
          B = (dP/dz)_vo    (all-vapor frictional gradient)

    Parameters
    ----------
    G    : kg/(m²·s)   mass flux
    x    : –           vapor quality [0, 1]
    dh   : m           hydraulic diameter
    rho_l, rho_v : kg/m³  densities
    mu_l, mu_v   : Pa·s   dynamic viscosities

    Returns
    -------
    dP_dz : Pa/m  (positive = pressure decreasing in flow direction)
    """
    x = max(0.0, min(1.0, x))

    # All-liquid frictional gradient
    Re_lo = G * dh / mu_l
    f_lo  = _f_single_phase(Re_lo)
    dPdz_lo = f_lo * G**2 / (2.0 * rho_l * dh)

    # All-vapor frictional gradient
    Re_vo = G * dh / mu_v
    f_vo  = _f_single_phase(Re_vo)
    dPdz_vo = f_vo * G**2 / (2.0 * rho_v * dh)

    # MSH interpolation
    A = dPdz_lo
    B = dPdz_vo
    Gx = A + 2.0 * (B - A) * x
    dPdz = Gx * (1.0 - x)**(1.0 / 3.0) + B * x**3

    return dPdz


# ---------------------------------------------------------------------------
# Acceleration (momentum) pressure gradient — homogeneous model
# ---------------------------------------------------------------------------

def _void_fraction_homogeneous(x: float, rho_l: float, rho_v: float) -> float:
    """Homogeneous void fraction alpha_h = 1 / (1 + (1-x)/x * rho_v/rho_l)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    return 1.0 / (1.0 + (1.0 - x) / x * rho_v / rho_l)


def acceleration_gradient(G: float, x_in: float, x_out: float,
                           rho_l: float, rho_v: float, dz: float) -> float:
    """
    Acceleration pressure gradient from momentum change [Pa/m].

    dP/dz|_accel = G² * d/dz [ x²/(rho_v*alpha) + (1-x)²/(rho_l*(1-alpha)) ]

    Using homogeneous model (Kokate PhD, Appendix B):
        = G² * d/dz (1 / rho_homogeneous)
        = G² * (1/rho_out - 1/rho_in) / dz
    """
    if abs(x_out - x_in) < 1e-10 or dz <= 0.0:
        return 0.0

    rho_in  = 1.0 / (x_in  / rho_v + (1.0 - x_in)  / rho_l)
    rho_out = 1.0 / (x_out / rho_v + (1.0 - x_out) / rho_l)

    dPdz_accel = G**2 * (1.0 / rho_out - 1.0 / rho_in) / dz
    return dPdz_accel


# ---------------------------------------------------------------------------
# Full pressure drop over a discretised evaporator/condenser channel
# ---------------------------------------------------------------------------

def two_phase_pressure_drop(
    G: float,
    x_in: float,
    x_out: float,
    L: float,
    dh: float,
    rho_l: float,
    rho_v: float,
    mu_l: float,
    mu_v: float,
    n_cv: int = 20,
    horizontal: bool = True,
) -> DPResult:
    """
    Compute total two-phase pressure drop [Pa] over a channel of length L [m].

    The channel is divided into n_cv control volumes. Quality varies linearly
    from x_in to x_out (valid for uniform heat flux, as in Kokate's model).

    Parameters
    ----------
    G        : kg/(m²·s)   mass flux
    x_in     : –           inlet vapor quality
    x_out    : –           outlet vapor quality
    L        : m           channel length
    dh       : m           hydraulic diameter
    n_cv     : int         number of control volumes for integration
    horizontal: bool       if True, hydrostatic term = 0

    Returns
    -------
    DPResult
    """
    x_in  = max(0.0, min(1.0, x_in))
    x_out = max(0.0, min(1.0, x_out))

    dz = L / n_cv
    dP_fric_total  = 0.0
    dP_accel_total = 0.0

    x_arr = [x_in + (x_out - x_in) * i / n_cv for i in range(n_cv + 1)]

    for i in range(n_cv):
        x_mid = 0.5 * (x_arr[i] + x_arr[i + 1])

        # Frictional gradient at mid-point quality
        dPdz_fric = msh_frictional_gradient(
            G=G, x=x_mid, dh=dh,
            rho_l=rho_l, rho_v=rho_v,
            mu_l=mu_l, mu_v=mu_v,
        )
        dP_fric_total += dPdz_fric * dz

        # Acceleration gradient for this CV
        dPdz_accel = acceleration_gradient(
            G=G,
            x_in=x_arr[i], x_out=x_arr[i + 1],
            rho_l=rho_l, rho_v=rho_v,
            dz=dz,
        )
        dP_accel_total += dPdz_accel * dz

    dP_static = 0.0  # horizontal assumption

    return DPResult(
        dP_total  = dP_fric_total + dP_accel_total + dP_static,
        dP_fric   = dP_fric_total,
        dP_accel  = dP_accel_total,
        dP_static = dP_static,
        x_in      = x_in,
        x_out     = x_out,
    )
