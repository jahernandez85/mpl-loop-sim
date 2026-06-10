"""
test_pump_accumulator.py — Test Suite for pump.py and accumulator.py
======================================================================
MPL Simulation Library — Phase 6 Tests

Coverage
--------
Pump (curve-based)
  1.  Physical consistency: P_out > P_in, h_out > h_in
  2.  Isentropic limit: η→1 gives minimum enthalpy rise
  3.  Shaft power: W = mdot * ΔP / (ρ * η)
  4.  Energy balance: h_out - h_in = ΔP / (ρ * η)
  5.  Polynomial curve evaluation
  6.  Linear (Leveque) curve evaluation
  7.  NPSH warning triggered below threshold
  8.  Two-phase inlet raises ComponentError
  9.  Negative mdot raises ComponentError
  10. Negative pump curve raises ComponentError

PumpFixed
  11. P_out = P_in + dp_set
  12. h_out = h_in + dp_set / (ρ * η)
  13. W_shaft formula
  14. Two-phase inlet raises ComponentError

AccumulatorHCA
  15. P_sys = P_sat(T_set) from CoolProp
  16. Fluid inventory: V_liquid + V_vapour = V_total
  17. fluid inventory mass balance: x_accu consistent
  18. dP/dT > 0 (pressure rises with temperature)
  19. Adjust setpoint changes pressure
  20. Invalid T_set raises ValueError
  21. x_accu > 1 raises ValueError

AccumulatorPCA
  22. P_sys = P_gas_set
  23. Polytropic gas law: V_gas * P^(1/n) = const
  24. V_liquid + V_gas = V_total
  25. liquid_mass > 0
  26. Isothermal (n=1) compressibility analytical check
  27. V_prefill > V_total raises ValueError
  28. Over-pressurisation raises ValueError (V_gas > V_total)
  29. adjust_setpoint updates P_sys

Integration
  30. Pump + AccumulatorHCA: outlet P equals setpoint after ΔP_pump
  31. Pump operating curve: ΔP monotonically decreasing with mdot (for typical curve)
"""

from __future__ import annotations

import math
import sys
import warnings

import pytest

# ---------------------------------------------------------------------------
# Path setup so tests find the modules in the project root
# ---------------------------------------------------------------------------
sys.path.insert(0, "/mnt/project")
sys.path.insert(0, "/home/claude")

from fluid_properties import FluidState
from base import Port
from pump import Pump, PumpFixed, polynomial_pump_curve, linear_pump_curve
from accumulator import AccumulatorHCA, AccumulatorPCA

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

FLUID = "Acetone"


def make_liquid_inlet(
    P: float = 3.0e5,   # [Pa]
    T: float = 293.15,  # [K]  20 °C
    mdot: float = 0.005,  # [kg/s]
) -> Port:
    """Create a subcooled liquid inlet port for Acetone."""
    state = FluidState.from_PT(fluid=FLUID, P=P, T=T)
    return Port(state=state, mdot=mdot)


def make_two_phase_inlet(
    P: float = 3.0e5,
    x: float = 0.3,
    mdot: float = 0.005,
) -> Port:
    """Create a two-phase inlet port."""
    state = FluidState.from_Px(fluid=FLUID, P=P, x=x)
    return Port(state=state, mdot=mdot)


def default_pump(eta: float = 0.45) -> Pump:
    """Build a typical Pump with a linear curve."""
    curve = linear_pump_curve(dp_zero_flow=40_000.0, b=4e6)
    return Pump(dp_curve=curve, eta=eta, fluid=FLUID)


def default_pump_fixed(dp: float = 20_000.0, eta: float = 0.45) -> PumpFixed:
    return PumpFixed(dp_set=dp, eta=eta, fluid=FLUID)


def default_hca(T_set: float = 293.15) -> AccumulatorHCA:
    return AccumulatorHCA(
        fluid=FLUID, T_set=T_set, V_total=1e-3, x_accu=0.3
    )


def default_pca(P_gas: float = 3.0e5) -> AccumulatorPCA:
    return AccumulatorPCA(
        fluid=FLUID,
        P_gas_set=P_gas,
        V_total=1.0e-3,   # 1 L
        V_prefill=0.8e-3,  # 0.8 L N2 at prefill
        P_prefill=2.0e5,  # 2 bar prefill
        n_polytropic=1.0,
    )


# ===========================================================================
# Pump (curve-based)
# ===========================================================================

