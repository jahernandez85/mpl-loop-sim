"""
tests/test_fluid_properties.py
================================
Unit tests for mpl.fluid_properties.

Run with:
    python -m pytest tests/test_fluid_properties.py -v
"""

import math
import pytest
import sys
sys.path.insert(0, "/mpl")

from mpl.fluid_properties import FluidState, Phase, resolve_fluid_name, SUPPORTED_FLUIDS


# ---------------------------------------------------------------------------
# Fixtures: one state per fluid, covering all three phases
# ---------------------------------------------------------------------------

FLUIDS = ["Acetone", "R1233ZDE", "R1234YF"]

def make_state(fluid, phase_label):
    """Return a FluidState for the given fluid and phase."""
    if phase_label == "liquid":
        # Subcooled: 5 K below T_sat at 3 bar
        return FluidState.from_Px(fluid, P=3e5, x=0.0).with_enthalpy(
            FluidState.from_Px(fluid, P=3e5, x=0.0).h - 5000
        )
    elif phase_label == "two_phase":
        return FluidState.from_Px(fluid, P=3e5, x=0.5)
    elif phase_label == "vapor":
        return FluidState.from_Px(fluid, P=3e5, x=1.0).with_enthalpy(
            FluidState.from_Px(fluid, P=3e5, x=1.0).h + 10000
        )


# ---------------------------------------------------------------------------
# 1. Fluid name resolution
# ---------------------------------------------------------------------------

class TestFluidResolution:
    def test_aliases_resolve(self):
        assert resolve_fluid_name("acetone")   == "Acetone"
        assert resolve_fluid_name("r1233zde")  == "R1233ZDE"
        assert resolve_fluid_name("R1234YF")   == "R1234YF"
        assert resolve_fluid_name("r134a")     == "R134a"

    def test_hyphen_underscore_insensitive(self):
        assert resolve_fluid_name("R1233-ZDE") == "R1233ZDE"
        assert resolve_fluid_name("R_1234_YF") == "R1234YF"

    def test_unknown_fluid_raises(self):
        with pytest.raises(Exception):
            resolve_fluid_name("NotAFluid")


# ---------------------------------------------------------------------------
# 2. Constructors
# ---------------------------------------------------------------------------

class TestConstructors:
    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_from_Ph(self, fluid):
        fs = FluidState.from_Px(fluid, P=3e5, x=0.5)
        fs2 = FluidState.from_Ph(fluid, P=fs.P, h=fs.h)
        assert abs(fs2.x - 0.5) < 1e-6

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_from_PT_liquid(self, fluid):
        # T well below T_sat at 1 bar → should be liquid
        import CoolProp.CoolProp as CP
        T_sat = CP.PropsSI("T", "P", 1e5, "Q", 0, fluid)
        T_sub = T_sat - 10
        fs = FluidState.from_PT(fluid, P=1e5, T=T_sub)
        assert fs.phase == Phase.LIQUID

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_from_Px_boundaries(self, fluid):
        fs_l = FluidState.from_Px(fluid, P=2e5, x=0.0)
        fs_v = FluidState.from_Px(fluid, P=2e5, x=1.0)
        # sat liquid enthalpy should equal h_l
        assert abs(fs_l.h - fs_l.h_l) < 1.0   # < 1 J/kg tolerance
        assert abs(fs_v.h - fs_v.h_v) < 1.0

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_from_Tsat(self, fluid):
        fs = FluidState.from_Tsat(fluid, T_sat_C=30.0, x=0.5)
        assert abs(fs.T_sat_C - 30.0) < 0.1   # within 0.1 °C

    def test_from_Px_invalid_quality(self):
        with pytest.raises(ValueError):
            FluidState.from_Px("Acetone", P=2e5, x=1.5)


# ---------------------------------------------------------------------------
# 3. Phase detection
# ---------------------------------------------------------------------------

class TestPhaseDetection:
    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_liquid_phase(self, fluid):
        fs = make_state(fluid, "liquid")
        assert fs.phase == Phase.LIQUID
        assert fs.is_liquid
        assert not fs.is_two_phase
        assert math.isnan(fs.x)
        assert math.isnan(fs.alpha)

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_two_phase(self, fluid):
        fs = make_state(fluid, "two_phase")
        assert fs.phase == Phase.TWO_PHASE
        assert fs.is_two_phase
        assert abs(fs.x - 0.5) < 1e-6
        assert 0 < fs.alpha < 1

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_vapor_phase(self, fluid):
        fs = make_state(fluid, "vapor")
        assert fs.phase == Phase.VAPOR
        assert fs.is_vapor
        assert math.isnan(fs.x)


# ---------------------------------------------------------------------------
# 4. Thermodynamic consistency
# ---------------------------------------------------------------------------

