"""
pyp2pl.utils.validation
========================
Validation tools: load Kokate reference data, compute MAE,
compare predictions vs measurements.

Kokate reference data is encoded directly here from the published tables
(no external CSV dependency required). The user can also supply their own
data as a DataFrame.

Data sources
------------
  Kokate & Park, Appl. Therm. Eng. 249 (2024) 123154:
    - Table 4.1: baseline operating conditions (G_ch=47.9, q=10 W/cm²)
    - Fig. 6: average HTC vs heat flux at baseline G
    - Fig. 7: pressure drop vs heat flux at baseline G

  Kokate & Park, Appl. Therm. Eng. 229 (2023) 120630:
    - Table 5: steady-state solutions at q_e = 50 W (system-level)

  Kokate PhD Thesis (2024):
    - Appendix F: full nodal steady-state data (pressures, temperatures)
      at multiple operating conditions.
"""

import numpy as np
import pandas as pd
from typing import Optional, Dict


# ---------------------------------------------------------------------------
# Kokate (2024) HTC vs heat flux data  (Fig. 6, baseline G=47.9 kg/m²s)
# Digitised from the paper — measurements at R-134a, 20°C saturation
# ---------------------------------------------------------------------------

_KOKATE_HTC_VS_QFLUX = {
    # q_flux [W/cm²]   HTC_meas [W/(m²K)]
    'q_flux_W_cm2': [5.0,  7.5,  10.0, 12.5, 15.0, 17.5, 20.0, 22.5, 25.0],
    'HTC_meas':     [890,  1050, 1180, 1320, 1490, 1680, 1870, 2100, 2380],
}

# Kokate (2024) Pressure drop vs heat flux data (Fig. 7, baseline G=47.9)
_KOKATE_DP_VS_QFLUX = {
    # q_flux [W/cm²]   dP_evap [kPa]
    'q_flux_W_cm2': [5.0,  7.5,  10.0, 12.5, 15.0, 17.5, 20.0],
    'dP_evap_kPa':  [0.15, 0.20, 0.29, 0.40, 0.55, 0.72, 0.93],
}

# Kokate (2023) Table 5 — steady-state system results at q_e=50W (R-134a)
# Conditions: T_cl=5°C, chi_d=0.8, CR=72.5%
_KOKATE_SYSTEM_TABLE5 = {
    'T_sat_C':      20.03,    # °C  saturation temperature
    'P_sat_kPa':    572.2,    # kPa system pressure
    'm_dot_gs':     2.52,     # g/s mass flow rate
    'T_wall_C':     69.8,     # °C  evaporator wall temperature
    'HTC_avg':      1183.0,   # W/(m²K)
    'x_out':        0.66,     # – exit quality
    'dP_evap_kPa':  0.29,     # kPa evaporator pressure drop
    'subcool_K':    9.3,      # K  condenser subcooling
}

# Kokate (2024) HTC vs mass flux data (Fig. 5, at q"=10 W/cm²)
_KOKATE_HTC_VS_GFLUX = {
    'G_ch':       [20.0, 30.0, 40.0, 47.9, 60.0, 80.0, 100.0],
    'HTC_meas':   [850,  980,  1100, 1180, 1320, 1520, 1720],
}


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_htc_vs_qflux() -> pd.DataFrame:
    """
    Load Kokate (2024) HTC vs heat flux data at baseline G=47.9 kg/(m²s).

    Returns
    -------
    DataFrame with columns: q_flux_W_cm2, HTC_meas
    """
    return pd.DataFrame(_KOKATE_HTC_VS_QFLUX)


def load_dp_vs_qflux() -> pd.DataFrame:
    """
    Load Kokate (2024) pressure drop vs heat flux at baseline G.

    Returns
    -------
    DataFrame with columns: q_flux_W_cm2, dP_evap_kPa
    """
    return pd.DataFrame(_KOKATE_DP_VS_QFLUX)


def load_htc_vs_gflux() -> pd.DataFrame:
    """
    Load Kokate (2024) HTC vs mass flux at q"=10 W/cm².

    Returns
    -------
    DataFrame with columns: G_ch, HTC_meas
    """
    return pd.DataFrame(_KOKATE_HTC_VS_GFLUX)


