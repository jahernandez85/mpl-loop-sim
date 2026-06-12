"""Tests for FluidState.

Acceptance criteria (INTERFACE_SPEC §3.2, TEST_PLAN_V1 §5.1):
- FluidState holds exactly three fields: P, h, identity.
- FluidState is immutable.
- No mdot field.
- No stored derived properties (T, x, rho, mu, k, sigma, cp, h_f, h_g, h_fg, phase).
- FluidState does not import or depend on CoolProp.
"""

import dataclasses
import sys
from pathlib import Path

import pytest

from mpl_sim.core.fluid_identity import Mixture, PureFluid
from mpl_sim.core.fluid_state import FluidState

_R134A = PureFluid("R134a")
_ACETONE = PureFluid("Acetone")


class TestFluidStateConstruction:
    def test_construction_keyword_args(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        assert state.P == 1e5
        assert state.h == 200_000.0
        assert state.identity == _R134A

    def test_construction_positional_args(self):
        state = FluidState(1e5, 200_000.0, _R134A)
        assert state.P == 1e5
        assert state.h == 200_000.0
        assert state.identity == _R134A

    def test_construction_with_mixture_identity(self):
        mix = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        state = FluidState(P=5e5, h=350_000.0, identity=mix)
        assert state.identity == mix


class TestFluidStateExactlyThreeFields:
    def test_field_count(self):
        fields = dataclasses.fields(FluidState)
        assert len(fields) == 3, f"FluidState must have exactly 3 fields, got {len(fields)}"

    def test_field_names(self):
        names = {f.name for f in dataclasses.fields(FluidState)}
        assert names == {"P", "h", "identity"}


class TestFluidStateEquality:
    def test_equal_states(self):
        s1 = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        s2 = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        assert s1 == s2

    def test_inequality_on_P(self):
        s1 = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        s2 = FluidState(P=2e5, h=200_000.0, identity=_R134A)
        assert s1 != s2

    def test_inequality_on_h(self):
        s1 = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        s2 = FluidState(P=1e5, h=300_000.0, identity=_R134A)
        assert s1 != s2

    def test_inequality_on_identity(self):
        s1 = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        s2 = FluidState(P=1e5, h=200_000.0, identity=_ACETONE)
        assert s1 != s2


class TestFluidStateImmutability:
    def test_cannot_set_P(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        with pytest.raises(AttributeError):
            state.P = 2e5  # type: ignore[misc]

    def test_cannot_set_h(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        with pytest.raises(AttributeError):
            state.h = 300_000.0  # type: ignore[misc]

    def test_cannot_set_identity(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        with pytest.raises(AttributeError):
            state.identity = _ACETONE  # type: ignore[misc]

    def test_cannot_add_attribute(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        with pytest.raises(AttributeError):
            state.T = 300.0  # type: ignore[attr-defined]


class TestFluidStateNoMdot:
    def test_no_mdot_field(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        assert not hasattr(state, "mdot"), "FluidState must not have an mdot field"

    def test_mdot_not_in_dataclass_fields(self):
        names = {f.name for f in dataclasses.fields(FluidState)}
        assert "mdot" not in names


class TestFluidStateNoStoredDerivedProperties:
    """No derived thermodynamic quantity may be stored on FluidState."""

    FORBIDDEN = ("T", "x", "rho", "mu", "k", "sigma", "cp", "phase", "h_f", "h_g", "h_fg")

    def test_no_forbidden_fields_in_dataclass(self):
        field_names = {f.name for f in dataclasses.fields(FluidState)}
        for attr in self.FORBIDDEN:
            assert attr not in field_names, f"FluidState must not declare field '{attr}'"

    def test_no_forbidden_attributes_on_instance(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        for attr in self.FORBIDDEN:
            assert not hasattr(state, attr), f"FluidState instance must not have attribute '{attr}'"


class TestFluidStateNoCoolProp:
    """FluidState must not import or depend on CoolProp.

    CoolProp is only permitted inside mpl_sim.properties (ARCHITECTURE_MASTER §3,
    IMPLEMENTATION_PLAN §21-6, anti-pattern §19-9).
    """

    def test_no_coolprop_string_in_source(self):
        import mpl_sim.core.fluid_state as fs_module

        source_path = Path(fs_module.__file__)
        source = source_path.read_text(encoding="utf-8")
        assert "CoolProp" not in source, "fluid_state.py must not reference CoolProp"
        assert "coolprop" not in source.lower(), "fluid_state.py must not reference coolprop"

    def test_importing_fluid_state_does_not_load_coolprop(self):
        # Only valid when CoolProp was not already present before this test.
        # We verify fluid_state itself does not trigger a CoolProp import.
        before = "CoolProp" in sys.modules
        import mpl_sim.core.fluid_state  # noqa: F401

        after = "CoolProp" in sys.modules
        # If CoolProp was not there before, it must not be there after.
        if not before:
            assert not after, "Importing fluid_state must not load CoolProp"
