"""
tests/test_components/test_base_pipe.py
=======================================
pytest test suite for components/base.py and components/pipe.py.

Coverage
--------
base.py
  - Port construction and property delegation
  - Port.__repr__
  - Orientation constants and validation
  - Component abstract enforcement
  - ComponentError

pipe.py
  - PipeGeometry construction, validation, derived properties
  - Pipe construction with defaults and explicit correlations
  - Single-phase adiabatic pipe: pressure drop, enthalpy conservation
  - Single-phase pipe with heat loss
  - Two-phase pipe: friction + gravity ΔP
  - Vertical pipe: gravity contribution sign
  - Physical consistency: P_out < P_in, h_out = h_in (adiabatic)
  - Edge cases: zero Q_loss, negative mdot raises, bad orientation raises
  - Summary string formatting

Test strategy
-------------
All tests use duck-typed FluidState stubs so the suite runs without CoolProp.
The stubs expose exactly the attributes consumed by correlations.py and pipe.py.
Where CoolProp IS available, a separate section runs integration checks.

Run with:
    pytest tests/test_components/test_base_pipe.py -v
"""

from __future__ import annotations

import math
import sys
import os
from dataclasses import dataclass

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running from repo root without installation
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from base import Port, Component, Orientation, ComponentError
from pipe import Pipe, PipeGeometry, _SimplePHState


# ---------------------------------------------------------------------------
# Shared stub FluidState
# ---------------------------------------------------------------------------

@dataclass
class StubState:
    """
    Duck-typed FluidState stub that satisfies all attribute checks in
    base.py, correlations.py, and pipe.py.
    """
    phase: str   = "liquid"
    P:     float = 5.0e5
    h:     float = 2.5e5
    T:     float = 310.0
    rho:   float = 900.0
    x:     float = 0.0

    # For two-phase correlations
    rho_l: float = 900.0
    rho_v: float = 5.0
    mu_l:  float = 2.0e-4
    mu_v:  float = 1.0e-5
    mu_tp: float = 1.5e-4
    k_l:   float = 0.08
    k_v:   float = 0.015
    Pr_l:  float = 3.5
    Pr_v:  float = 1.1
    h_fg:  float = 300_000.0
    h_l:   float = 1.0e5
    sigma: float = 0.010
    P_red: float = 0.05
    T_sat: float = 310.0


@dataclass
class StubStateTP(StubState):
    """Two-phase version of StubState."""
    phase: str  = "two-phase"
    x:     float = 0.3
    rho:   float = 30.0   # HEM mixture density at x=0.3


# ---------------------------------------------------------------------------
# Stub ΔP correlation (constant gradient, no CoolProp dependency)
# ---------------------------------------------------------------------------

class ConstDP:
    """Returns a flat dP/dz = value Pa/m regardless of conditions."""
    def __init__(self, value: float = 500.0):
        self.value = value

    def __call__(self, state, G, D_h, **kwargs) -> float:
        return self.value


# ===========================================================================
# ── TESTS: base.py
# ===========================================================================

class TestPort:
    """Tests for the Port dataclass."""

    def _make_port(self, **kwargs) -> Port:
        s = StubState(**kwargs)
        return Port(state=s, mdot=0.05)

    def test_construction(self):
        port = self._make_port()
        assert port.mdot == pytest.approx(0.05)

    def test_property_delegation_P(self):
        port = self._make_port(P=4.0e5)
        assert port.P == pytest.approx(4.0e5)

    def test_property_delegation_h(self):
        port = self._make_port(h=3.0e5)
        assert port.h == pytest.approx(3.0e5)

    def test_property_delegation_T(self):
        port = self._make_port(T=320.0)
        assert port.T == pytest.approx(320.0)

    def test_property_delegation_rho(self):
        port = self._make_port(rho=850.0)
        assert port.rho == pytest.approx(850.0)

    def test_property_delegation_x(self):
        port = self._make_port(x=0.0)
        assert port.x == pytest.approx(0.0)

    def test_property_delegation_phase(self):
        port = self._make_port(phase="liquid")
        assert port.phase == "liquid"

    def test_G_raises_attribute_error(self):
        """Port.G should raise AttributeError — area not known at Port level."""
        port = self._make_port()
        with pytest.raises(AttributeError):
            _ = port.G

    def test_repr_contains_key_fields(self):
        port = self._make_port()
        r = repr(port)
        assert "Port(" in r
        assert "mdot" in r

    def test_two_phase_port(self):
        port = Port(state=StubStateTP(), mdot=0.02)
        assert port.phase == "two-phase"
        assert port.x == pytest.approx(0.3)


