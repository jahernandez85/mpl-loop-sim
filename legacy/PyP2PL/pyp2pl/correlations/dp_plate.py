"""
pyp2pl.correlations.dp_plate
==============================
Pressure drop and heat transfer correlations for flat-plate heat exchangers.

Implemented:
  - Yan et al. (1999)   — two-phase condensation in plate HX (condenser)
  - Kumar (1984)        — single-phase in plate HX (subcooling section)

References:
  Kokate PhD Thesis (2024), Appendix B.
  Kokate & Park, Applied Thermal Engineering 229 (2023), Appendix.
"""

import math
from dataclasses import dataclass


@dataclass
class PlateHTCResult:
    """Heat transfer coefficient result for a plate HX."""
    alpha: float   # W/(m²·K)
    Re:    float   # –  Reynolds number
    Nu:    float   # –  Nusselt number


@dataclass
class PlateDPResult:
    """Pressure drop result for a plate HX."""
    dP:    float   # Pa
    f:     float   # –  friction factor
    Re:    float   # –  Reynolds number


# ---------------------------------------------------------------------------
# Kumar (1984) — single-phase plate HX
# ---------------------------------------------------------------------------
# Correlation coefficients from Kumar (1984) for corrugated plates.
# Kokate uses these for the subcooling section of the condenser.
# Plate angle beta typically 30–60°. Kokate uses 60° (chevron) plates.

_KUMAR_COEFF = {
    # beta (deg): { Re_range: (c_h, n, c_f, m) }
    60: [
        (400,    0.718, 0.349, 2.990, 0.183),   # Re <= 400
        (1e9,    0.348, 0.663, 0.652, 0.333),   # Re > 400
    ]
}


def kumar_plate(m_dot_ch: float, Dh: float, A_ch: float,
                rho: float, mu: float, k: float, Pr: float,
                L_plate: float, plate_angle_deg: float = 60.0) -> tuple:
    """
    Kumar (1984) single-phase plate HX heat transfer and friction.

    Parameters
    ----------
    m_dot_ch     : kg/s   mass flow rate per channel
    Dh           : m      hydraulic diameter of plate channel (≈ 2*gap)
    A_ch         : m²     channel cross-section area
    rho, mu, k   : fluid properties
    Pr           : Prandtl number
    L_plate      : m      active plate length
    plate_angle_deg : deg  chevron angle (default 60°)

    Returns
    -------
    (PlateHTCResult, PlateDPResult)
    """
    u  = m_dot_ch / (rho * A_ch)
    Re = rho * u * Dh / mu

    # Use 60° coefficients (closest to Kokate's condenser)
    coeffs = _KUMAR_COEFF.get(60, _KUMAR_COEFF[60])
    c_h, n, c_f, m = coeffs[0][1:] if Re <= coeffs[0][0] else coeffs[1][1:]

    Nu = c_h * Re**n * Pr**(1.0 / 3.0)
    alpha = Nu * k / Dh

    f  = c_f / Re**m
    dP = f * (L_plate / Dh) * rho * u**2 / 2.0

    return (
        PlateHTCResult(alpha=alpha, Re=Re, Nu=Nu),
        PlateDPResult(dP=dP, f=f, Re=Re),
    )


# ---------------------------------------------------------------------------
# Yan et al. (1999) — two-phase condensation in plate HX
# ---------------------------------------------------------------------------

def yan_condensation(G: float, x_in: float, x_out: float,
                     Dh: float, L_plate: float,
                     rho_l: float, rho_v: float,
                     mu_l: float, mu_v: float,
                     k_l: float, cp_l: float,
                     h_fg: float, P: float,
                     n_cv: int = 20) -> tuple:
    """
    Yan et al. (1999) condensation HTC and pressure drop in plate HX.

    Nu_cond = 4.118 * Re_eq^0.4 * Pr_l^(1/3)
    f_cond  = 94.75 * Re_eq^(-0.14)

    Where Re_eq is the equivalent Reynolds number:
    Re_eq = G * Dh / mu_l * [x + (1-x) * (rho_v / rho_l)^0.5 * (mu_l/mu_v)^0.5]

    Integrated over n_cv control volumes with linearly varying quality.

    Parameters
    ----------
    (geometry and fluid properties as above)

    Returns
    -------
    (PlateHTCResult, PlateDPResult)  — averaged over the condensation length
    """
    x_in  = max(0.0, min(1.0, x_in))
    x_out = max(0.0, min(1.0, x_out))

    Pr_l = cp_l * mu_l / k_l

    alpha_sum = 0.0
    dP_sum    = 0.0
    Re_sum    = 0.0
    dz = L_plate / n_cv

    for i in range(n_cv):
        x = x_in + (x_out - x_in) * (i + 0.5) / n_cv

        # Equivalent Reynolds number (Yan)
        corr = x + (1.0 - x) * (rho_v / rho_l)**0.5 * (mu_l / mu_v)**0.5
        Re_eq = G * Dh / mu_l * corr

        Re_eq = max(Re_eq, 1.0)

        # HTC
        Nu    = 4.118 * Re_eq**0.4 * Pr_l**(1.0 / 3.0)
        alpha = Nu * k_l / Dh
        alpha_sum += alpha

        # Friction
        f  = 94.75 / Re_eq**0.14
        dP_cv = f * (dz / Dh) * rho_l * (G / rho_l)**2 / 2.0  # approximate
        dP_sum += dP_cv

        Re_sum += Re_eq

    alpha_avg = alpha_sum / n_cv
    dP_total  = dP_sum
    Re_avg    = Re_sum / n_cv
    Nu_avg    = alpha_avg * Dh / k_l

    return (
        PlateHTCResult(alpha=alpha_avg, Re=Re_avg, Nu=Nu_avg),
        PlateDPResult(dP=dP_total, f=94.75 / Re_avg**0.14, Re=Re_avg),
    )
