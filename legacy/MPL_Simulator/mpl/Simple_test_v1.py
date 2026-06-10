# -*- coding: utf-8 -*-
"""
Created on Thu Apr  2 14:43:54 2026

@author: AndresH
"""
# import sys, os
# # Asegura que Python use los módulos de ESTA carpeta, no los del sistema
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fluid_properties import FluidState
from pump import PumpFixed
from accumulator import AccumulatorHCA
from evaporator import Evaporator, EvaporatorGeometry
from condenser import Condenser, CondenserGeometry
from loop import build_standard_loop

fluid = "Acetone"

# Acumulador: fija P_sys a T_sat = 30°C
acc = AccumulatorHCA(fluid=fluid, T_set=50+273.15, V_total=0.001)

# Bomba: ΔP fijo 20 kPa, η=60%
pump = PumpFixed(dp_set=15_000.0, eta=0.6, fluid=fluid)

# Evaporador: microcanales aluminio, Q=200 W
geom_evap = EvaporatorGeometry(N_ch=30, L_ch=0.05, W_ch=3e-4, H_ch=2e-4)
evap = Evaporator(geom=geom_evap, Q_evap=200.0)  

# Condensador: placa HX, agua fría a 20°C
geom_cond = CondenserGeometry(N_ch=40, L_p=0.1, D_h=0.003, W_p=0.1)
cond = Condenser(geom=geom_cond, T_w_in=20+273.15, mdot_w=3)

# Ensamblar el lazo y resolver en estado estacionario
solver = build_standard_loop(
    pump=pump, evaporator=evap, condenser=cond,
    accumulator=acc, fluid=fluid, verbose=True
)

result = solver.solve(Q_evap=1000.0, mdot_guess=0.01)
print(result.summary())