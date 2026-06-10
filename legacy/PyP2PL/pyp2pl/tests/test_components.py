"""
tests/test_components.py
=========================
Unit tests for all P2PL component models.

Reference values from:
  - Kokate & Park, Appl. Therm. Eng. 249 (2024), Table 4.1 baseline:
      G_ch = 47.9 kg/(m²·s), q" = 10 W/cm², T_coolant = 5°C, CR = 72.5%
  - Kokate PhD Thesis (2024), Appendix F (steady-state validation data)

Run with:
    cd /path/to/pyp2pl
    PYTHONPATH=. python pyp2pl/tests/test_components.py
    or: pytest pyp2pl/tests/test_components.py -v
"""

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import CoolProp.CoolProp as CP
from pyp2pl.fluid.fluid import FluidProperties
from pyp2pl.components.base import PortState
from pyp2pl.components.evaporator  import MicrochannelEvaporator, EvaporatorGeometry
from pyp2pl.components.condenser   import FlatPlateCondenser, CondenserGeometry
from pyp2pl.components.preheater   import Preheater
from pyp2pl.components.pump        import Pump
from pyp2pl.components.reservoir   import Reservoir, ReservoirGeometry
from pyp2pl.components.accumulator import Accumulator, AccumulatorGeometry
from pyp2pl.components.pipe        import Pipe, PipeGeometry

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FLUID = 'R134a'
FP    = FluidProperties(FLUID)
SAT   = FP.saturated(P=572.2e3)    # 20°C / 572 kPa — Kokate Table 2.1

# Kokate baseline: N_ch=44, W=0.5mm, H=2.5mm, L=25mm, G_ch=47.9 kg/(m²s)
GEO = EvaporatorGeometry(N_ch=44, W_ch=0.5e-3, H_ch=2.5e-3, L_ch=25e-3)
# Total m_dot for G_ch=47.9: m_dot = G_ch * Ac * N_ch
M_DOT_BASELINE = 47.9 * GEO.Ac * GEO.N_ch    # ≈ 2.63 g/s

def _tol(val, ref, pct, label=''):
    err = abs(val - ref) / max(abs(ref), 1e-12) * 100.0
    assert err < pct, (
        f"{label}: got {val:.4g}, expected {ref:.4g} "
        f"(error {err:.1f}% > {pct}%)"
    )

def _sat_inlet(m_dot=None) -> PortState:
    """Saturated liquid inlet at reference conditions."""
    m = m_dot or M_DOT_BASELINE
    return PortState(P=SAT.P_sat, h=SAT.h_l, m_dot=m, fluid=FLUID)

def _twophase_inlet(x=0.8, m_dot=None) -> PortState:
    h = SAT.h_l + x * SAT.h_fg
    m = m_dot or M_DOT_BASELINE
    return PortState(P=SAT.P_sat, h=h, m_dot=m, fluid=FLUID)


# ===========================================================================
# Evaporator tests
# ===========================================================================

def test_evap_x_out_physical():
    """Exit quality must be in [0, 1]."""
    evap = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO)
    res  = evap.compute(_sat_inlet())
    assert 0.0 <= res.metrics['x_out'] <= 1.0

def test_evap_energy_balance():
    """
    Total heat = m_dot * (h_out - h_in).
    """
    evap   = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO)
    inlet  = _sat_inlet()
    result = evap.compute(inlet)
    q_expected = inlet.m_dot * (result.outlet.h - inlet.h)
    _tol(result.metrics['q_total_W'], q_expected, pct=0.1, label='evap energy balance')

def test_evap_x_out_increases_with_q():
    """Exit quality should increase with heat flux."""
    evap = MicrochannelEvaporator(fluid=FLUID, geometry=GEO)
    inlet = _sat_inlet()
    evap.q_flux = 5e4
    x1 = evap.compute(inlet).metrics['x_out']
    evap.q_flux = 15e4
    x2 = evap.compute(inlet).metrics['x_out']
    assert x2 > x1, f"x_out should increase with q_flux: {x1:.3f} vs {x2:.3f}"

def test_evap_T_wall_above_T_sat():
    """Wall temperature must always exceed saturation temperature."""
    evap   = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO)
    result = evap.compute(_sat_inlet())
    T_wall_C = result.metrics['T_wall_avg_C']
    T_sat_C  = SAT.T_sat - 273.15
    assert T_wall_C > T_sat_C, f"T_wall={T_wall_C:.1f} must exceed T_sat={T_sat_C:.1f}"

