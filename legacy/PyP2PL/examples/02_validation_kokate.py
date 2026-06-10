"""
examples/02_validation_kokate.py
=================================
Validate PyP2PL against Kokate & Park (2024) experimental data.

Reproduces:
  - Fig. 6: average HTC vs heat flux (Shah correlation)
  - Fig. 7: evaporator pressure drop vs heat flux
  - Table 5 (2023): system-level operating point comparison

Reference:
  Kokate & Park, Appl. Therm. Eng. 249 (2024) 123154
  Kokate & Park, Appl. Therm. Eng. 229 (2023) 120630

Run from Spyder (F5) or terminal:
    python examples/02_validation_kokate.py
"""

import numpy as np
import matplotlib.pyplot as plt

# --- PyP2PL imports ---
from pyp2pl.system.loop import Loop
from pyp2pl.components.evaporator  import MicrochannelEvaporator, EvaporatorGeometry
from pyp2pl.components.condenser   import FlatPlateCondenser
from pyp2pl.components.preheater   import Preheater
from pyp2pl.components.pump        import Pump
from pyp2pl.components.reservoir   import Reservoir, ReservoirGeometry

from pyp2pl.utils.parametric  import sweep
from pyp2pl.utils.validation  import (load_htc_vs_qflux, load_dp_vs_qflux,
                                       load_system_baseline, compute_mae)
from pyp2pl.utils.plotting    import plot_validation

# =============================================================================
# 1. Build the Kokate baseline loop
# =============================================================================

FLUID    = 'R134a'
T_COOL   = 278.15    # K  (5°C)
CHI_D    = 0.8

geo = EvaporatorGeometry(N_ch=44, W_ch=0.5e-3, H_ch=2.5e-3, L_ch=25e-3)

loop = Loop(FLUID, [
    Pump(FLUID, eta=0.8, mode='ideal'),
    Preheater(FLUID, mode='target_sat'),
    MicrochannelEvaporator(FLUID, q_flux=10e4, geometry=geo,
                           htc_correlation='shah'),
    FlatPlateCondenser(FLUID, T_coolant_in=T_COOL),
    Reservoir(FLUID, geometry=ReservoirGeometry(
        V_total=780e-6, charge_ratio=0.725)),
])

# =============================================================================
# 2. Sweep heat flux (5 – 25 W/cm²)  — matching Kokate Fig. 6 & 7
# =============================================================================

print("Running heat flux sweep (5 – 25 W/cm²)...")
q_meas = load_htc_vs_qflux()['q_flux_W_cm2'].values   # [W/cm²]
q_values = q_meas * 1e4                                # convert to W/m²

df_pred = sweep(loop, 'q_flux', q_values, T_coolant=T_COOL,
                chi_d=CHI_D, verbose=True)

# =============================================================================
# 3. Load Kokate measured data
# =============================================================================

df_htc_meas = load_htc_vs_qflux()    # HTC vs q"
df_dp_meas  = load_dp_vs_qflux()     # ΔP  vs q"
sys_ref     = load_system_baseline() # scalar system reference values

# =============================================================================
# 4. Compute MAE
# =============================================================================

mae_htc = compute_mae(df_pred['HTC_avg'].values,
                      df_htc_meas['HTC_meas'].values)

# ΔP sweep covers slightly different q-range — align by index
n_dp  = min(len(df_pred), len(df_dp_meas))
mae_dp = compute_mae(df_pred['dP_evap_kPa'].values[:n_dp],
                     df_dp_meas['dP_evap_kPa'].values[:n_dp])

print(f"\n{'='*55}")
print(f"  Validation results (Shah correlation vs Kokate 2024)")
print(f"{'='*55}")
print(f"  HTC  MAE = {mae_htc:.1f}%   (Kokate reports 37.2% for Shah)")
print(f"  ΔP   MAE = {mae_dp:.1f}%")

# System-level comparison
state_bl = loop.solve(T_coolant=T_COOL, chi_d=CHI_D)
evap_res = state_bl.results[2]   # evaporator
print(f"\n  System-level comparison (q=10 W/cm²):")
print(f"  {'Quantity':<25} {'Predicted':>12} {'Kokate ref':>12} {'Error':>8}")
print(f"  {'-'*60}")

