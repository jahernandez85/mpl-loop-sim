"""Tests for FluidIdentity: PureFluid, Mixture, CustomFluid.

Acceptance criteria (INTERFACE_SPEC §3.1, TEST_PLAN_V1 §5.1):
- Structural equality holds for all three variants.
- All variants are immutable after construction.
- No thermodynamic properties are stored on identity objects.
"""

import pytest

from mpl_sim.core.fluid_identity import CustomFluid, FluidIdentity, Mixture, PureFluid


class TestPureFluid:
    def test_construction(self):
        f = PureFluid("R134a")
        assert f.name == "R134a"

    def test_structural_equality(self):
        assert PureFluid("R134a") == PureFluid("R134a")

    def test_structural_inequality(self):
        assert PureFluid("R134a") != PureFluid("Acetone")

    def test_case_sensitive(self):
        assert PureFluid("r134a") != PureFluid("R134a")

    def test_immutable(self):
        f = PureFluid("R134a")
        with pytest.raises(AttributeError):
            f.name = "Water"  # type: ignore[misc]

    def test_hashable(self):
        s = {PureFluid("R134a"), PureFluid("R134a"), PureFluid("Acetone")}
        assert len(s) == 2

    def test_no_thermodynamic_fields(self):
        f = PureFluid("R134a")
        for attr in ("T", "h", "P", "x", "rho", "mu", "k", "sigma", "cp", "phase"):
            assert not hasattr(f, attr), f"PureFluid must not have field '{attr}'"


class TestMixture:
    def test_construction(self):
        m = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        assert m.components == (("R134a", 0.7), ("R32", 0.3))
        assert m.model is None

    def test_construction_with_model(self):
        m = Mixture(components=(("R134a", 0.5), ("R32", 0.5)), model="HEOS")
        assert m.model == "HEOS"

    def test_structural_equality(self):
        m1 = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        m2 = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        assert m1 == m2

    def test_structural_inequality_different_fractions(self):
        m1 = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        m2 = Mixture(components=(("R134a", 0.6), ("R32", 0.4)))
        assert m1 != m2

    def test_structural_inequality_order_matters(self):
        # Ordering is part of the identity — different order is a different mixture.
        m1 = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        m2 = Mixture(components=(("R32", 0.3), ("R134a", 0.7)))
        assert m1 != m2

    def test_structural_inequality_model(self):
        m1 = Mixture(components=(("R134a", 1.0),), model="HEOS")
        m2 = Mixture(components=(("R134a", 1.0),), model=None)
        assert m1 != m2

    def test_immutable_components(self):
        m = Mixture(components=(("R134a", 1.0),))
        with pytest.raises(AttributeError):
            m.components = (("Water", 1.0),)  # type: ignore[misc]

    def test_hashable(self):
        m1 = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        m2 = Mixture(components=(("R134a", 0.7), ("R32", 0.3)))
        assert hash(m1) == hash(m2)

    def test_single_component_mixture(self):
        m = Mixture(components=(("R134a", 1.0),))
        assert len(m.components) == 1


class TestCustomFluid:
    def test_construction(self):
        c = CustomFluid("my_special_fluid_v2")
        assert c.handle == "my_special_fluid_v2"

    def test_structural_equality(self):
        assert CustomFluid("a") == CustomFluid("a")

    def test_structural_inequality(self):
        assert CustomFluid("a") != CustomFluid("b")

    def test_immutable(self):
        c = CustomFluid("x")
        with pytest.raises(AttributeError):
            c.handle = "y"  # type: ignore[misc]

    def test_hashable(self):
        assert hash(CustomFluid("a")) == hash(CustomFluid("a"))


class TestFluidIdentityUnion:
    """Verify all three variants satisfy the FluidIdentity union contract."""

    def test_pure_fluid_is_valid_identity(self):
        identity: FluidIdentity = PureFluid("R134a")
        assert isinstance(identity, PureFluid)

    def test_mixture_is_valid_identity(self):
        identity: FluidIdentity = Mixture(components=(("R134a", 1.0),))
        assert isinstance(identity, Mixture)

    def test_custom_fluid_is_valid_identity(self):
        identity: FluidIdentity = CustomFluid("handle")
        assert isinstance(identity, CustomFluid)

    def test_cross_type_inequality(self):
        # Different variants with the same string content are not equal.
        assert PureFluid("R134a") != CustomFluid("R134a")
