"""
examples/01_baseline_kokate.py
================================
Reproduce the Kokate & Park (2023 / 2024) baseline P2PL simulation.

Reference conditions (Kokate PhD 2024, Table 2.1 / Table 4.1):
  Fluid     : R-134a
  q"        : 10 W/cm²  (100 000 W/m²)
  T_coolant : 5°C
  CR        : 72.5%
  chi_d     : 0.8  (desired flow ratio, Kokate control law)
  G_ch ref  : 47.9 kg/(m²·s)

Run this script from Spyder (F5) or from the terminal:
    python examples/01_baseline_kokate.py
"""

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
from pyp2pl.system.loop import Loop
from pyp2pl.components.evaporator  import MicrochannelEvaporator, EvaporatorGeometry
from pyp2pl.components.condenser   import FlatPlateCondenser
from pyp2pl.components.preheater   import Preheater
from pyp2pl.components.pump        import Pump
from pyp2pl.components.reservoir   import Reservoir, ReservoirGeometry

# ---------------------------------------------------------------------------
# 1.  Define components
#     All geometry defaults match Kokate's experimental setup.
#     Change any parameter here to run your own case.
# ---------------------------------------------------------------------------

# Evaporator — Lytron CP20G03 microchannel heat sink
geo_evap = EvaporatorGeometry(
    N_ch = 44,          # number of parallel microchannels
    W_ch = 0.5e-3,      # m  channel width
    H_ch = 2.5e-3,      # m  channel height
    L_ch = 25.0e-3,     # m  channel length
)

pump = Pump(
    fluid = 'R134a',
    eta   = 0.8,        # pump efficiency (Kokate assumption)
    mode  = 'ideal',    # ideal pump: head = loop ΔP
)

preh = Preheater(
    fluid = 'R134a',
    mode  = 'target_sat',   # always deliver saturated liquid to evaporator
)

evap = MicrochannelEvaporator(
    fluid            = 'R134a',
    q_flux           = 10e4,    # W/m²  — heat flux per channel wall
    geometry         = geo_evap,
    htc_correlation  = 'shah',  # best performer vs Kokate data (MAE 37%)
)

cond = FlatPlateCondenser(
    fluid         = 'R134a',
    T_coolant_in  = 278.15,   # K  (5°C — Kokate baseline)
    coolant_fluid = 'Water',  # use 'INCOMP::MEG[0.5]' for 50/50 EGW
)

res = Reservoir(
    fluid    = 'R134a',
    geometry = ReservoirGeometry(
        V_total      = 780e-6,  # m³
        charge_ratio = 0.725,   # 72.5% liquid fill
        polytropic_n = 1.4,     # isentropic ideal gas
    ),
)

# ---------------------------------------------------------------------------
# 2.  Assemble the loop
#     Order = flow direction, starting from pump outlet.
# ---------------------------------------------------------------------------
loop = Loop(
    fluid      = 'R134a',
    components = [pump, preh, evap, cond, res],
)

# ---------------------------------------------------------------------------
# 3.  Solve steady state
# ---------------------------------------------------------------------------
print("Solving Kokate baseline (q=10 W/cm², T_coolant=5°C, chi_d=0.8)...\n")

state = loop.solve(
    T_coolant    = 278.15,   # K  coolant inlet temperature
    chi_d        = 0.8,      # desired flow ratio (Kokate control parameter)
    verbose      = True,     # print solver iterations
)

# ---------------------------------------------------------------------------
# 4.  Print results
# ---------------------------------------------------------------------------
print()
print(state.summary())

# ---------------------------------------------------------------------------
# 5.  Plots  (comment out if running without display)
# ---------------------------------------------------------------------------
state.plot_Ph()     # Pressure-enthalpy diagram
state.plot_loop()   # Pressure profile + temperatures + energy flows

# ---------------------------------------------------------------------------
# 6.  Export to DataFrame (useful for further analysis)
# ---------------------------------------------------------------------------
df = state.to_dataframe()
print("\nNode states as DataFrame:")
print(df.to_string(index=False))