comparisons = [
    ('m_dot [g/s]',   state_bl.m_dot * 1e3,              sys_ref['m_dot_gs']),
    ('T_wall [°C]',   evap_res.metrics['T_wall_avg_C'],   sys_ref['T_wall_C']),
    ('HTC [W/m²K]',   evap_res.metrics['HTC_avg'],        sys_ref['HTC_avg']),
    ('x_out [-]',     evap_res.metrics['x_out'],           sys_ref['x_out']),
    ('ΔP_evap [kPa]', evap_res.metrics['delta_P_kPa'],    sys_ref['dP_evap_kPa']),
]
for name, pred, ref in comparisons:
    err = (pred - ref) / max(abs(ref), 1e-12) * 100
    print(f"  {name:<25} {pred:>12.3f} {ref:>12.3f} {err:>+7.1f}%")

# =============================================================================
# 5. Plots
# =============================================================================

fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
fig.suptitle('PyP2PL Validation vs Kokate & Park (2024)', fontsize=12, y=1.01)

# --- Panel 1: HTC vs heat flux ---
ax = axes[0]
ax.plot(df_pred['q_flux_W_cm2'], df_pred['HTC_avg'],
        'o-', color='#2E6DB4', lw=2, markersize=5, label='PyP2PL (Shah)')
ax.scatter(df_htc_meas['q_flux_W_cm2'], df_htc_meas['HTC_meas'],
           c='#C0561A', s=50, zorder=5, label='Kokate (2024) measured')
ax.set_xlabel(r"Heat flux $q''$ [W/cm²]")
ax.set_ylabel(r"Average HTC $\bar{\alpha}$ [W/(m²·K)]")
ax.set_title(f'HTC vs heat flux\nMAE = {mae_htc:.1f}%')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# --- Panel 2: Pressure drop vs heat flux ---
ax = axes[1]
ax.plot(df_pred['q_flux_W_cm2'].iloc[:n_dp], df_pred['dP_evap_kPa'].iloc[:n_dp],
        'o-', color='#2E6DB4', lw=2, markersize=5, label='PyP2PL')
ax.scatter(df_dp_meas['q_flux_W_cm2'], df_dp_meas['dP_evap_kPa'],
           c='#C0561A', s=50, zorder=5, label='Kokate (2024) measured')
ax.set_xlabel(r"Heat flux $q''$ [W/cm²]")
ax.set_ylabel("Evaporator pressure drop [kPa]")
ax.set_title(f'Pressure drop vs heat flux\nMAE = {mae_dp:.1f}%')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# --- Panel 3: HTC parity chart ---
ax = axes[2]
htc_pred = df_pred['HTC_avg'].values
htc_meas = df_htc_meas['HTC_meas'].values
n_p = min(len(htc_pred), len(htc_meas))
plot_validation(htc_pred[:n_p], htc_meas[:n_p],
                quantity=r'HTC [W/(m²·K)]',
                error_bands=[20.0, 40.0],
                title=f'Parity chart\nMAE = {mae_htc:.1f}%',
                ax=ax, show=False)

plt.tight_layout()
plt.savefig('validation_kokate_2024.png', dpi=150, bbox_inches='tight')
print("\n  Plot saved: validation_kokate_2024.png")
plt.show()

# =============================================================================
# 6. Correlation comparison (all 5 correlations)
# =============================================================================

print(f"\n{'='*55}")
print("  HTC correlation comparison at q=10 W/cm², baseline G")
print(f"{'='*55}")
print(f"  {'Correlation':<20} {'HTC [W/m²K]':>12} {'MAE vs Kokate':>14}")
print(f"  {'-'*48}")

corr_list = ['shah', 'chen', 'bennett_chen', 'gungor_winterton', 'kandlikar']
htc_ref   = load_htc_vs_qflux()

for corr in corr_list:
    # Build a fresh loop with this correlation
    loop_c = Loop(FLUID, [
        Pump(FLUID, eta=0.8, mode='ideal'),
        Preheater(FLUID, mode='target_sat'),
        MicrochannelEvaporator(FLUID, q_flux=10e4, geometry=geo,
                               htc_correlation=corr),
        FlatPlateCondenser(FLUID, T_coolant_in=T_COOL),
        Reservoir(FLUID, geometry=ReservoirGeometry(
            V_total=780e-6, charge_ratio=0.725)),
    ])
    df_c = sweep(loop_c, 'q_flux', q_values, T_coolant=T_COOL, chi_d=CHI_D)

    n_c   = min(len(df_c), len(htc_ref))
    mae_c = compute_mae(df_c['HTC_avg'].values[:n_c],
                        htc_ref['HTC_meas'].values[:n_c])
    htc_at_10 = df_c.loc[df_c['q_flux_W_cm2'].sub(10.0).abs().idxmin(), 'HTC_avg']
    print(f"  {corr:<20} {htc_at_10:>12.0f} {mae_c:>13.1f}%")