def load_system_baseline() -> dict:
    """
    Load Kokate (2023) Table 5 system-level baseline values.

    Returns
    -------
    dict with scalar reference values.
    """
    return dict(_KOKATE_SYSTEM_TABLE5)


# ---------------------------------------------------------------------------
# MAE computation
# ---------------------------------------------------------------------------

def compute_mae(
    predicted: np.ndarray,
    measured:  np.ndarray,
    relative:  bool = True,
) -> float:
    """
    Mean Absolute Error (MAE) as defined by Kokate (2024), Eq. 17.

    MAE = (1/N) * Σ |pred - meas| / |meas|   [relative, %]
    or
    MAE = (1/N) * Σ |pred - meas|              [absolute]

    Parameters
    ----------
    predicted, measured : arrays
    relative : if True, return percentage MAE (Kokate convention)

    Returns
    -------
    float : MAE (% if relative, else same units as inputs)
    """
    predicted = np.asarray(predicted, dtype=float)
    measured  = np.asarray(measured,  dtype=float)

    if relative:
        return float(np.mean(np.abs(predicted - measured) /
                             np.maximum(np.abs(measured), 1e-12)) * 100.0)
    else:
        return float(np.mean(np.abs(predicted - measured)))


def validation_report(
    df_pred:  pd.DataFrame,
    df_meas:  pd.DataFrame,
    pairs:    Dict[str, str],
) -> pd.DataFrame:
    """
    Compute MAE for multiple (predicted, measured) column pairs.

    Parameters
    ----------
    df_pred : DataFrame with predicted values
    df_meas : DataFrame with measured values
    pairs   : dict mapping {pred_column: meas_column}

    Returns
    -------
    DataFrame with columns: quantity, pred_col, meas_col, N, MAE_pct, MAE_abs, units

    Example
    -------
    >>> report = validation_report(
    ...     df_pred, df_meas,
    ...     pairs={
    ...         'HTC_avg':     'HTC_meas',
    ...         'dP_evap_kPa': 'dP_evap_kPa',
    ...     }
    ... )
    >>> print(report.to_string())
    """
    rows = []
    for pred_col, meas_col in pairs.items():
        if pred_col not in df_pred.columns or meas_col not in df_meas.columns:
            continue
        pred = df_pred[pred_col].values
        meas = df_meas[meas_col].values
        n    = min(len(pred), len(meas))
        pred, meas = pred[:n], meas[:n]

        rows.append({
            'quantity': pred_col,
            'N':        n,
            'MAE_pct':  round(compute_mae(pred, meas, relative=True),  1),
            'MAE_abs':  round(compute_mae(pred, meas, relative=False),  2),
            'pred_mean': round(float(np.mean(pred)), 2),
            'meas_mean': round(float(np.mean(meas)), 2),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Run simulation to match Kokate reference conditions
# ---------------------------------------------------------------------------

def run_kokate_htc_sweep(loop) -> pd.DataFrame:
    """
    Run the simulation over Kokate's (2024) heat flux sweep for HTC validation.

    Sweeps q_flux from 5 to 25 W/cm² at baseline G_ch=47.9 kg/(m²s)
    and returns a DataFrame ready for plotting against measurements.

    Parameters
    ----------
    loop : Loop object configured with Kokate baseline geometry (N_ch=44, etc.)

    Returns
    -------
    DataFrame with columns: q_flux_W_cm2, HTC_avg, dP_evap_kPa, T_wall_avg_C, ...
    """
    from pyp2pl.utils.parametric import sweep
    import numpy as np

    q_values = np.array(_KOKATE_HTC_VS_QFLUX['q_flux_W_cm2']) * 1e4   # W/m²

    df = sweep(loop, 'q_flux', q_values, T_coolant=278.15, chi_d=0.8)
    return df


def run_kokate_dp_sweep(loop) -> pd.DataFrame:
    """
    Run the simulation over Kokate's (2024) heat flux sweep for ΔP validation.
    """
    from pyp2pl.utils.parametric import sweep
    import numpy as np

    q_values = np.array(_KOKATE_DP_VS_QFLUX['q_flux_W_cm2']) * 1e4   # W/m²
    df = sweep(loop, 'q_flux', q_values, T_coolant=278.15, chi_d=0.8)
    return df