class TestPumpPhysics:

    def test_pressure_rises(self):
        """P_out must be greater than P_in."""
        pump = default_pump()
        inlet = make_liquid_inlet()
        outlet = pump.solve_ss(inlet)
        assert outlet.P > inlet.P

    def test_enthalpy_rises(self):
        """h_out > h_in because of irreversible work input."""
        pump = default_pump()
        inlet = make_liquid_inlet()
        outlet = pump.solve_ss(inlet)
        assert outlet.h > inlet.h

    def test_pressure_drop_negative(self):
        """Pump pressure_drop() must be negative (pressure rises)."""
        pump = default_pump()
        inlet = make_liquid_inlet()
        pump.solve_ss(inlet)
        assert pump.pressure_drop() < 0

    def test_enthalpy_rise_formula(self):
        """Δh = ΔP / (ρ_l * η)  — isentropic + irreversibility."""
        eta = 0.45
        pump = default_pump(eta=eta)
        inlet = make_liquid_inlet()
        outlet = pump.solve_ss(inlet)
        dp = pump.dp_pump
        dh_expected = dp / (inlet.rho * eta)
        dh_actual = outlet.h - inlet.h
        assert abs(dh_actual - dh_expected) / dh_expected < 1e-9

    def test_shaft_power_formula(self):
        """W_shaft = mdot * ΔP / (ρ * η)."""
        pump = default_pump()
        inlet = make_liquid_inlet()
        pump.solve_ss(inlet)
        W_expected = inlet.mdot * pump.dp_pump / (inlet.rho * pump._last_eta)
        assert abs(pump.W_shaft - W_expected) / W_expected < 1e-9

    def test_higher_efficiency_lower_enthalpy_rise(self):
        """With η→1 the enthalpy rise is minimal (least work wasted)."""
        inlet = make_liquid_inlet()
        curve = linear_pump_curve(40_000.0, 4e6)

        pump_low = Pump(dp_curve=curve, eta=0.30, fluid=FLUID)
        pump_hi = Pump(dp_curve=curve, eta=0.80, fluid=FLUID)

        out_low = pump_low.solve_ss(inlet)
        out_hi = pump_hi.solve_ss(inlet)

        assert out_low.h > out_hi.h, "Lower η should give higher enthalpy rise."

    def test_mdot_unchanged(self):
        """Mass flow rate must be conserved through the pump."""
        pump = default_pump()
        inlet = make_liquid_inlet(mdot=0.008)
        outlet = pump.solve_ss(inlet)
        assert outlet.mdot == pytest.approx(0.008)

    def test_heat_transfer_zero(self):
        """Adiabatic pump: heat_transfer() == 0."""
        pump = default_pump()
        pump.solve_ss(make_liquid_inlet())
        assert pump.heat_transfer() == 0.0


class TestPumpCurves:

    def test_polynomial_curve_zero_flow(self):
        """At zero flow the polynomial curve returns the constant term."""
        coeffs = [30_000.0, -5e6, 0.0]
        curve = polynomial_pump_curve(coeffs)
        assert curve(0.0) == pytest.approx(30_000.0)

    def test_polynomial_curve_known_value(self):
        """ΔP = 30000 - 5e6*0.005 = 5000 Pa."""
        curve = polynomial_pump_curve([30_000.0, -5e6])
        assert curve(0.005) == pytest.approx(5_000.0, rel=1e-9)

    def test_linear_curve_zero_flow(self):
        """ΔP at mdot=0 equals dp_zero_flow."""
        curve = linear_pump_curve(dp_zero_flow=40_000.0, b=4e6)
        assert curve(0.0) == pytest.approx(40_000.0)

    def test_linear_curve_slope(self):
        """ΔP decreases linearly with mdot."""
        b = 4e6
        curve = linear_pump_curve(40_000.0, b)
        m1, m2 = 0.001, 0.003
        assert (curve(m1) - curve(m2)) == pytest.approx(b * (m2 - m1), rel=1e-9)

    def test_operating_curve_length(self):
        """operating_point_curve returns same length as input."""
        pump = default_pump()
        mdot_range = [0.001, 0.003, 0.005, 0.007]
        m_out, dp_out = pump.operating_point_curve(mdot_range)
        assert len(m_out) == len(mdot_range)
        assert len(dp_out) == len(mdot_range)

    def test_operating_curve_decreasing(self):
        """Typical pump curve: ΔP decreasing with mdot."""
        pump = default_pump()
        mdot_range = [0.001, 0.003, 0.005, 0.007]
        _, dp_out = pump.operating_point_curve(mdot_range)
        assert dp_out[0] > dp_out[-1]


