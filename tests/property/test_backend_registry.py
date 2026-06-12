"""Tests for Phase 2C — PropertyBackendRegistry and BackendSelection.

Acceptance criteria (INTERFACE_SPEC §3.4, TEST_PLAN_V1 §5):

- BackendSelection is immutable, hashable, and equality-comparable.
- PropertyBackendRegistry.register() accepts a constructor by name.
- PropertyBackendRegistry.register() raises ValueError on duplicate registration.
- PropertyBackendRegistry.is_registered() returns correct booleans.
- PropertyBackendRegistry.resolve() constructs and returns a backend instance.
- PropertyBackendRegistry.resolve() raises KeyError for unknown names.
- PropertyBackendRegistry.resolve() returns a fresh instance on each call.
- PropertyBackendRegistry.instance_for() returns a PropertyBackend.
- PropertyBackendRegistry.instance_for() returns the same instance on repeated calls.
- PropertyBackendRegistry.instance_for() raises KeyError for unknown backend name.
- PropertyBackendRegistry.backend_names() lists registered names.
- default_backend_name_for() returns "coolprop" for PureFluid.
- default_backend_name_for() raises TypeError for Mixture and CustomFluid.
- create_default_property_backend_registry() registers "coolprop".
- Default registry "coolprop" resolves to a PropertyBackend instance.
- Lazy import: creating the default registry does NOT import CoolProp.
- CoolPropBackend.query() raises ValueError for mismatched P/h lengths (audit follow-up).
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from mpl_sim.core.fluid_identity import CustomFluid, Mixture, PureFluid
from mpl_sim.properties import (
    BackendSelection,
    PropertyBackend,
    PropertyBackendRegistry,
    create_default_property_backend_registry,
    default_backend_name_for,
)
from mpl_sim.properties.backend import (
    BackendCapability,
    PropertyResult,
    ValidRange,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_R134A = PureFluid("R134a")
_MIXTURE = Mixture((("R134a", 0.5), ("R32", 0.5)))
_CUSTOM = CustomFluid("my_fluid")


class _StubBackend(PropertyBackend):
    """Minimal no-physics stub used to test the registry without CoolProp."""

    def query(self, prop, P, h, identity) -> PropertyResult:
        return PropertyResult.ok(np.ones(len(P)))

    def query_derivative(self, prop, P, h, identity) -> PropertyResult:
        return PropertyResult.unavailable(len(P))

    def provides(self, cap: BackendCapability) -> bool:
        return cap == BackendCapability.VECTOR_QUERIES

    def valid_range(self, identity) -> ValidRange:
        return ValidRange()


def _stub_constructor() -> PropertyBackend:
    return _StubBackend()


# ---------------------------------------------------------------------------
# BackendSelection value object
# ---------------------------------------------------------------------------


class TestBackendSelection:
    def test_construction(self):
        sel = BackendSelection(identity=_R134A, backend_name="coolprop")
        assert sel.identity == _R134A
        assert sel.backend_name == "coolprop"

    def test_equality(self):
        a = BackendSelection(identity=_R134A, backend_name="coolprop")
        b = BackendSelection(identity=_R134A, backend_name="coolprop")
        assert a == b

    def test_inequality_different_identity(self):
        a = BackendSelection(identity=PureFluid("R134a"), backend_name="coolprop")
        b = BackendSelection(identity=PureFluid("Water"), backend_name="coolprop")
        assert a != b

    def test_inequality_different_name(self):
        a = BackendSelection(identity=_R134A, backend_name="coolprop")
        b = BackendSelection(identity=_R134A, backend_name="refprop")
        assert a != b

    def test_hashable(self):
        sel = BackendSelection(identity=_R134A, backend_name="coolprop")
        assert hash(sel) is not None
        s = {sel}
        assert sel in s

    def test_immutable(self):
        sel = BackendSelection(identity=_R134A, backend_name="coolprop")
        with pytest.raises(AttributeError):
            sel.backend_name = "other"  # type: ignore[misc]

    def test_usable_as_dict_key(self):
        sel = BackendSelection(identity=_R134A, backend_name="coolprop")
        d = {sel: "value"}
        assert d[sel] == "value"

    def test_mixture_identity(self):
        sel = BackendSelection(identity=_MIXTURE, backend_name="future_backend")
        assert sel.identity == _MIXTURE

    def test_custom_fluid_identity(self):
        sel = BackendSelection(identity=_CUSTOM, backend_name="empirical")
        assert sel.identity == _CUSTOM


# ---------------------------------------------------------------------------
# PropertyBackendRegistry — registration
# ---------------------------------------------------------------------------


class TestRegistryRegister:
    def test_register_adds_backend(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        assert reg.is_registered("stub")

    def test_register_multiple_backends(self):
        reg = PropertyBackendRegistry()
        reg.register("alpha", _stub_constructor)
        reg.register("beta", _stub_constructor)
        assert reg.is_registered("alpha")
        assert reg.is_registered("beta")

    def test_duplicate_registration_raises_value_error(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("stub", _stub_constructor)

    def test_is_registered_false_for_unknown(self):
        reg = PropertyBackendRegistry()
        assert not reg.is_registered("unknown")

    def test_is_registered_true_after_register(self):
        reg = PropertyBackendRegistry()
        reg.register("x", _stub_constructor)
        assert reg.is_registered("x")


# ---------------------------------------------------------------------------
# PropertyBackendRegistry — backend_names()
# ---------------------------------------------------------------------------


class TestRegistryBackendNames:
    def test_empty_registry_returns_empty_list(self):
        reg = PropertyBackendRegistry()
        assert reg.backend_names() == []

    def test_names_after_single_registration(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        assert "stub" in reg.backend_names()

    def test_names_after_multiple_registrations(self):
        reg = PropertyBackendRegistry()
        reg.register("a", _stub_constructor)
        reg.register("b", _stub_constructor)
        names = reg.backend_names()
        assert "a" in names
        assert "b" in names
        assert len(names) == 2


# ---------------------------------------------------------------------------
# PropertyBackendRegistry — resolve()
# ---------------------------------------------------------------------------


class TestRegistryResolve:
    def test_resolve_returns_property_backend(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        backend = reg.resolve("stub")
        assert isinstance(backend, PropertyBackend)

    def test_resolve_unknown_raises_key_error(self):
        reg = PropertyBackendRegistry()
        with pytest.raises(KeyError, match="unknown"):
            reg.resolve("unknown")

    def test_resolve_error_message_lists_available(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        with pytest.raises(KeyError) as exc_info:
            reg.resolve("missing")
        assert "stub" in str(exc_info.value)

    def test_resolve_returns_fresh_instance_each_call(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        a = reg.resolve("stub")
        b = reg.resolve("stub")
        assert a is not b

    def test_resolve_uses_registered_constructor(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        backend = reg.resolve("stub")
        assert isinstance(backend, _StubBackend)


# ---------------------------------------------------------------------------
# PropertyBackendRegistry — instance_for()
# ---------------------------------------------------------------------------


class TestRegistryInstanceFor:
    def test_instance_for_returns_property_backend(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        backend = reg.instance_for(_R134A, "stub")
        assert isinstance(backend, PropertyBackend)

    def test_instance_for_caches_per_identity_and_name(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        first = reg.instance_for(_R134A, "stub")
        second = reg.instance_for(_R134A, "stub")
        assert first is second

    def test_instance_for_different_identities_different_instances(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        r134a_inst = reg.instance_for(PureFluid("R134a"), "stub")
        water_inst = reg.instance_for(PureFluid("Water"), "stub")
        assert r134a_inst is not water_inst

    def test_instance_for_unknown_backend_raises_key_error(self):
        reg = PropertyBackendRegistry()
        with pytest.raises(KeyError, match="unknown_backend"):
            reg.instance_for(_R134A, "unknown_backend")

    def test_instance_for_supports_mixture_identity(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        backend = reg.instance_for(_MIXTURE, "stub")
        assert isinstance(backend, PropertyBackend)

    def test_instance_for_supports_custom_fluid_identity(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        backend = reg.instance_for(_CUSTOM, "stub")
        assert isinstance(backend, PropertyBackend)

    def test_instance_for_caches_mixture_separately_from_pure(self):
        reg = PropertyBackendRegistry()
        reg.register("stub", _stub_constructor)
        pure_inst = reg.instance_for(_R134A, "stub")
        mix_inst = reg.instance_for(_MIXTURE, "stub")
        assert pure_inst is not mix_inst


# ---------------------------------------------------------------------------
# default_backend_name_for()
# ---------------------------------------------------------------------------


class TestDefaultBackendNameFor:
    def test_pure_fluid_returns_coolprop(self):
        assert default_backend_name_for(_R134A) == "coolprop"

    def test_pure_fluid_any_name_returns_coolprop(self):
        assert default_backend_name_for(PureFluid("Water")) == "coolprop"

    def test_mixture_raises_type_error(self):
        with pytest.raises(TypeError, match="Mixture"):
            default_backend_name_for(_MIXTURE)

    def test_custom_fluid_raises_type_error(self):
        with pytest.raises(TypeError, match="CustomFluid"):
            default_backend_name_for(_CUSTOM)

    def test_error_message_mentions_v1(self):
        with pytest.raises(TypeError, match="V1"):
            default_backend_name_for(_MIXTURE)


# ---------------------------------------------------------------------------
# create_default_property_backend_registry()
# ---------------------------------------------------------------------------


class TestCreateDefaultRegistry:
    def test_coolprop_is_registered(self):
        reg = create_default_property_backend_registry()
        assert reg.is_registered("coolprop")

    def test_backend_names_contains_coolprop(self):
        reg = create_default_property_backend_registry()
        assert "coolprop" in reg.backend_names()

    def test_resolve_coolprop_returns_property_backend(self):
        reg = create_default_property_backend_registry()
        backend = reg.resolve("coolprop")
        assert isinstance(backend, PropertyBackend)

    def test_coolprop_backend_is_correct_type(self):
        from mpl_sim.properties import CoolPropBackend

        reg = create_default_property_backend_registry()
        backend = reg.resolve("coolprop")
        assert isinstance(backend, CoolPropBackend)

    def test_instance_for_pure_fluid_returns_backend(self):
        reg = create_default_property_backend_registry()
        backend = reg.instance_for(_R134A, "coolprop")
        assert isinstance(backend, PropertyBackend)

    def test_instance_for_caches_coolprop(self):
        reg = create_default_property_backend_registry()
        first = reg.instance_for(_R134A, "coolprop")
        second = reg.instance_for(_R134A, "coolprop")
        assert first is second

    def test_creating_registry_does_not_load_coolprop(self):
        # Only meaningful if CoolProp has not been loaded yet by a prior test.
        before = "CoolProp" in sys.modules or "CoolProp.CoolProp" in sys.modules
        if not before:
            create_default_property_backend_registry()
            after = "CoolProp" in sys.modules or "CoolProp.CoolProp" in sys.modules
            assert not after, "Factory must not load CoolProp until a backend is resolved"

    def test_unknown_backend_raises_in_default_registry(self):
        reg = create_default_property_backend_registry()
        with pytest.raises(KeyError):
            reg.resolve("refprop")


# ---------------------------------------------------------------------------
# Audit follow-up: CoolPropBackend.query() raises on mismatched P/h lengths
# ---------------------------------------------------------------------------


class TestCoolPropMismatchedLengths:
    """Audit follow-up: PHASE_2_PROPERTY_LAYER_AUDIT — shape-mismatch guard."""

    @pytest.fixture(scope="class")
    def backend(self):
        from mpl_sim.properties import CoolPropBackend

        return CoolPropBackend()

    def test_mismatched_lengths_raise_value_error(self, backend):
        P = np.array([8.0e5, 9.0e5])
        h = np.array([200_000.0])  # length 1 vs length 2
        with pytest.raises(ValueError, match="same length"):
            backend.query(
                __import__("mpl_sim.properties.backend", fromlist=["PropertyName"]).PropertyName.T,
                P,
                h,
                _R134A,
            )

    def test_mismatched_lengths_error_reports_both_lengths(self, backend):
        from mpl_sim.properties.backend import PropertyName

        P = np.array([8.0e5, 9.0e5, 10.0e5])
        h = np.array([200_000.0])
        with pytest.raises(ValueError, match="3") as exc_info:
            backend.query(PropertyName.T, P, h, _R134A)
        assert "1" in str(exc_info.value)

    def test_equal_lengths_do_not_raise(self, backend):
        from mpl_sim.properties.backend import PropertyName

        P = np.array([8.0e5, 9.0e5])
        h = np.array([200_000.0, 220_000.0])
        result = backend.query(PropertyName.T, P, h, _R134A)
        assert len(result.values) == 2
