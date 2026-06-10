"""
pyp2pl.utils.plotting
======================
Standard plots for P2PL parametric studies and validation.

All functions accept a pandas DataFrame (from parametric.sweep() or
validation.load_kokate_data()) and return a matplotlib Figure.

Functions
---------
plot_sweep(df, x, y, ...)
    Generic 1-D sweep line plot with optional multi-line grouping.

plot_sweep_multi(df, x, ys, ...)
    Multiple y-axes on the same sweep result.

plot_boiling_curve(df, ...)
    Wall superheat vs heat flux (boiling curve).

plot_stability_map(df_ledinegg, ...)
    Ledinegg stability map: stable/unstable regions on (q, m_dot) plane.

plot_validation(df_pred, df_meas, quantity, ...)
    Predicted vs measured parity chart with ±20% error bands.

plot_Ph_diagram(state, ...)
    P-h diagram for a LoopState (re-export from results.py).

plot_fluid_comparison(df, x, y, fluid_col, ...)
    Side-by-side comparison of multiple fluids.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import List, Optional


# Default style — clean, publication-quality
_STYLE = {
    'figure.dpi':         120,
    'axes.spines.top':    False,
    'axes.spines.right':  False,
    'axes.grid':          True,
    'grid.alpha':         0.3,
    'grid.linestyle':     '--',
    'font.size':          11,
    'axes.labelsize':     12,
    'legend.framealpha':  0.85,
}

_COLORS = ['#2E6DB4', '#C0561A', '#1E6B3A', '#7B3F9E', '#888780', '#BA7517']

# Map parameter names to nice axis labels
_LABELS = {
    'q_flux_W_m2':   r"Heat flux $q''$ [W/m²]",
    'q_flux_W_cm2':  r"Heat flux $q''$ [W/cm²]",
    'T_coolant_C':   "Coolant inlet temperature [°C]",
    'm_dot_gs':      r"Mass flow rate $\dot{m}$ [g/s]",
    'G_ch':          r"Channel mass flux $G$ [kg/(m²·s)]",
    'T_wall_max_C':  "Max wall temperature [°C]",
    'T_wall_avg_C':  "Avg wall temperature [°C]",
    'HTC_avg':       r"Average HTC $\bar{\alpha}$ [W/(m²·K)]",
    'x_out':         "Exit vapor quality $x_{out}$ [–]",
    'dP_evap_kPa':   "Evaporator pressure drop [kPa]",
    'Q_evap_W':      r"Evaporator heat load $Q_e$ [W]",
    'COP':           "COP [–]",
    'subcooling_K':  "Subcooling [K]",
    'pump_dP_kPa':   "Pump head [kPa]",
}


def _apply_style():
    plt.rcParams.update(_STYLE)


# ---------------------------------------------------------------------------
# Generic 1-D sweep plot
# ---------------------------------------------------------------------------

def plot_sweep(
    df,
    x:         str,
    y:         str,
    hue:       Optional[str] = None,
    title:     Optional[str] = None,
    xlabel:    Optional[str] = None,
    ylabel:    Optional[str] = None,
    marker:    str = 'o',
    ax=None,
    show:      bool = True,
) -> plt.Axes:
    """
    Line plot of y vs x from a sweep DataFrame.

    Parameters
    ----------
    df    : DataFrame from parametric.sweep() or similar
    x, y  : column names
    hue   : optional column to split into multiple lines (e.g. 'fluid')
    title : axes title
    xlabel, ylabel : axis labels (auto-detected from _LABELS if None)

    Returns
    -------
    matplotlib Axes

    Example
    -------
    >>> ax = plot_sweep(df, 'q_flux_W_cm2', 'T_wall_max_C',
    ...                 title='Wall temperature vs heat flux')
    """
    _apply_style()
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4.5))

    if hue is None:
        ax.plot(df[x], df[y], f'{marker}-', color=_COLORS[0], lw=2, markersize=5)
    else:
        groups = df[hue].unique()
        for i, grp in enumerate(groups):
            sub = df[df[hue] == grp]
            ax.plot(sub[x], sub[y], f'{marker}-',
                    color=_COLORS[i % len(_COLORS)], lw=2,
                    markersize=5, label=str(grp))
        ax.legend()

    ax.set_xlabel(xlabel or _LABELS.get(x, x))
    ax.set_ylabel(ylabel or _LABELS.get(y, y))
    if title:
        ax.set_title(title, pad=10)

    plt.tight_layout()
    if show:
        plt.show()
    return ax


# ---------------------------------------------------------------------------
# Multi-y sweep plot
# ---------------------------------------------------------------------------

def plot_sweep_multi(
    df,
    x:      str,
    ys:     List[str],
    title:  Optional[str] = None,
    xlabel: Optional[str] = None,
    show:   bool = True,
) -> plt.Figure:
    """
    Multiple subplots — one per y variable — sharing the same x axis.

    Parameters
    ----------
    df   : DataFrame
    x    : x-axis column name
    ys   : list of y-axis column names

    Example
    -------
    >>> fig = plot_sweep_multi(df, 'q_flux_W_cm2',
    ...     ['T_wall_max_C', 'HTC_avg', 'x_out', 'dP_evap_kPa'])
    """
    _apply_style()
    n = len(ys)
    fig, axes = plt.subplots(n, 1, figsize=(7, 3.5 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, y, col in zip(axes, ys, _COLORS[:n]):
        ax.plot(df[x], df[y], 'o-', color=col, lw=2, markersize=5)
        ax.set_ylabel(_LABELS.get(y, y))
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    axes[-1].set_xlabel(xlabel or _LABELS.get(x, x))
    if title:
        fig.suptitle(title, y=1.01, fontsize=12)

    plt.tight_layout()
    if show:
        plt.show()
    return fig


# ---------------------------------------------------------------------------
# Boiling curve
# ---------------------------------------------------------------------------

def plot_boiling_curve(
    df,
    x:      str = 'T_wall_avg_C',   # wall superheat or T_wall
    y:      str = 'q_flux_W_cm2',
    hue:    Optional[str] = None,
    T_sat_C: Optional[float] = None,
    title:  str = 'Boiling curve',
    ax=None,
    show:   bool = True,
) -> plt.Axes:
    """
    Wall temperature (or superheat) vs heat flux — the boiling curve.

    If T_sat_C is provided, the x-axis shows wall superheat (T_wall - T_sat).

    Parameters
    ----------
    df       : DataFrame with T_wall and q_flux columns
    T_sat_C  : saturation temperature [°C] for superheat calculation
    """
    _apply_style()
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 5))

    x_data = df[x]
    xlabel = _LABELS.get(x, x)
    if T_sat_C is not None:
        x_data = df[x] - T_sat_C
        xlabel = r"Wall superheat $(T_{wall} - T_{sat})$ [K]"

    if hue is None:
        ax.semilogy(x_data, df[y], 'o-', color=_COLORS[0], lw=2, markersize=5)
    else:
        for i, grp in enumerate(df[hue].unique()):
            sub = df[df[hue] == grp]
            ax.semilogy(sub[x] if T_sat_C is None else sub[x] - T_sat_C,
                        sub[y], 'o-',
                        color=_COLORS[i % len(_COLORS)], lw=2,
                        markersize=5, label=str(grp))
        ax.legend()

    ax.set_xlabel(xlabel)
    ax.set_ylabel(_LABELS.get(y, y))
    ax.set_title(title, pad=10)
    plt.tight_layout()
    if show:
        plt.show()
    return ax


# ---------------------------------------------------------------------------
# Ledinegg stability map
# ---------------------------------------------------------------------------

def plot_stability_map(
    df,
    x:     str = 'G_ch',
    y:     str = 'q_flux_W_cm2',
    title: str = 'Ledinegg stability map',
    ax=None,
    show:  bool = True,
) -> plt.Axes:
    """
    Plot the Ledinegg stability map.

    Stable region (d(ΔP)/d(ṁ) ≥ 0) shown in blue,
    unstable region (d(ΔP)/d(ṁ) < 0) shown in red.
    The stability boundary is the separating contour.

    Parameters
    ----------
    df : DataFrame from parametric.ledinegg_map()
    """
    _apply_style()
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 5))

    stable   = df[df['stable']   == True]
    unstable = df[df['stable']   == False]

    if len(stable) > 0:
        ax.scatter(stable[x],   stable[y],   c='#2E6DB4', s=25,
                   label='Stable', alpha=0.7, zorder=3)
    if len(unstable) > 0:
        ax.scatter(unstable[x], unstable[y], c='#C0561A', s=25,
                   label='Unstable (Ledinegg)', alpha=0.7, zorder=3)

    ax.set_xlabel(_LABELS.get(x, x))
    ax.set_ylabel(_LABELS.get(y, y))
    ax.set_title(title, pad=10)
    ax.legend()
    plt.tight_layout()
    if show:
        plt.show()
    return ax


# ---------------------------------------------------------------------------
# Validation parity chart
# ---------------------------------------------------------------------------

def plot_validation(
    predicted:  np.ndarray,
    measured:   np.ndarray,
    quantity:   str = 'HTC [W/(m²K)]',
    title:      Optional[str] = None,
    error_bands: List[float] = [20.0],
    ax=None,
    show:       bool = True,
) -> plt.Axes:
    """
    Predicted vs measured parity chart.

    Draws the 1:1 line and ±N% error bands.

    Parameters
    ----------
    predicted, measured : arrays of the same quantity
    quantity : label for the axes
    error_bands : list of % error band values, e.g. [10, 20]

    Returns
    -------
    Axes with MAE annotation.

    Example
    -------
    >>> plot_validation(df['HTC_pred'].values,
    ...                 df['HTC_meas'].values,
    ...                 quantity='HTC [W/(m²K)]')
    """
    _apply_style()
    predicted = np.asarray(predicted)
    measured  = np.asarray(measured)

    if ax is None:
        _, ax = plt.subplots(figsize=(5.5, 5))

    vmin = min(predicted.min(), measured.min()) * 0.9
    vmax = max(predicted.max(), measured.max()) * 1.1
    ref  = np.linspace(vmin, vmax, 100)

    # Error bands
    band_colors = ['#D6E8F7', '#A8CAE8', '#7AABDA']
    for j, pct in enumerate(sorted(error_bands, reverse=True)):
        frac = pct / 100.0
        ax.fill_between(ref, ref * (1 - frac), ref * (1 + frac),
                        color=band_colors[j % len(band_colors)],
                        alpha=0.4, label=f'±{pct:.0f}%')

    # 1:1 line
    ax.plot(ref, ref, 'k-', lw=1.2, label='1:1')

    # Data points
    ax.scatter(measured, predicted, c=_COLORS[0], s=35, zorder=5, alpha=0.85)

    # MAE annotation
    mae = np.mean(np.abs(predicted - measured) / np.maximum(np.abs(measured), 1e-12)) * 100
    ax.text(0.04, 0.96, f'MAE = {mae:.1f}%',
            transform=ax.transAxes, va='top', fontsize=10,
            bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.8))

    ax.set_xlabel(f'Measured {quantity}')
    ax.set_ylabel(f'Predicted {quantity}')
    ax.set_xlim(vmin, vmax)
    ax.set_ylim(vmin, vmax)
    ax.set_aspect('equal')
    ax.set_title(title or f'Validation — {quantity}', pad=10)
    ax.legend(fontsize=9)
    plt.tight_layout()
    if show:
        plt.show()
    return ax


# ---------------------------------------------------------------------------
# Fluid comparison
# ---------------------------------------------------------------------------

def plot_fluid_comparison(
    df,
    x:          str,
    y:          str,
    fluid_col:  str = 'fluid',
    title:      Optional[str] = None,
    xlabel:     Optional[str] = None,
    ylabel:     Optional[str] = None,
    show:       bool = True,
) -> plt.Axes:
    """
    Overlay multiple fluids on the same axes.

    Parameters
    ----------
    df        : DataFrame from parametric.compare_fluids()
    x, y      : column names
    fluid_col : column containing fluid names

    Example
    -------
    >>> plot_fluid_comparison(df, 'q_flux_W_cm2', 'T_wall_max_C')
    """
    _apply_style()
    _, ax = plt.subplots(figsize=(7, 4.5))

    for i, fluid in enumerate(df[fluid_col].unique()):
        sub = df[df[fluid_col] == fluid].sort_values(x)
        ax.plot(sub[x], sub[y], 'o-',
                color=_COLORS[i % len(_COLORS)],
                lw=2, markersize=5, label=fluid)

    ax.set_xlabel(xlabel or _LABELS.get(x, x))
    ax.set_ylabel(ylabel or _LABELS.get(y, y))
    ax.set_title(title or f'{y} — fluid comparison', pad=10)
    ax.legend()
    plt.tight_layout()
    if show:
        plt.show()
    return ax