class TestPumpGuards:

    def test_negative_mdot_raises(self):
        pump = default_pump()
        inlet = make_liquid_inlet(mdot=-0.005)
        with pytest.raises(Exception):
            pump.solve_ss(inlet)

    def test_two_phase_inlet_raises(self):
        pump = default_pump()
        inlet = make_two_phase_inlet(x=0.3)
        with pytest.raises(Exception):
            pump.solve_ss(inlet)

    def test_negative_curve_raises(self):
        """A pump curve returning negative ΔP should raise ComponentError."""
        curve = linear_pump_curve(dp_zero_flow=1_000.0, b=1e9)
        pump = Pump(dp_curve=curve, eta=0.45, fluid=FLUID)
        inlet = make_liquid_inlet(mdot=0.005)
        with pytest.raises(Exception):
            pump.solve_ss(inlet)

    def test_npsh_warning(self):
        """NPSH_a < NPSH_r triggers RuntimeWarning."""
        curve = linear_pump_curve(40_000.0, 4e6)
        # Force NPSH check to fail by setting very high NPSH_required
        pump = Pump(dp_curve=curve, eta=0.45, fluid=FLUID, npsh_required=1000.0)
        inlet = make_liquid_inlet()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pump.solve_ss(inlet)
            runtime_warnings = [x for x in w if issubclass(x.category, RuntimeWarning)]
            assert len(runtime_warnings) >= 1

    def test_invalid_eta_raises(self):
        curve = linear_pump_curve(40_000.0, 4e6)
        with pytest.raises((ValueError, Exception)):
            Pump(dp_curve=curve, eta=1.5, fluid=FLUID)

    def test_eta_zero_raises(self):
        curve = linear_pump_curve(40_000.0, 4e6)
        with pytest.raises((ValueError, Exception)):
            Pump(dp_curve=curve, eta=0.0, fluid=FLUID)


# ===========================================================================
# PumpFixed
# ===========================================================================

class TestPumpFixed:

    def test_pressure_rise(self):
        pf = default_pump_fixed(dp=25_000.0)
        inlet = make_liquid_inlet()
        outlet = pf.solve_ss(inlet)
        assert outlet.P == pytest.approx(inlet.P + 25_000.0, rel=1e-9)

    def test_enthalpy_rise(self):
        dp, eta = 25_000.0, 0.50
        pf = default_pump_fixed(dp=dp, eta=eta)
        inlet = make_liquid_inlet()
        outlet = pf.solve_ss(inlet)
        dh_expected = dp / (inlet.rho * eta)
        assert (outlet.h - inlet.h) == pytest.approx(dh_expected, rel=1e-9)

    def test_shaft_power(self):
        dp, eta = 20_000.0, 0.45
        pf = default_pump_fixed(dp=dp, eta=eta)
        inlet = make_liquid_inlet(mdot=0.005)
        pf.solve_ss(inlet)
        W_expected = 0.005 * dp / (inlet.rho * eta)
        assert pf.W_shaft == pytest.approx(W_expected, rel=1e-9)

    def test_two_phase_raises(self):
        pf = default_pump_fixed()
        with pytest.raises(Exception):
            pf.solve_ss(make_two_phase_inlet(x=0.2))

    def test_pressure_drop_negative(self):
        pf = default_pump_fixed()
        pf.solve_ss(make_liquid_inlet())
        assert pf.pressure_drop() < 0

    def test_heat_transfer_zero(self):
        pf = default_pump_fixed()
        pf.solve_ss(make_liquid_inlet())
        assert pf.heat_transfer() == 0.0

    def test_negative_dp_raises(self):
        with pytest.raises(ValueError):
            PumpFixed(dp_set=-1000.0, eta=0.45, fluid=FLUID)


# ===========================================================================
# AccumulatorHCA
# ===========================================================================