class TestThermodynamicConsistency:
    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_hem_density(self, fluid):
        """HEM: 1/ρ = x/ρ_v + (1-x)/ρ_l  (Dogan 1983, Eq. 4)"""
        fs = FluidState.from_Px(fluid, P=3e5, x=0.4)
        rho_expected = 1.0 / (fs.x / fs.rho_v + (1 - fs.x) / fs.rho_l)
        assert abs(fs.rho - rho_expected) / rho_expected < 1e-9

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_void_fraction_bounds(self, fluid):
        for x in [0.01, 0.1, 0.5, 0.9, 0.99]:
            fs = FluidState.from_Px(fluid, P=3e5, x=x)
            assert 0 < fs.alpha < 1

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_void_fraction_increases_with_quality(self, fluid):
        fs1 = FluidState.from_Px(fluid, P=3e5, x=0.2)
        fs2 = FluidState.from_Px(fluid, P=3e5, x=0.8)
        assert fs2.alpha > fs1.alpha

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_latent_heat_positive(self, fluid):
        fs = FluidState.from_Px(fluid, P=2e5, x=0.5)
        assert fs.h_fg > 0

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_saturation_temperature_increases_with_pressure(self, fluid):
        fs_lo = FluidState.from_Px(fluid, P=1e5, x=0.0)
        fs_hi = FluidState.from_Px(fluid, P=5e5, x=0.0)
        assert fs_hi.T_sat > fs_lo.T_sat

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_cicchitti_viscosity(self, fluid):
        """μ_tp = x·μ_v + (1-x)·μ_l  (Cicchitti) — only when both phases available"""
        fs = FluidState.from_Px(fluid, P=3e5, x=0.6)
        if math.isnan(fs.mu_l) or math.isnan(fs.mu_v):
            pytest.skip(f"{fluid}: transport props not available in CoolProp")
        expected = fs.x * fs.mu_v + (1 - fs.x) * fs.mu_l
        assert abs(fs.mu_tp - expected) / expected < 1e-9

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_reduced_pressure(self, fluid):
        fs = FluidState.from_Px(fluid, P=3e5, x=0.5)
        assert 0 < fs.P_red < 1  # below critical for all test fluids at 3 bar


# ---------------------------------------------------------------------------
# 5. Helper methods
# ---------------------------------------------------------------------------

class TestHelpers:
    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_subcooling_positive_for_liquid(self, fluid):
        fs = make_state(fluid, "liquid")
        assert fs.subcooling() > 0

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_superheating_positive_for_vapor(self, fluid):
        fs = make_state(fluid, "vapor")
        assert fs.superheating() > 0

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_with_enthalpy_same_pressure(self, fluid):
        fs = FluidState.from_Px(fluid, P=3e5, x=0.5)
        h_new = fs.h_v + 5000
        fs2 = fs.with_enthalpy(h_new)
        assert fs2.P == fs.P
        assert fs2.h == h_new
        assert fs2.is_vapor

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_with_pressure_same_enthalpy(self, fluid):
        fs = FluidState.from_Px(fluid, P=3e5, x=0.5)
        fs2 = fs.with_pressure(4e5)
        assert fs2.h == fs.h
        assert fs2.P == 4e5

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_T_C_property(self, fluid):
        fs = FluidState.from_Px(fluid, P=3e5, x=0.5)
        assert abs(fs.T_C - (fs.T - 273.15)) < 1e-9

    @pytest.mark.parametrize("fluid", FLUIDS)
    def test_summary_runs(self, fluid):
        for phase in ["liquid", "two_phase", "vapor"]:
            fs = make_state(fluid, phase)
            s = fs.summary()
            assert fluid in s or fluid.lower() in s.lower()


# ---------------------------------------------------------------------------
# 6. Numerical values spot-check (Acetone at 1 atm)
# ---------------------------------------------------------------------------

class TestAcetoneAtmospheric:
    """
    Reference: CoolProp for Acetone at 1 atm.
    T_sat ≈ 56.1 °C, h_fg ≈ 501.4 kJ/kg
    """
    def test_tsat_acetone_1bar(self):
        fs = FluidState.from_Px("Acetone", P=101325, x=0.0)
        assert abs(fs.T_sat_C - 56.1) < 0.2   # within 0.2 °C

    def test_hfg_acetone_1bar(self):
        fs = FluidState.from_Px("Acetone", P=101325, x=0.5)
        assert abs(fs.h_fg / 1e3 - 501.4) < 1.0  # within 1 kJ/kg

    def test_rho_liquid_reasonable(self):
        fs = FluidState.from_Px("Acetone", P=101325, x=0.0)
        # Acetone liquid density ~720 kg/m³ at boiling point
        assert 650 < fs.rho_l < 800


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
