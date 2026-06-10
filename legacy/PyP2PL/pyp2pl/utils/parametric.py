"""
pyp2pl.utils.parametric
========================
High-level parametric study utilities built on top of Loop.sweep().

Functions
---------
sweep(loop, param, values, T_coolant, chi_d, ...)
    Run a 1-D parametric sweep and return a tidy DataFrame.

sweep_2d(loop, param1, values1, param2, values2, ...)
    Run a 2-D parameter grid and return a DataFrame.

compare_fluids(fluids, base_loop_factory, param, values, ...)
    Compare multiple refrigerants side-by-side over a parameter range.

ledinegg_map(loop, q_flux_range, m_dot_range, ...)
    Compute the Ledinegg stability boundary:
    onset of flow instability = where d(ΔP_evap)/d(m_dot) < 0.

All functions return pandas DataFrames for easy plotting and export.

Reference (Ledinegg)
--------------------
  Ledinegg (1938): instability occurs when the negative slope of the
  internal pressure-drop curve exceeds the pump curve slope.
  d(ΔP_loop)/d(ṁ) < 0  at the operating point → flow excursion.
  Kokate PhD Thesis (2024), Ch. 3 — Ledinegg stability analysis.
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Callable


# ---------------------------------------------------------------------------
# 1-D parametric sweep
# ---------------------------------------------------------------------------

def sweep(
    loop,
    param:       str,
    values:      list,
    T_coolant:   float,
    chi_d:       float = 0.8,
    extra_metrics: Optional[List[str]] = None,
    verbose:     bool  = False,
) -> pd.DataFrame:
    """
    Run a 1-D parametric sweep and return a tidy DataFrame.

    Parameters
    ----------
    loop       : Loop object (already assembled with components)
    param      : parameter to vary — 'q_flux', 'T_coolant', 'chi_d',
                 'charge_ratio'
    values     : list or array of values to sweep
    T_coolant  : K   baseline coolant temperature
    chi_d      : float  baseline flow ratio
    extra_metrics : list of additional metric keys to extract from component
                    results (e.g. ['HTC_avg', 'x_out'])
    verbose    : print progress

    Returns
    -------
    pandas DataFrame with one row per sweep point.

    Example
    -------
    >>> import numpy as np
    >>> from pyp2pl.utils.parametric import sweep
    >>> df = sweep(loop, 'q_flux', np.linspace(5e4, 20e4, 10), T_coolant=278.15)
    >>> df.plot(x='q_flux_W_m2', y='T_wall_max_C')
    """
    rows = []
    n = len(values)

    for i, val in enumerate(values):
        if verbose:
            print(f"  [{i+1:3d}/{n}]  {param} = {val:.4g}")

        # Set parameter
        T_cl   = T_coolant
        chi    = chi_d
        _set_param(loop, param, val)
        if param == 'T_coolant':
            T_cl = val
        elif param == 'chi_d':
            chi = val

        state = loop.solve(T_coolant=T_cl, chi_d=chi)

        row = _state_to_row(state, param, val)

        # Extra component-level metrics
        if extra_metrics:
            for comp, res in zip(state.components, state.results):
                prefix = comp.__class__.__name__[:4].lower() + '_'
                for k in extra_metrics:
                    if k in res.metrics:
                        row[prefix + k] = res.metrics[k]

        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 2-D parametric sweep
# ---------------------------------------------------------------------------

def sweep_2d(
    loop,
    param1:    str,
    values1:   list,
    param2:    str,
    values2:   list,
    T_coolant: float,
    chi_d:     float = 0.8,
    verbose:   bool  = False,
) -> pd.DataFrame:
    """
    Run a 2-D parameter grid sweep.

    Returns a DataFrame with len(values1) × len(values2) rows.
    Useful for generating response surfaces and contour plots.

    Parameters
    ----------
    param1, values1 : first parameter and its values
    param2, values2 : second parameter and its values

    Example
    -------
    >>> df = sweep_2d(loop,
    ...     'q_flux',  np.linspace(5e4, 20e4, 8),
    ...     'T_coolant', np.linspace(273.15, 293.15, 5),
    ...     T_coolant=278.15)
    >>> # Pivot for contour plot
    >>> pivot = df.pivot(index='q_flux_W_m2', columns='T_coolant_C', values='T_wall_max_C')
    """
    rows = []
    n_total = len(values1) * len(values2)
    count = 0

    for v1 in values1:
        for v2 in values2:
            count += 1
            if verbose:
                print(f"  [{count:3d}/{n_total}]  {param1}={v1:.4g}  {param2}={v2:.4g}")

            _set_param(loop, param1, v1)
            _set_param(loop, param2, v2)

            T_cl  = v1 if param1 == 'T_coolant' else (v2 if param2 == 'T_coolant' else T_coolant)
            chi   = v1 if param1 == 'chi_d'     else (v2 if param2 == 'chi_d'     else chi_d)

            state = loop.solve(T_coolant=T_cl, chi_d=chi)
            row   = _state_to_row(state, param1, v1)
            row[param2] = v2

            # Convenience aliases for the second param
            if param2 == 'T_coolant':
                row['T_coolant_C'] = v2 - 273.15
            elif param2 == 'q_flux':
                row['q_flux_W_m2'] = v2

            rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Fluid comparison
# ---------------------------------------------------------------------------

def compare_fluids(
    fluids:            List[str],
    loop_factory:      Callable,
    param:             str,
    values:            list,
    T_coolant:         float,
    chi_d:             float = 0.8,
    verbose:           bool  = False,
) -> pd.DataFrame:
    """
    Compare multiple refrigerants over a parameter range.

    Parameters
    ----------
    fluids       : list of CoolProp fluid names, e.g. ['R134a','R1234yf','R245fa']
    loop_factory : callable(fluid) -> Loop
                   A function that builds and returns a Loop for the given fluid.
    param        : parameter to sweep (same as in sweep())
    values       : values to sweep
    T_coolant    : K   coolant temperature
    chi_d        : flow ratio

    Returns
    -------
    DataFrame with a 'fluid' column added.

    Example
    -------
    >>> from pyp2pl.utils.parametric import compare_fluids
    >>> def make_loop(fluid):
    ...     return Loop(fluid, [Pump(fluid), Preheater(fluid), ...])
    >>> df = compare_fluids(['R134a','R1234yf'], make_loop,
    ...                     'q_flux', np.linspace(5e4,20e4,8), T_coolant=278.15)
    >>> df.groupby('fluid').plot(x='q_flux_W_m2', y='T_wall_max_C')
    """
    dfs = []
    for fluid in fluids:
        if verbose:
            print(f"\n  Fluid: {fluid}")
        loop = loop_factory(fluid)
        df   = sweep(loop, param, values, T_coolant, chi_d, verbose=verbose)
        df['fluid'] = fluid
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)


# ---------------------------------------------------------------------------
# Ledinegg stability map
# ---------------------------------------------------------------------------

def ledinegg_map(
    loop,
    q_flux_range:  np.ndarray,
    m_dot_range:   np.ndarray,
    T_coolant:     float,
    delta_m:       float = 1e-5,
    verbose:       bool  = False,
) -> pd.DataFrame:
    """
    Compute the Ledinegg stability indicator over a (q_flux, m_dot) grid.

    For each (q_flux, m_dot) point, compute:
        S = d(ΔP_loop)/d(ṁ)   [Pa·s/kg]

    If S < 0 → Ledinegg unstable (flow excursion onset).
    The stability boundary is where S = 0.

    This uses finite differences on the total loop pressure drop:
        S ≈ [ΔP(ṁ + δ) - ΔP(ṁ - δ)] / (2δ)

    Parameters
    ----------
    loop         : Loop object
    q_flux_range : array of heat fluxes [W/m²]
    m_dot_range  : array of mass flow rates [kg/s]
    T_coolant    : K
    delta_m      : kg/s   finite difference step for derivative
    verbose      : print progress

    Returns
    -------
    DataFrame with columns: q_flux, m_dot, dP_total, dPdm, stable

    Example
    -------
    >>> import numpy as np
    >>> from pyp2pl.utils.parametric import ledinegg_map
    >>> q_arr = np.linspace(5e4, 25e4, 15)
    >>> m_arr = np.linspace(1e-3, 10e-3, 15)
    >>> df = ledinegg_map(loop, q_arr, m_arr, T_coolant=278.15)
    >>> # Plot stability boundary
    >>> stable   = df[df['stable']]
    >>> unstable = df[~df['stable']]
    """
    from pyp2pl.system.solver import _total_dp, _sat_at
    import CoolProp.CoolProp as CP

    rows = []
    n_total = len(q_flux_range) * len(m_dot_range)
    count   = 0

    # Find evaporator and pump
    pump_idx = evap_idx = None
    for i, comp in enumerate(loop.components):
        if 'Pump'      in comp.__class__.__name__: pump_idx = i
        if 'Evaporator' in comp.__class__.__name__: evap_idx = i

    for q in q_flux_range:
        # Set heat flux
        loop.components[evap_idx].q_flux = q

        for m in m_dot_range:
            count += 1
            if verbose and count % 10 == 0:
                print(f"  [{count:4d}/{n_total}]  q={q/1e4:.1f} W/cm²  "
                      f"m={m*1e3:.2f} g/s")

            # Estimate system pressure
            P_init = CP.PropsSI('P', 'T', T_coolant + 10.0, 'Q', 0, loop.fluid)
            sat    = _sat_at(P_init, loop.fluid)
            h_init = CP.PropsSI('H', 'T', sat.T_sat - 2.0, 'P', P_init, loop.fluid)

            # Set reservoir reference if needed
            for comp in loop.components:
                if 'Reservoir' in comp.__class__.__name__:
                    comp.set_reference_pressure(P_init)
                    break

            def dp_at(mdot):
                try:
                    return _total_dp(loop.components, mdot, P_init, h_init,
                                     loop.fluid, pump_idx)
                except Exception:
                    return float('nan')

            dP_c = dp_at(m)
            dP_p = dp_at(m + delta_m)
            dP_m = dp_at(m - delta_m)

            dPdm = (dP_p - dP_m) / (2.0 * delta_m) if not (
                np.isnan(dP_p) or np.isnan(dP_m)) else float('nan')

            rows.append({
                'q_flux_W_m2':  q,
                'q_flux_W_cm2': q / 1e4,
                'm_dot_gs':     m * 1e3,
                'm_dot_kgs':    m,
                'dP_total_Pa':  dP_c,
                'dPdm':         dPdm,
                'stable':       (dPdm >= 0) if not np.isnan(dPdm) else True,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_param(loop, param: str, value):
    """Set a loop parameter in-place."""
    if param == 'q_flux':
        for comp in loop.components:
            if 'Evaporator' in comp.__class__.__name__:
                comp.q_flux = value
    elif param == 'T_coolant':
        for comp in loop.components:
            if 'Condenser' in comp.__class__.__name__:
                comp.T_cl_in = value
    elif param == 'charge_ratio':
        for comp in loop.components:
            if 'Reservoir' in comp.__class__.__name__:
                comp.geo.charge_ratio = value
                comp._P_v_ref = None
    elif param == 'chi_d':
        pass   # handled at solve() call level
    else:
        raise ValueError(
            f"Unknown sweep parameter '{param}'. "
            f"Supported: 'q_flux', 'T_coolant', 'charge_ratio', 'chi_d'."
        )


def _state_to_row(state, param_name: str, param_value) -> dict:
    """Extract key metrics from a LoopState into a flat dict."""
    row = {
        'param_name':    param_name,
        'param_value':   param_value,
        'converged':     state.converged,
        'm_dot_gs':      state.m_dot * 1e3,
        'P_high_kPa':    state._p_high() / 1e3,
        'P_low_kPa':     state._p_low()  / 1e3,
        'T_wall_max_C':  state._t_wall_max(),
        'Q_evap_W':      state._q_evap(),
        'Q_cond_W':      state._q_cond(),
        'W_pump_W':      state._w_pump(),
        'COP':           state._cop(),
    }
    # Convenience aliases
    if param_name == 'q_flux':
        row['q_flux_W_m2']  = param_value
        row['q_flux_W_cm2'] = param_value / 1e4
    elif param_name == 'T_coolant':
        row['T_coolant_C'] = param_value - 273.15
    elif param_name == 'chi_d':
        row['chi_d'] = param_value

    # Per-component metrics
    for comp, res in zip(state.components, state.results):
        name = comp.__class__.__name__
        if 'Evaporator' in name:
            row['HTC_avg']       = res.metrics.get('HTC_avg', float('nan'))
            row['x_out']         = res.metrics.get('x_out',   float('nan'))
            row['T_wall_avg_C']  = res.metrics.get('T_wall_avg_C', float('nan'))
            row['dP_evap_kPa']   = res.metrics.get('delta_P_kPa',  float('nan'))
            row['G_ch']          = res.metrics.get('G_ch',    float('nan'))
        elif 'Condenser' in name:
            row['subcooling_K']  = res.metrics.get('subcooling_K', float('nan'))
            row['dP_cond_kPa']   = res.metrics.get('delta_P_kPa',  float('nan'))
            row['NTU']           = res.metrics.get('NTU',     float('nan'))
        elif 'Pump' in name:
            row['pump_dP_kPa']   = res.metrics.get('delta_P_kPa',  float('nan'))

    return row
