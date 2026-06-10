"""
examples/03_parametric_sweeps.py
=================================
Parametric study of the P2PL system response to:
  1. Heat flux sweep          (q" = 5 – 25 W/cm²)
  2. Coolant temperature sweep (T_cl = -5 – 20°C)
  3. Charge ratio sweep        (CR = 60 – 90%)

Each sweep produces a DataFrame and a multi-panel plot.
Results are saved as CSV for further analysis.

Run from Spyder (F5) or terminal:
    python examples/03_parametric_sweeps.py
"""

import numpy as np
import matplotlib.pyplot as plt

from pyp2pl.system.loop import Loop
from pyp2pl.components.evaporator  import MicrochannelEvaporator, EvaporatorGeometry
from pyp2pl.components.condenser   import FlatPlateCondenser
from pyp2pl.components.preheater   import Preheater
from pyp2pl.components.pump        import Pump
from pyp2pl.components.reservoir   import Reservoir, ReservoirGeometry

from pyp2pl.utils.parametric import sweep, sweep_2d
from pyp2pl.utils.plotting   import plot_sweep_multi

FLUID  = 'R134a'
T_COOL = 278.15   # K (5°C baseline)
CHI_D  = 0.8

def make_loop(fluid=FLUID, T_cool=T_COOL):
    geo = EvaporatorGeometry(N_ch=44, W_ch=0.5e-3, H_ch=2.5e-3, L_ch=25e-3)
    return Loop(fluid, [
        Pump(fluid, eta=0.8, mode='ideal'),
        Preheater(fluid, mode='target_sat'),
        MicrochannelEvaporator(fluid, q_flux=10e4, geometry=geo),
        FlatPlateCondenser(fluid, T_coolant_in=T_cool),
        Reservoir(fluid, geometry=ReservoirGeometry(
            V_total=780e-6, charge_ratio=0.725)),
    ])

# =============================================================================
# Sweep 1: Heat flux
# =============================================================================
print("Sweep 1: heat flux (5 – 25 W/cm²)...")
q_values = np.linspace(5e4, 25e4, 12)   # W/m²
loop = make_loop()
df_q = sweep(loop, 'q_flux', q_values, T_coolant=T_COOL, chi_d=CHI_D, verbose=True)
df_q.to_csv('sweep_heatflux.csv', index=False)
print(f"  → sweep_heatflux.csv  ({len(df_q)} rows)\n")

fig = plot_sweep_multi(df_q, 'q_flux_W_cm2',
    ['T_wall_max_C', 'HTC_avg', 'x_out', 'm_dot_gs'],
    title='System response — heat flux sweep', show=False)
fig.savefig('sweep_heatflux.png', dpi=150, bbox_inches='tight')
print("  → sweep_heatflux.png")

# =============================================================================
# Sweep 2: Coolant temperature
# =============================================================================
print("\nSweep 2: coolant temperature (-5 – 20°C)...")
T_values = np.linspace(268.15, 293.15, 10)   # K
loop2 = make_loop()
df_T = sweep(loop2, 'T_coolant', T_values, T_coolant=T_COOL, chi_d=CHI_D, verbose=True)
df_T.to_csv('sweep_coolant_temp.csv', index=False)
print(f"  → sweep_coolant_temp.csv  ({len(df_T)} rows)\n")

fig2, axes2 = plt.subplots(1, 2, figsize=(11, 4))
fig2.suptitle('System response — coolant temperature sweep', fontsize=11)

axes2[0].plot(df_T['T_coolant_C'], df_T['T_wall_max_C'],
              'o-', color='#2E6DB4', lw=2, markersize=5)
axes2[0].set_xlabel('Coolant temperature [°C]')
axes2[0].set_ylabel('Max wall temperature [°C]')
axes2[0].grid(True, alpha=0.3, linestyle='--')
axes2[0].spines['top'].set_visible(False)
axes2[0].spines['right'].set_visible(False)

axes2[1].plot(df_T['T_coolant_C'], df_T['m_dot_gs'],
              'o-', color='#C0561A', lw=2, markersize=5)