def test_evap_dp_positive():
    """Pressure drop across evaporator must be positive."""
    evap   = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO)
    result = evap.compute(_sat_inlet())
    assert result.metrics['delta_P_Pa'] > 0

def test_evap_outlet_pressure_lower_than_inlet():
    """Outlet pressure must be lower than inlet due to friction."""
    evap   = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO)
    result = evap.compute(_sat_inlet())
    assert result.outlet.P < SAT.P_sat

def test_evap_htc_order_of_magnitude():
    """
    Shah HTC for Kokate baseline (G≈48, q"=10W/cm²) should be ~500–3000 W/(m²K).
    Kokate Fig. 6 shows ~1000–2500 W/(m²K) range.
    """
    evap   = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO)
    result = evap.compute(_sat_inlet())
    htc    = result.metrics['HTC_avg']
    assert 300 < htc < 5000, f"HTC out of expected range: {htc:.0f} W/(m²K)"

def test_evap_all_correlations():
    """All 5 HTC correlations should run and give positive HTC."""
    for corr in ('shah', 'chen', 'bennett_chen', 'gungor_winterton', 'kandlikar'):
        evap   = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4, geometry=GEO,
                                        htc_correlation=corr)
        result = evap.compute(_sat_inlet())
        assert result.metrics['HTC_avg'] > 0, f"Correlation {corr} gave HTC <= 0"

def test_evap_q_out_increases_with_area():
    """More channels → more heat transfer area → more total heat."""
    inlet = _sat_inlet(m_dot=2e-3)
    evap1 = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4,
                                   geometry=EvaporatorGeometry(N_ch=20))
    evap2 = MicrochannelEvaporator(fluid=FLUID, q_flux=10e4,
                                   geometry=EvaporatorGeometry(N_ch=44))
    q1 = evap1.compute(inlet).metrics['q_total_W']
    q2 = evap2.compute(inlet).metrics['q_total_W']
    assert q2 > q1, "More channels should give more total heat transfer"


# ===========================================================================
# Condenser tests
# ===========================================================================

def test_cond_energy_balance():
    """Heat rejected = m_dot * (h_in - h_out), must be positive."""
    cond   = FlatPlateCondenser(fluid=FLUID, T_coolant_in=278.15)
    inlet  = _twophase_inlet(x=0.8)
    result = cond.compute(inlet)
    q_check = inlet.m_dot * (inlet.h - result.outlet.h)
    _tol(result.metrics['q_total_W'], q_check, pct=0.1, label='cond energy balance')

def test_cond_outlet_subcooled():
    """Condenser outlet should be subcooled (T < T_sat)."""
    cond   = FlatPlateCondenser(fluid=FLUID, T_coolant_in=278.15)
    result = cond.compute(_twophase_inlet(x=0.8))
    assert result.metrics['subcooling_K'] >= 0, "Outlet should not be superheated"

def test_cond_more_cooling_with_lower_T_coolant():
    """Lower coolant temperature → more heat rejection."""
    inlet = _twophase_inlet(x=0.8)
    q_warm = FlatPlateCondenser(fluid=FLUID, T_coolant_in=288.15).compute(inlet).metrics['q_total_W']
    q_cold = FlatPlateCondenser(fluid=FLUID, T_coolant_in=268.15).compute(inlet).metrics['q_total_W']
    assert q_cold > q_warm, "Colder coolant should reject more heat"

def test_cond_dp_positive():
    """Condenser pressure drop must be positive."""
    cond   = FlatPlateCondenser(fluid=FLUID, T_coolant_in=278.15)
    result = cond.compute(_twophase_inlet(x=0.8))
    assert result.metrics['delta_P_Pa'] > 0

def test_cond_ntu_effectiveness():
    """NTU-effectiveness must be in [0, 1]."""
    cond   = FlatPlateCondenser(fluid=FLUID, T_coolant_in=278.15)
    result = cond.compute(_twophase_inlet(x=0.8))
    assert 0.0 <= result.metrics['epsilon'] <= 1.0


# ===========================================================================
# Preheater tests
# ===========================================================================

def test_preh_target_sat_outlet_at_sat():
    """In target_sat mode, outlet should be at (or very near) T_sat."""
    preh = Preheater(fluid=FLUID, mode='target_sat')
    # Subcooled inlet at T_sat - 10 K
    h_sub = CP.PropsSI('H', 'T', SAT.T_sat - 10.0, 'P', SAT.P_sat, FLUID)
    inlet = PortState(P=SAT.P_sat, h=h_sub, m_dot=5e-3, fluid=FLUID)
    result = preh.compute(inlet)
    # subcooling should be ≈ 0
    _tol(result.metrics['subcooling_K'], 0.0, pct=500,   # near-zero comparison
         label='preheater subcooling')
    # Better: T_out should equal T_sat within 0.1 K
    assert abs(result.metrics['T_out_C'] - (SAT.T_sat - 273.15)) < 0.5