class TestOrientation:
    """Tests for Orientation constants and validation."""

    def test_constants_exist(self):
        assert Orientation.HORIZONTAL    == "horizontal"
        assert Orientation.VERTICAL_UP   == "vertical_up"
        assert Orientation.VERTICAL_DOWN == "vertical_down"

    def test_validate_valid(self):
        for val in ("horizontal", "vertical_up", "vertical_down"):
            assert Orientation.validate(val) == val

    def test_validate_invalid(self):
        with pytest.raises(ValueError):
            Orientation.validate("diagonal")

    def test_validate_case_sensitive(self):
        with pytest.raises(ValueError):
            Orientation.validate("Horizontal")


class TestComponentAbstract:
    """Tests for the Component abstract base class."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Component()  # type: ignore

    def test_concrete_subclass_requires_all_methods(self):
        """A subclass missing one abstract method should still be abstract."""
        class Incomplete(Component):
            def solve_ss(self, inlet): ...
            def pressure_drop(self): ...
            # heat_transfer is missing

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore

    def test_fully_concrete_subclass(self):
        class Dummy(Component):
            def solve_ss(self, inlet):
                self.inlet  = inlet
                self.outlet = inlet
                return inlet

            def pressure_drop(self) -> float:
                return 0.0

            def heat_transfer(self) -> float:
                return 0.0

        d = Dummy(name="dummy")
        assert d.name == "dummy"
        assert d.inlet is None
        assert d.outlet is None

    def test_component_error(self):
        class Dummy(Component):
            def solve_ss(self, inlet): ...
            def pressure_drop(self): return 0.0
            def heat_transfer(self): return 0.0

        d = Dummy(name="MyComp")
        err = ComponentError(d, "something went wrong")
        assert "MyComp" in str(err)
        assert "something went wrong" in str(err)
        assert err.component is d

    def test_dP_alias(self):
        class Dummy(Component):
            def solve_ss(self, i): ...
            def pressure_drop(self): return 42.0
            def heat_transfer(self): return 0.0

        d = Dummy()
        assert d.dP == 42.0

    def test_Q_alias(self):
        class Dummy(Component):
            def solve_ss(self, i): ...
            def pressure_drop(self): return 0.0
            def heat_transfer(self): return -100.0

        d = Dummy()
        assert d.Q == -100.0


# ===========================================================================
# ── TESTS: PipeGeometry
# ===========================================================================

class TestPipeGeometry:
    """Tests for PipeGeometry construction and derived properties."""

    def test_basic_construction(self):
        g = PipeGeometry(D_i=0.01, L=1.0)
        assert g.D_i == pytest.approx(0.01)
        assert g.L   == pytest.approx(1.0)
        assert g.roughness == pytest.approx(1.5e-6)
        assert g.orientation == "horizontal"
        assert g.n_passes == 1

    def test_derived_A_c(self):
        g = PipeGeometry(D_i=0.01, L=1.0)
        expected = math.pi * 0.01**2 / 4.0
        assert g.A_c == pytest.approx(expected, rel=1e-10)

    def test_derived_P_wet(self):
        g = PipeGeometry(D_i=0.01, L=1.0)
        assert g.P_wet == pytest.approx(math.pi * 0.01, rel=1e-10)

    def test_derived_D_h(self):
        g = PipeGeometry(D_i=0.01, L=1.0)
        assert g.D_h == pytest.approx(0.01)

    def test_derived_V(self):
        g = PipeGeometry(D_i=0.01, L=1.0)
        expected = math.pi * 0.01**2 / 4.0 * 1.0
        assert g.V == pytest.approx(expected, rel=1e-10)

    def test_V_with_n_passes(self):
        g = PipeGeometry(D_i=0.01, L=1.0, n_passes=4)
        expected = math.pi * 0.01**2 / 4.0 * 1.0 * 4
        assert g.V == pytest.approx(expected, rel=1e-10)

    def test_invalid_D_i(self):
        with pytest.raises(ValueError):
            PipeGeometry(D_i=0.0, L=1.0)

    def test_invalid_L(self):
        with pytest.raises(ValueError):
            PipeGeometry(D_i=0.01, L=-1.0)

    def test_invalid_roughness(self):
        with pytest.raises(ValueError):
            PipeGeometry(D_i=0.01, L=1.0, roughness=-1e-6)

    def test_invalid_n_passes(self):
        with pytest.raises(ValueError):
            PipeGeometry(D_i=0.01, L=1.0, n_passes=0)

    def test_invalid_orientation(self):
        with pytest.raises(ValueError):
            PipeGeometry(D_i=0.01, L=1.0, orientation="diagonal")

    @pytest.mark.parametrize("ori", ["horizontal", "vertical_up", "vertical_down"])
    def test_valid_orientations(self, ori):
        g = PipeGeometry(D_i=0.01, L=1.0, orientation=ori)
        assert g.orientation == ori


# ===========================================================================
# ── TESTS: Pipe (with stub correlations, no CoolProp)
# ===========================================================================

class TestPipeAdiabatic:
    """Single-phase adiabatic pipe tests."""

    def _make_pipe(self, D_i=0.01, L=1.0, Q_loss=0.0,
                   orientation="horizontal", dp_val=500.0):
        geom = PipeGeometry(D_i=D_i, L=L, orientation=orientation)
        return Pipe(
            geometry=geom,
            Q_loss=Q_loss,
            dp_correlation_sp=ConstDP(dp_val),
            dp_correlation_tp=ConstDP(dp_val),
            name="TestPipe",
        )

    def _liquid_port(self, P=5e5, h=2.5e5, mdot=0.05):
        return Port(state=StubState(P=P, h=h), mdot=mdot)

    def test_P_decreases(self):
        pipe = self._make_pipe(dp_val=500.0, L=1.0)
        port_in  = self._liquid_port()
        port_out = pipe.solve_ss(port_in)
        assert port_out.P < port_in.P

    def test_friction_dp_equals_dPdz_times_L(self):
        dp_val = 800.0
        L      = 2.0
        pipe   = self._make_pipe(dp_val=dp_val, L=L)
        port_in  = self._liquid_port()
        pipe.solve_ss(port_in)
        assert pipe.dP_friction == pytest.approx(dp_val * L, rel=1e-10)

    def test_h_conserved_adiabatic(self):
        """For Q_loss=0 the outlet enthalpy must equal inlet enthalpy."""
        pipe = self._make_pipe(Q_loss=0.0)
        port_in  = self._liquid_port(h=3e5)
        port_out = pipe.solve_ss(port_in)
        # _SimplePHState stores h directly
        assert port_out.h == pytest.approx(3e5, rel=1e-10)

    def test_mdot_conserved(self):
        """Mass flow rate must be unchanged (incompressible SS pipe)."""
        pipe = self._make_pipe()
        port_in  = self._liquid_port(mdot=0.03)
        port_out = pipe.solve_ss(port_in)
        assert port_out.mdot == pytest.approx(0.03)

    def test_gravity_horizontal_zero(self):
        pipe = self._make_pipe(orientation="horizontal")
        self._liquid_port()
        port_in = self._liquid_port()
        pipe.solve_ss(port_in)
        assert pipe.dP_gravity == pytest.approx(0.0, abs=1e-10)

    def test_gravity_vertical_up_positive(self):
        """Vertical-up pipe: gravity adds to pressure drop."""
        pipe = self._make_pipe(orientation="vertical_up", L=1.0)
        port_in = self._liquid_port()
        pipe.solve_ss(port_in)
        # ρ = 900, g = 9.806, L = 1.0 → ~8825 Pa
        expected = 900.0 * 9.806 * 1.0
        assert pipe.dP_gravity == pytest.approx(expected, rel=1e-3)

    def test_gravity_vertical_down_negative(self):
        """Vertical-down pipe: gravity reduces pressure drop (flow aided)."""
        pipe = self._make_pipe(orientation="vertical_down", L=1.0)
        port_in = self._liquid_port()
        pipe.solve_ss(port_in)
        expected = -900.0 * 9.806 * 1.0
        assert pipe.dP_gravity == pytest.approx(expected, rel=1e-3)

    def test_total_dp_components(self):
        """ΔP_total = ΔP_friction + ΔP_gravity + ΔP_accel."""
        pipe = self._make_pipe(orientation="horizontal")
        port_in = self._liquid_port()
        pipe.solve_ss(port_in)
        total = pipe.dP_friction + pipe.dP_gravity + pipe.dP_accel
        assert pipe.pressure_drop() == pytest.approx(total, rel=1e-10)

    def test_P_out_equals_P_in_minus_dP(self):
        pipe = self._make_pipe()
        port_in  = self._liquid_port(P=8e5)
        port_out = pipe.solve_ss(port_in)
        expected = port_in.P - pipe.pressure_drop()
        assert port_out.P == pytest.approx(expected, rel=1e-10)

    def test_inlet_stored(self):
        pipe = self._make_pipe()
        port_in = self._liquid_port()
        pipe.solve_ss(port_in)
        assert pipe.inlet is port_in

    def test_outlet_stored(self):
        pipe = self._make_pipe()
        port_in = self._liquid_port()
        port_out = pipe.solve_ss(port_in)
        assert pipe.outlet is port_out


class TestPipeWithHeatLoss:
    """Tests for pipe with Q_loss > 0."""

    def _make_pipe(self, Q_loss=100.0, L=1.0):
        geom = PipeGeometry(D_i=0.01, L=L)
        return Pipe(
            geometry=geom,
            Q_loss=Q_loss,
            dp_correlation_sp=ConstDP(500.0),
            dp_correlation_tp=ConstDP(500.0),
            name="LossyPipe",
        )

    def _liquid_port(self, h=3e5, mdot=0.05):
        return Port(state=StubState(h=h), mdot=mdot)

    def test_h_decreases_with_qloss(self):
        pipe = self._make_pipe(Q_loss=100.0)
        port_in  = self._liquid_port(h=3e5, mdot=0.05)
        port_out = pipe.solve_ss(port_in)
        assert port_out.h < port_in.h

    def test_h_drop_equals_qloss_over_mdot(self):
        Q_loss = 200.0
        mdot   = 0.04
        pipe   = self._make_pipe(Q_loss=Q_loss)
        port_in  = self._liquid_port(h=3e5, mdot=mdot)
        port_out = pipe.solve_ss(port_in)
        expected_h_out = port_in.h - Q_loss / mdot
        assert port_out.h == pytest.approx(expected_h_out, rel=1e-10)

    def test_heat_transfer_negative(self):
        """heat_transfer() should return −Q_loss (heat leaves fluid)."""
        pipe = self._make_pipe(Q_loss=150.0)
        port_in = self._liquid_port(mdot=0.05)
        pipe.solve_ss(port_in)
        assert pipe.heat_transfer() == pytest.approx(-150.0)

    def test_heat_transfer_zero_when_adiabatic(self):
        pipe = self._make_pipe(Q_loss=0.0)
        port_in = self._liquid_port()
        pipe.solve_ss(port_in)
        assert pipe.heat_transfer() == pytest.approx(0.0)


class TestPipeTwoPhase:
    """Two-phase pipe tests."""

    def _make_tp_pipe(self, orientation="horizontal", Q_loss=0.0, L=1.0):
        geom = PipeGeometry(D_i=0.008, L=L, orientation=orientation)
        return Pipe(
            geometry=geom,
            Q_loss=Q_loss,
            dp_correlation_sp=ConstDP(300.0),
            dp_correlation_tp=ConstDP(1000.0),  # higher for two-phase
            name="TwoPhPipe",
        )

    def _tp_port(self, P=5e5, h=2e5, mdot=0.01):
        return Port(state=StubStateTP(P=P, h=h), mdot=mdot)

    def test_P_decreases_tp(self):
        pipe = self._make_tp_pipe()
        port_out = pipe.solve_ss(self._tp_port())
        assert port_out.P < 5e5

    def test_friction_uses_tp_correlation(self):
        """Two-phase correlation (1000 Pa/m) vs single-phase (300 Pa/m)."""
        pipe  = self._make_tp_pipe(L=1.0)
        port_out = pipe.solve_ss(self._tp_port())
        assert pipe.dP_friction == pytest.approx(1000.0 * 1.0, rel=1e-10)

    def test_gravity_vertical_up_tp(self):
        """Two-phase vertical-up: gravity uses HEM mixture density."""
        pipe = self._make_tp_pipe(orientation="vertical_up", L=1.0)
        pipe.solve_ss(self._tp_port())
        expected = StubStateTP().rho * 9.806 * 1.0
        assert pipe.dP_gravity == pytest.approx(expected, rel=1e-3)

    def test_accel_zero_adiabatic_tp(self):
        """Adiabatic two-phase: no enthalpy change → no acceleration ΔP."""
        pipe = self._make_tp_pipe(Q_loss=0.0)
        pipe.solve_ss(self._tp_port())
        assert pipe.dP_accel == pytest.approx(0.0, abs=1e-6)

    def test_accel_nonzero_with_qloss_tp(self):
        """Two-phase with Q_loss → quality changes → acceleration term ≠ 0."""
        pipe = self._make_tp_pipe(Q_loss=50.0, L=1.0)
        pipe.solve_vs = pipe.solve_ss
        port_in  = self._tp_port(mdot=0.01)
        pipe.solve_ss(port_in)
        # The acceleration ΔP should be non-zero (quality decreases with heat loss)
        # We only check the sign: condensing → x decreases → v_tp decreases → ΔP_a < 0
        # (pressure recovered), or for evaporating → positive
        # Here Q_loss > 0 means heat leaves → condensing → x_out < x_in → dP_accel < 0
        assert pipe.dP_accel != pytest.approx(0.0, abs=1e-6)


class TestPipeEdgeCases:
    """Edge cases and error handling."""

    def _make_pipe(self):
        geom = PipeGeometry(D_i=0.01, L=1.0)
        return Pipe(
            geometry=geom,
            dp_correlation_sp=ConstDP(500.0),
            dp_correlation_tp=ConstDP(500.0),
        )

    def test_negative_mdot_raises(self):
        pipe = self._make_pipe()
        port_in = Port(state=StubState(), mdot=-0.01)
        with pytest.raises(ComponentError):
            pipe.solve_ss(port_in)

    def test_zero_mdot_raises(self):
        pipe = self._make_pipe()
        port_in = Port(state=StubState(), mdot=0.0)
        with pytest.raises(ComponentError):
            pipe.solve_ss(port_in)

    def test_missing_dp_correlation_raises(self):
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, dp_correlation_sp=None, dp_correlation_tp=None)
        port_in = Port(state=StubState(), mdot=0.05)
        with pytest.raises(ComponentError):
            pipe.solve_ss(port_in)

    def test_small_dp_does_not_make_P_negative(self):
        """Extremely high ΔP should be clamped with a warning, not crash."""
        geom = PipeGeometry(D_i=0.001, L=100.0)  # thin long pipe
        pipe = Pipe(
            geometry=geom,
            dp_correlation_sp=ConstDP(1e7),   # 10 MPa/m — absurd but tests clamping
            dp_correlation_tp=ConstDP(1e7),
        )
        port_in = Port(state=StubState(P=1e5), mdot=0.05)
        with pytest.warns(RuntimeWarning):
            port_out = pipe.solve_ss(port_in)
        assert port_out.P > 0.0

    def test_summary_string(self):
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, dp_correlation_sp=ConstDP(), dp_correlation_tp=ConstDP(),
                    name="MyPipe")
        port_in = Port(state=StubState(), mdot=0.05)
        pipe.solve_ss(port_in)
        s = pipe.summary()
        assert "MyPipe" in s
        assert "ΔP_total" in s

    def test_name_defaults_to_Pipe(self):
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, dp_correlation_sp=ConstDP(), dp_correlation_tp=ConstDP())
        assert pipe.name == "Pipe"

    def test_custom_name(self):
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, dp_correlation_sp=ConstDP(), dp_correlation_tp=ConstDP(),
                    name="LiquidLine")
        assert pipe.name == "LiquidLine"

    def test_dP_alias(self):
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, dp_correlation_sp=ConstDP(200.0),
                    dp_correlation_tp=ConstDP(200.0))
        pipe.solve_ss(Port(state=StubState(), mdot=0.05))
        assert pipe.dP == pipe.pressure_drop()


# ===========================================================================
# ── INTEGRATION TESTS (only run if CoolProp + correlations available)
# ===========================================================================

try:
    from fluid_properties import FluidState
    from correlations import BlassiusDP, HomogeneousDP
    _INTEGRATION_AVAILABLE = True
except ImportError:
    _INTEGRATION_AVAILABLE = False


@pytest.mark.skipif(not _INTEGRATION_AVAILABLE, reason="CoolProp not available")
class TestPipeIntegration:
    """Integration tests using real FluidState and real correlations."""

    def test_single_phase_liquid_acetone(self):
        """Single-phase liquid Acetone pipe: basic physical consistency."""
        geom = PipeGeometry(D_i=0.01, L=1.0, orientation="horizontal")
        pipe = Pipe(geometry=geom, Q_loss=0.0, fluid="Acetone", name="AcetonePipe")

        # Acetone saturation at 5 bar ~ 140°C; use T=60°C, P=5bar → subcooled liquid
        state_in = FluidState.from_PT("Acetone", 5e5, 333.15)
        port_in  = Port(state=state_in, mdot=0.02)
        port_out = pipe.solve_ss(port_in)

        assert port_out.P    <  port_in.P
        assert port_out.h    == pytest.approx(port_in.h, rel=1e-10)
        assert port_out.mdot == pytest.approx(port_in.mdot, rel=1e-10)
        assert pipe.dP_friction > 0.0
        assert pipe.dP_gravity  == pytest.approx(0.0, abs=1e-6)

    def test_single_phase_R134a_vertical_up(self):
        """R134a liquid vertical-up pipe: gravity adds to drop."""
        geom = PipeGeometry(D_i=0.01, L=1.0, orientation="vertical_up")
        pipe = Pipe(geometry=geom, Q_loss=0.0, fluid="R134a", name="R134aPipe")

        # R134a subcooled: T = -20°C, P = 8 bar (sat P @ -20°C ~ 1.3 bar, so 8 bar is compressed)
        state_in = FluidState.from_PT("R134a", 8e5, 253.15)
        port_in  = Port(state=state_in, mdot=0.03)
        pipe.solve_ss(port_in)

        assert pipe.dP_gravity > 0.0
        assert pipe.pressure_drop() > pipe.dP_friction

    def test_two_phase_R134a(self):
        """Two-phase R134a pipe: pressure drops, quality changes with heat loss."""
        geom = PipeGeometry(D_i=0.008, L=0.5, orientation="horizontal")
        pipe = Pipe(geometry=geom, Q_loss=5.0, fluid="R134a", name="TwoPhasePipe")

        state_in = FluidState.from_Px("R134a", 4.0e5, 0.3)
        port_in  = Port(state=state_in, mdot=0.01)
        port_out = pipe.solve_ss(port_in)

        assert port_out.P < port_in.P
        assert port_out.h < port_in.h  # heat removed

    def test_multiple_solves_idempotent(self):
        """Repeated solves with same inlet should give same outlet."""
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, Q_loss=0.0, fluid="Acetone")

        state_in = FluidState.from_PT("Acetone", 5e5, 333.15)
        port_in  = Port(state=state_in, mdot=0.02)

        port_out_1 = pipe.solve_ss(port_in)
        port_out_2 = pipe.solve_ss(port_in)

        assert port_out_1.P == pytest.approx(port_out_2.P, rel=1e-12)
        assert port_out_1.h == pytest.approx(port_out_2.h, rel=1e-12)

    def test_mass_flux_scaling(self):
        """Higher mdot → higher G → higher ΔP_friction (turbulent regime)."""
        geom = PipeGeometry(D_i=0.01, L=1.0)
        pipe = Pipe(geometry=geom, Q_loss=0.0, fluid="Acetone")

        state_in = FluidState.from_PT("Acetone", 5e5, 333.15)

        port_low  = Port(state=state_in, mdot=0.01)
        port_high = Port(state=state_in, mdot=0.05)

        pipe.solve_ss(port_low)
        dP_low = pipe.dP_friction

        pipe.solve_ss(port_high)
        dP_high = pipe.dP_friction

        assert dP_high > dP_low

    def test_longer_pipe_higher_dp(self):
        """Longer pipe → higher friction pressure drop."""
        geom_short = PipeGeometry(D_i=0.01, L=0.5)
        geom_long  = PipeGeometry(D_i=0.01, L=2.0)

        state_in = FluidState.from_PT("Acetone", 5e5, 333.15)
        port_in  = Port(state=state_in, mdot=0.02)

        pipe_short = Pipe(geometry=geom_short, Q_loss=0.0, fluid="Acetone")
        pipe_long  = Pipe(geometry=geom_long,  Q_loss=0.0, fluid="Acetone")

        pipe_short.solve_ss(port_in)
        pipe_long.solve_ss(port_in)

        assert pipe_long.dP_friction > pipe_short.dP_friction
