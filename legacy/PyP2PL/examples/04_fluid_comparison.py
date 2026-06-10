"""
examples/04_fluid_comparison.py
================================
Compare R-134a, R-1234yf, and R-245fa in the same P2PL loop geometry.

This study addresses a key research question:
    "Which low-GWP refrigerant best replaces R-134a in this system?"

Outputs:
  - Wall temperature vs heat flux for all three fluids
  - HTC vs heat flux
  - Mass flow rate vs heat flux
  - Summary table of key metrics at q=10 W/cm²

Reference:
  R-134a:   GWP = 1430   (reference fluid, Kokate)
  R-1234yf: GWP < 1      (HFO drop-in replacement)
  R-245fa:  GWP = 1030   (used in ORC systems)

Run from Spyder (F5) or terminal:
    python examples/04_fluid_comparison.py
"""

import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

from pyp2pl.system.loop import Loop
from pyp2pl.components.evaporator  import MicrochannelEvaporator, EvaporatorGeometry
from pyp2pl.components.condenser   import FlatPlateCondenser
from pyp2pl.components.preheater   import Preheater
from pyp2pl.components.pump        import Pump
from pyp2pl.components.reservoir   import Reservoir, ReservoirGeometry

from pyp2pl.utils.parametric  import compare_fluids
from pyp2pl.utils.plotting    import plot_fluid_comparison

# Fluids to compare
FLUIDS = ['R134a', 'R1234yf', 'R245fa']

# Fluid metadata (for annotation)
FLUID_INFO = {
    'R134a':   {'GWP': 1430, 'label': 'R-134a (ref)'},
    'R1234yf': {'GWP': 4,    'label': 'R-1234yf (low-GWP)'},
    'R245fa':  {'GWP': 1030, 'label': 'R-245fa'},
}

T_COOL = 278.15   # K (5°C)
CHI_D  = 0.8


def make_loop(fluid):
    """Build a loop for any CoolProp fluid using Kokate baseline geometry."""
    geo = EvaporatorGeometry(N_ch=44, W_ch=0.5e-3, H_ch=2.5e-3, L_ch=25e-3)
    return Loop(fluid, [
        Pump(fluid, eta=0.8, mode='ideal'),
        Preheater(fluid, mode='target_sat'),
        MicrochannelEvaporator(fluid, q_flux=10e4, geometry=geo),
        FlatPlateCondenser(fluid, T_coolant_in=T_COOL),
        Reservoir(fluid, geometry=ReservoirGeometry(
            V_total=780e-6, charge_ratio=0.725)),
    ])


# =============================================================================
# Run comparison sweep
# =============================================================================
print("Running fluid comparison sweep (5 – 20 W/cm²)...")
print("Fluids:", FLUIDS)

q_values = np.linspace(5e4, 20e4, 9)   # W/m²

df_all = compare_fluids(
    fluids       = FLUIDS,
    loop_factory = make_loop,
    param        = 'q_flux',
    values       = q_values,
    T_coolant    = T_COOL,
    chi_d        = CHI_D,
    verbose      = True,
)
df_all.to_csv('fluid_comparison.csv', index=False)
print(f"\n  → fluid_comparison.csv  ({len(df_all)} rows)")

# =============================================================================
# Summary table at q = 10 W/cm²
# =============================================================================
print(f"\n{'='*65}")
print("  Fluid comparison at q\" = 10 W/cm², T_coolant = 5°C, chi_d = 0.8")
print(f"{'='*65}")
print(f"  {'Fluid':<12} {'GWP':>5}  {'T_wall [°C]':>12}  {'HTC [W/m²K]':>12}  "
      f"{'m_dot [g/s]':>12}  {'ΔP [kPa]':>10}")
print(f"  {'-'*65}")

for fluid in FLUIDS:
    sub = df_all[df_all['fluid'] == fluid]
    row = sub.iloc[(sub['q_flux_W_cm2'] - 10.0).abs().argsort().iloc[0]]
    gwp = FLUID_INFO[fluid]['GWP']
    print(f"  {fluid:<12} {gwp:>5}  {row['T_wall_max_C']:>12.1f}  "
          f"{row['HTC_avg']:>12.0f}  {row['m_dot_gs']:>12.3f}  "
          f"{row['dP_evap_kPa']:>10.3f}")

# =============================================================================
# Plots
# =============================================================================
colors = ['#2E6DB4', '#C0561A', '#1E6B3A']
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
fig.suptitle('Fluid comparison: R-134a vs R-1234yf vs R-245fa', fontsize=12)

metrics = [
    ('T_wall_max_C', 'Max wall temperature [°C]'),
    ('HTC_avg',      r'Average HTC [W/(m²·K)]'),
    ('m_dot_gs',     r'Mass flow rate $\dot{m}$ [g/s]'),
]

for ax, (col, ylabel) in zip(axes, metrics):
    for i, fluid in enumerate(FLUIDS):
        sub = df_all[df_all['fluid'] == fluid].sort_values('q_flux_W_cm2')
        lbl = FLUID_INFO[fluid]['label']
        ax.plot(sub['q_flux_W_cm2'], sub[col], 'o-',
                color=colors[i], lw=2, markersize=5, label=lbl)
    ax.set_xlabel(r"Heat flux $q''$ [W/cm²]")
    ax.set_ylabel(ylabel)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig('fluid_comparison.png', dpi=150, bbox_inches='tight')
print("\n  → fluid_comparison.png")
plt.show()