class TestAccumulatorHCA:

    def test_pressure_from_saturation(self):
        """P_sys = P_sat(T_set) from CoolProp."""
        T_set = 293.15  # 20 °C
        hca = default_hca(T_set=T_set)
        P_sys = hca.set_pressure()
        import CoolProp.CoolProp as CP
        P_ref = float(CP.PropsSI("P", "T", T_set, "Q", 0, "Acetone"))
        assert P_sys == pytest.approx(P_ref, rel=1e-6)

    def test_pressure_property_alias(self):
        hca = default_hca()
        assert hca.P_sys == hca.set_pressure()

    def test_volume_conservation(self):
        """V_liquid + V_vapour = V_total."""
        hca = default_hca()
        inv = hca.fluid_inventory()
        assert inv["V_liquid"] + inv["V_vapour"] == pytest.approx(
            hca.V_total, rel=1e-9
        )

    def test_quality_consistency(self):
        """Computed x_accu must match the prescribed quality."""
        x_set = 0.25
        hca = AccumulatorHCA(fluid=FLUID, T_set=293.15, V_total=1e-3, x_accu=x_set)
        inv = hca.fluid_inventory()
        m_v = inv["m_vapour"]
        m_total = inv["m_total"]
        x_check = m_v / m_total
        assert x_check == pytest.approx(x_set, rel=1e-6)

    def test_dP_dT_positive(self):
        """dP/dT > 0: pressure rises with temperature for any normal fluid."""
        hca = default_hca()
        assert hca.dP_dT() > 0

    def test_higher_T_higher_P(self):
        hca_lo = default_hca(T_set=283.15)
        hca_hi = default_hca(T_set=303.15)
        assert hca_hi.P_sys > hca_lo.P_sys

    def test_adjust_setpoint(self):
        hca = default_hca(T_set=290.0)
        P_before = hca.P_sys
        hca.adjust_setpoint(300.0)
        assert hca.P_sys > P_before
        assert hca.T_set == pytest.approx(300.0)

    def test_invalid_T_raises(self):
        with pytest.raises(ValueError):
            AccumulatorHCA(fluid=FLUID, T_set=-10.0, V_total=1e-3)

    def test_invalid_x_raises(self):
        with pytest.raises(ValueError):
            AccumulatorHCA(fluid=FLUID, T_set=293.15, V_total=1e-3, x_accu=1.5)

    def test_liquid_mass_positive(self):
        hca = default_hca()
        assert hca.liquid_mass() > 0.0

    def test_repr_contains_bar(self):
        hca = default_hca()
        r = repr(hca)
        assert "bar" in r

    def test_x_zero_all_liquid(self):
        """x_accu=0 → all liquid, V_vapour≈0."""
        hca = AccumulatorHCA(fluid=FLUID, T_set=293.15, V_total=1e-3, x_accu=0.0)
        inv = hca.fluid_inventory()
        assert inv["V_vapour"] < 1e-12

    def test_x_one_all_vapour(self):
        """x_accu=1 → all vapour, V_liquid≈0."""
        hca = AccumulatorHCA(fluid=FLUID, T_set=293.15, V_total=1e-3, x_accu=1.0)
        inv = hca.fluid_inventory()
        assert inv["V_liquid"] < 1e-12


# ===========================================================================
# AccumulatorPCA
# ===========================================================================