axes2[1].set_xlabel('Coolant temperature [°C]')
axes2[1].set_ylabel(r'Mass flow rate $\dot{m}$ [g/s]')
axes2[1].grid(True, alpha=0.3, linestyle='--')
axes2[1].spines['top'].set_visible(False)
axes2[1].spines['right'].set_visible(False)

plt.tight_layout()
fig2.savefig('sweep_coolant_temp.png', dpi=150, bbox_inches='tight')
print("  → sweep_coolant_temp.png")

# =============================================================================
# Sweep 3: Charge ratio
# =============================================================================
print("\nSweep 3: charge ratio (60 – 90%)...")
cr_values = np.linspace(0.60, 0.90, 10)
loop3 = make_loop()
df_cr = sweep(loop3, 'charge_ratio', cr_values, T_coolant=T_COOL, chi_d=CHI_D,
              verbose=True)
df_cr['charge_ratio_pct'] = df_cr['param_value'] * 100
df_cr.to_csv('sweep_charge_ratio.csv', index=False)
print(f"  → sweep_charge_ratio.csv  ({len(df_cr)} rows)\n")

fig3, axes3 = plt.subplots(1, 2, figsize=(11, 4))
fig3.suptitle('System response — charge ratio sweep', fontsize=11)

axes3[0].plot(df_cr['charge_ratio_pct'], df_cr['P_high_kPa'],
              'o-', color='#2E6DB4', lw=2, markersize=5)
axes3[0].set_xlabel('Charge ratio CR [%]')
axes3[0].set_ylabel('System pressure [kPa]')
axes3[0].grid(True, alpha=0.3, linestyle='--')
axes3[0].spines['top'].set_visible(False)
axes3[0].spines['right'].set_visible(False)

axes3[1].plot(df_cr['charge_ratio_pct'], df_cr['T_wall_max_C'],
              'o-', color='#C0561A', lw=2, markersize=5)
axes3[1].set_xlabel('Charge ratio CR [%]')
axes3[1].set_ylabel('Max wall temperature [°C]')
axes3[1].grid(True, alpha=0.3, linestyle='--')
axes3[1].spines['top'].set_visible(False)
axes3[1].spines['right'].set_visible(False)

plt.tight_layout()
fig3.savefig('sweep_charge_ratio.png', dpi=150, bbox_inches='tight')
print("  → sweep_charge_ratio.png")

# =============================================================================
# 2-D sweep: heat flux × coolant temperature  (response surface)
# =============================================================================
print("\n2-D sweep: q\" × T_coolant (response surface)...")
q_2d = np.linspace(5e4, 20e4, 6)
T_2d = np.linspace(271.15, 291.15, 5)
loop4 = make_loop()
df_2d = sweep_2d(loop4, 'q_flux', q_2d, 'T_coolant', T_2d,
                 T_coolant=T_COOL, chi_d=CHI_D, verbose=True)
df_2d['T_coolant_C'] = df_2d['T_coolant'] - 273.15
df_2d.to_csv('sweep_2d_q_Tcool.csv', index=False)
print(f"  → sweep_2d_q_Tcool.csv  ({len(df_2d)} rows)")

# Pivot for contour plot
try:
    import pandas as pd
    pivot = df_2d.pivot_table(
        index='q_flux_W_cm2', columns='T_coolant_C', values='T_wall_max_C')

    fig4, ax4 = plt.subplots(figsize=(7, 5))
    cs = ax4.contourf(pivot.columns, pivot.index, pivot.values,
                      levels=15, cmap='RdYlBu_r')
    plt.colorbar(cs, ax=ax4, label='Max wall temperature [°C]')
    ax4.set_xlabel('Coolant temperature [°C]')
    ax4.set_ylabel(r"Heat flux $q''$ [W/cm²]")
    ax4.set_title('Response surface: T_wall_max')
    fig4.savefig('sweep_2d_response_surface.png', dpi=150, bbox_inches='tight')
    print("  → sweep_2d_response_surface.png")
    plt.show()
except Exception as e:
    print(f"  (Contour plot skipped: {e})")

plt.show()
print("\nAll parametric sweeps complete.")