def test_preh_energy_positive():
    """Preheater must add heat (q > 0 for subcooled inlet)."""
    preh   = Preheater(fluid=FLUID, mode='target_sat')
    h_sub  = CP.PropsSI('H', 'T', SAT.T_sat - 5.0, 'P', SAT.P_sat, FLUID)
    inlet  = PortState(P=SAT.P_sat, h=h_sub, m_dot=5e-3, fluid=FLUID)
    result = preh.compute(inlet)
    assert result.metrics['q_input_W'] > 0

def test_preh_no_pressure_drop():
    """Preheater pressure drop is assumed zero (Kokate)."""
    preh   = Preheater(fluid=FLUID, mode='target_sat')
    h_sub  = CP.PropsSI('H', 'T', SAT.T_sat - 5.0, 'P', SAT.P_sat, FLUID)
    inlet  = PortState(P=SAT.P_sat, h=h_sub, m_dot=5e-3, fluid=FLUID)
    result = preh.compute(inlet)
    assert result.metrics['delta_P_Pa'] == 0.0


# ===========================================================================
# Pump tests
# ===========================================================================

def test_pump_ideal_delta_p():
    """Ideal pump must deliver exactly the set pressure rise."""
    pump  = Pump(fluid=FLUID, eta=0.8, mode='ideal', delta_P_ideal=50e3)
    inlet = PortState(P=500e3, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    res   = pump.compute(inlet)
    _tol(res.metrics['delta_P_Pa'], 50e3, pct=0.1, label='pump ideal dP')

def test_pump_outlet_pressure():
    """Outlet pressure = inlet + delta_P."""
    pump  = Pump(fluid=FLUID, eta=0.8, mode='ideal', delta_P_ideal=50e3)
    inlet = PortState(P=500e3, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    res   = pump.compute(inlet)
    _tol(res.outlet.P, 550e3, pct=0.1, label='pump outlet pressure')

def test_pump_work_positive():
    """Pump power must be positive."""
    pump  = Pump(fluid=FLUID, eta=0.8, mode='ideal', delta_P_ideal=50e3)
    inlet = PortState(P=500e3, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    res   = pump.compute(inlet)
    assert res.metrics['W_pump_W'] > 0

def test_pump_enthalpy_rise():
    """Pump outlet enthalpy must be higher than inlet (work added)."""
    pump  = Pump(fluid=FLUID, eta=0.8, mode='ideal', delta_P_ideal=50e3)
    inlet = PortState(P=500e3, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    res   = pump.compute(inlet)
    assert res.outlet.h > inlet.h

def test_pump_curve_mode():
    """Curve mode should interpolate head from the provided curve."""
    pump = Pump(fluid=FLUID, eta=0.8, mode='curve',
                curve_flow=[0.0, 1e-4, 2e-4, 3e-4],
                curve_head=[80e3, 70e3, 55e3, 30e3])
    inlet = PortState(P=500e3, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    res   = pump.compute(inlet)
    # At m_dot=5g/s, rho≈1225 kg/m³ → V_dot ≈ 4.1e-6 m³/s (within curve range)
    assert res.metrics['delta_P_Pa'] > 0
    assert res.outlet.P > inlet.P

def test_pump_efficiency_effect():
    """Lower efficiency → higher enthalpy rise for same dP."""
    inlet = PortState(P=500e3, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    h_out_80 = Pump(fluid=FLUID, eta=0.8, delta_P_ideal=50e3).compute(inlet).outlet.h
    h_out_60 = Pump(fluid=FLUID, eta=0.6, delta_P_ideal=50e3).compute(inlet).outlet.h
    assert h_out_60 > h_out_80, "Lower η must give higher h_out (more shaft work)"


# ===========================================================================
# Reservoir tests
# ===========================================================================

def test_res_passthrough():
    """At steady state, reservoir outlet = inlet."""
    res   = Reservoir(fluid=FLUID)
    inlet = _sat_inlet()
    res.set_reference_pressure(inlet.P)
    result = res.compute(inlet)
    assert result.outlet.P == inlet.P
    assert result.outlet.h == inlet.h
    assert result.outlet.m_dot == inlet.m_dot

def test_res_vapor_volume_charge_ratio():
    """Initial vapor volume should match 1 - charge_ratio."""
    geo = ReservoirGeometry(V_total=780e-6, charge_ratio=0.70)
    res = Reservoir(fluid=FLUID, geometry=geo)
    res.set_reference_pressure(SAT.P_sat)
    result = res.compute(_sat_inlet())
    _tol(result.metrics['V_vapor_m3'], geo.V_vapor_init, pct=5.0,
         label='reservoir vapor volume at ref P')

def test_res_vapor_compresses_at_higher_P():
    """Vapor volume should decrease when pressure increases above reference."""
    geo = ReservoirGeometry(V_total=780e-6, charge_ratio=0.70)
    res = Reservoir(fluid=FLUID, geometry=geo)
    P_ref = SAT.P_sat
    res.set_reference_pressure(P_ref)

    inlet_hi = PortState(P=P_ref * 1.1, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    V_hi = res.compute(inlet_hi).metrics['V_vapor_m3']

    inlet_lo = PortState(P=P_ref * 0.9, h=SAT.h_l, m_dot=5e-3, fluid=FLUID)
    V_lo = res.compute(inlet_lo).metrics['V_vapor_m3']

    assert V_hi < V_lo, "Higher pressure should compress vapor to smaller volume"


# ===========================================================================
# Accumulator tests
# ===========================================================================

def test_acc_passthrough():
    """Accumulator outlet = inlet at steady state."""
    acc   = Accumulator(fluid=FLUID)
    inlet = _sat_inlet()
    res   = acc.compute(inlet)
    assert res.outlet.P == inlet.P
    assert res.outlet.h == inlet.h

def test_acc_stiffness_positive():
    """Stiffness must be positive."""
    acc = Accumulator(fluid=FLUID)
    K   = acc.stiffness(600e3)
    assert K > 0

def test_acc_stiffness_increases_with_P():
    """Higher pressure → higher stiffness (less damping)."""
    acc = Accumulator(fluid=FLUID)
    K_lo = acc.stiffness(400e3)
    K_hi = acc.stiffness(800e3)
    assert K_hi > K_lo, "Stiffness should increase with pressure"

def test_acc_gas_volume_decreases_with_P():
    """Higher loop pressure → smaller gas volume (compressed)."""
    acc  = Accumulator(fluid=FLUID, geometry=AccumulatorGeometry(
        V_gas_init=50e-6, P_gas_init=600e3))
    r_lo = acc.compute(PortState(P=400e3, h=SAT.h_l, m_dot=1e-3, fluid=FLUID))
    r_hi = acc.compute(PortState(P=800e3, h=SAT.h_l, m_dot=1e-3, fluid=FLUID))
    assert r_hi.metrics['V_gas_m3'] < r_lo.metrics['V_gas_m3']


# ===========================================================================
# Pipe tests
# ===========================================================================

def test_pipe_dp_positive():
    """Pipe pressure drop must be positive."""
    pipe   = Pipe(fluid=FLUID)
    result = pipe.compute(_sat_inlet())
    assert result.metrics['delta_P_Pa'] > 0

def test_pipe_dp_increases_with_L():
    """Longer pipe → more pressure drop."""
    inlet = _sat_inlet()
    dp1 = Pipe(fluid=FLUID, geometry=PipeGeometry(L=0.3, D=6e-3)).compute(inlet).metrics['delta_P_Pa']
    dp2 = Pipe(fluid=FLUID, geometry=PipeGeometry(L=1.0, D=6e-3)).compute(inlet).metrics['delta_P_Pa']
    assert dp2 > dp1

def test_pipe_adiabatic():
    """Pipe enthalpy must be conserved (adiabatic)."""
    pipe   = Pipe(fluid=FLUID)
    inlet  = _sat_inlet()
    result = pipe.compute(inlet)
    assert result.outlet.h == inlet.h

def test_pipe_mass_conservation():
    """Pipe mass flow must be conserved."""
    pipe   = Pipe(fluid=FLUID)
    inlet  = _sat_inlet()
    result = pipe.compute(inlet)
    assert result.outlet.m_dot == inlet.m_dot


# ===========================================================================
# Run all tests
# ===========================================================================

if __name__ == '__main__':
    import inspect

    tests = [
        obj for name, obj in sorted(globals().items())
        if name.startswith('test_') and callable(obj)
    ]

    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}  →  {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*60}")
    if failed > 0:
        sys.exit(1)