class TestAccumulatorPCA:

    def test_pressure_equals_gas_setpoint(self):
        pca = default_pca(P_gas=3.5e5)
        assert pca.set_pressure() == pytest.approx(3.5e5)

    def test_P_sys_property(self):
        pca = default_pca()
        assert pca.P_sys == pca.set_pressure()

    def test_polytropic_gas_law_isothermal(self):
        """For n=1: P*V = const  → V_gas = V_prefill * P_prefill / P."""
        P_prefill = 2.0e5
        V_prefill = 0.8e-3
        P_gas = 3.0e5
        pca = AccumulatorPCA(
            fluid=FLUID,
            P_gas_set=P_gas,
            V_total=1.0e-3,
            V_prefill=V_prefill,
            P_prefill=P_prefill,
            n_polytropic=1.0,
        )
        V_gas_expected = V_prefill * P_prefill / P_gas
        assert pca.gas_volume() == pytest.approx(V_gas_expected, rel=1e-9)

    def test_volume_conservation(self):
        """V_gas + V_liquid = V_total."""
        pca = default_pca()
        assert pca.gas_volume() + pca.liquid_volume() == pytest.approx(
            pca.V_total, rel=1e-9
        )

    def test_liquid_mass_positive(self):
        pca = default_pca()
        assert pca.liquid_mass() > 0.0

    def test_higher_pressure_less_gas_volume(self):
        """Higher operating pressure compresses gas → less gas, more liquid."""
        P_lo, P_hi = 2.5e5, 4.0e5
        pca_lo = AccumulatorPCA(
            fluid=FLUID, P_gas_set=P_lo,
            V_total=1e-3, V_prefill=0.8e-3, P_prefill=2.0e5
        )
        pca_hi = AccumulatorPCA(
            fluid=FLUID, P_gas_set=P_hi,
            V_total=1e-3, V_prefill=0.8e-3, P_prefill=2.0e5
        )
        assert pca_hi.gas_volume() < pca_lo.gas_volume()
        assert pca_hi.liquid_volume() > pca_lo.liquid_volume()

    def test_isothermal_compressibility(self):
        """
        For n=1: C_eff = V_prefill * P_prefill / P²
        Verify analytically.
        """
        V_prefill = 0.8e-3
        P_prefill = 2.0e5
        P = 3.0e5
        pca = AccumulatorPCA(
            fluid=FLUID, P_gas_set=P,
            V_total=1.0e-3, V_prefill=V_prefill, P_prefill=P_prefill,
            n_polytropic=1.0,
        )
        C_expected = V_prefill * P_prefill / P**2
        C_actual = pca.effective_compressibility()
        assert C_actual == pytest.approx(C_expected, rel=1e-6)

    def test_compressibility_positive(self):
        """Compressibility must always be positive."""
        pca = default_pca()
        assert pca.effective_compressibility() > 0.0

    def test_adjust_setpoint(self):
        pca = default_pca(P_gas=3.0e5)
        pca.adjust_setpoint(4.0e5)
        assert pca.P_sys == pytest.approx(4.0e5)

    def test_V_prefill_greater_than_total_raises(self):
        with pytest.raises(ValueError):
            AccumulatorPCA(
                fluid=FLUID, P_gas_set=3e5,
                V_total=0.5e-3, V_prefill=1.0e-3, P_prefill=2e5,
            )

    def test_negative_P_gas_raises(self):
        with pytest.raises(ValueError):
            AccumulatorPCA(
                fluid=FLUID, P_gas_set=-1e5,
                V_total=1e-3, V_prefill=0.8e-3, P_prefill=2e5,
            )

    def test_over_extension_raises(self):
        """P much lower than prefill → gas would overflow vessel."""
        pca = AccumulatorPCA(
            fluid=FLUID, P_gas_set=3e5,
            V_total=1e-3, V_prefill=0.8e-3, P_prefill=2e5,
        )
        # At P = 0.001 * P_prefill the gas volume would be 200 × V_prefill >> V_total
        with pytest.raises((ValueError, Exception)):
            pca.gas_volume(P=0.001 * pca.P_prefill)

    def test_fluid_inventory_keys(self):
        pca = default_pca()
        inv = pca.fluid_inventory()
        for key in ("P_sys", "V_gas", "V_liquid", "rho_l", "m_liquid"):
            assert key in inv

    def test_repr_contains_bar(self):
        pca = default_pca()
        assert "bar" in repr(pca)

    def test_volume_at_pressure(self):
        """volume_at_pressure(P) matches liquid_volume(P)."""
        pca = default_pca()
        P_test = 3.5e5
        assert pca.volume_at_pressure(P_test) == pytest.approx(
            pca.liquid_volume(P_test), rel=1e-9
        )


# ===========================================================================
# Integration tests
# ===========================================================================

class TestIntegration:

    def test_pump_outlet_enters_loop_at_correct_pressure(self):
        """
        Pump ΔP_pump is consistent with the HCA system pressure.

        Scenario: HCA sets P_sys; pump must raise P by ΔP_pump so that
        after loop losses the inlet returns to P_sys.
        At minimal check: P_out_pump = P_in_pump + ΔP_pump.
        """
        hca = default_hca(T_set=293.15)
        P_sys = hca.P_sys
        # Liquid enters pump at system pressure with 5 K subcooling
        inlet = make_liquid_inlet(P=P_sys, T=288.15, mdot=0.005)
        pump = default_pump()
        outlet = pump.solve_ss(inlet)
        assert outlet.P == pytest.approx(inlet.P + pump.dp_pump, rel=1e-9)

    def test_pump_curve_monotone_for_typical_parameters(self):
        """Typical linear curve: ΔP decreases as mdot increases."""
        pump = default_pump()
        mdots = [0.001 * i for i in range(1, 9)]
        _, dps = pump.operating_point_curve(mdots)
        for i in range(len(dps) - 1):
            if not math.isnan(dps[i]) and not math.isnan(dps[i + 1]):
                assert dps[i] >= dps[i + 1]

    def test_pumpfixed_hca_pressure_balance(self):
        """
        PumpFixed raises P by dp_set; the outlet can supply HCA setpoint.
        """
        hca = default_hca(T_set=293.15)
        P_sys = hca.P_sys
        dp = 15_000.0
        pf = default_pump_fixed(dp=dp)
        inlet = make_liquid_inlet(P=P_sys, T=288.15)
        outlet = pf.solve_ss(inlet)
        assert outlet.P == pytest.approx(P_sys + dp, rel=1e-9)
