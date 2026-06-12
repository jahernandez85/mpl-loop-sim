"""Contract tests for Phase 2A — PropertyBackend interface.

Acceptance criteria (TEST_PLAN_V1 §5.2–§5.6, INTERFACE_SPEC §3.3, [F6], [F13]):

- PropertyName enum contains all required derived properties.
- BackendCapability contains expected capability flags.
- PhaseLabel contains expected phase descriptors.
- QueryStatus carries the required status codes.
- PropertyResult is a status-bearing return; never a bare array.
- PropertyBackend is abstract and cannot be instantiated.
- A conforming dummy backend satisfies the full interface.
- query() is vector-first: length-n input → length-n output.
- Scalar (length-1) and vector produce identical per-element values.
- An unsupported capability returns False; the query returns UNAVAILABLE with NaN.
- valid_range() is callable on the dummy backend.
- No CoolProp import exists anywhere in properties/backend.py.
- core/ (FluidState) does not import from properties/ (DAG guard).
- Importing properties/ does not trigger a CoolProp module load.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.properties.backend import (
    BackendCapability,
    PhaseLabel,
    PropertyBackend,
    PropertyName,
    PropertyResult,
    QueryStatus,
    ValidRange,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_R134A = PureFluid("R134a")
_P = np.array([8.0e5, 9.0e5, 10.0e5])  # 3-element pressure vector [Pa]
_H = np.array([250_000.0, 260_000.0, 270_000.0])  # 3-element enthalpy vector [J/kg]


class _DummyBackend(PropertyBackend):
    """Minimal conforming backend that returns constant dummy values.

    Used solely to verify the interface contract; no thermodynamics.
    """

    _SUPPORTED_CAPS = {
        BackendCapability.VECTOR_QUERIES,
        BackendCapability.SATURATION_PROPERTIES,
        BackendCapability.SURFACE_TENSION,
    }

    def query(
        self,
        prop: PropertyName,
        P: np.ndarray,
        h: np.ndarray,
        identity,
    ) -> PropertyResult:
        n = len(P)
        if prop == PropertyName.SIGMA_E:
            # electrical conductivity is not in supported caps
            return PropertyResult.unavailable(n, warning="SIGMA_E not supported")
        if prop == PropertyName.T:
            return PropertyResult.ok(np.full(n, 300.0))
        # All other supported props: return dummy 1.0 array
        return PropertyResult.ok(np.ones(n))

    def query_derivative(
        self,
        prop: PropertyName,
        P: np.ndarray,
        h: np.ndarray,
        identity,
    ) -> PropertyResult:
        n = len(P)
        # Derivatives not supported in this dummy
        return PropertyResult.unavailable(n, warning="derivatives not supported")

    def provides(self, cap: BackendCapability) -> bool:
        return cap in self._SUPPORTED_CAPS

    def valid_range(self, identity) -> ValidRange:
        return ValidRange(P_min=1e4, P_max=5e6, h_min=100_000.0, h_max=600_000.0)


@pytest.fixture
def backend() -> _DummyBackend:
    return _DummyBackend()


# ---------------------------------------------------------------------------
# PropertyName enum completeness
# ---------------------------------------------------------------------------


class TestPropertyNameEnum:
    REQUIRED_NAMES = {
        "T",
        "T_SAT",
        "X",
        "RHO",
        "MU",
        "K",
        "SIGMA",
        "CP",
        "PHASE",
        "H_F",
        "H_G",
        "H_FG",
    }

    def test_contains_all_required_properties(self):
        member_names = {m.name for m in PropertyName}
        missing = self.REQUIRED_NAMES - member_names
        assert not missing, f"PropertyName is missing: {missing}"

    def test_t_member(self):
        assert PropertyName.T is not None

    def test_rho_member(self):
        assert PropertyName.RHO is not None

    def test_x_member(self):
        assert PropertyName.X is not None

    def test_sigma_member(self):
        assert PropertyName.SIGMA is not None

    def test_sigma_e_member_for_table_only_backend(self):
        # sigma_e exists as a name; CoolProp will return UNAVAILABLE for it
        assert PropertyName.SIGMA_E is not None

    def test_derivative_members_present(self):
        assert PropertyName.DRHO_DP_H is not None
        assert PropertyName.DRHO_DH_P is not None


# ---------------------------------------------------------------------------
# PhaseLabel enum
# ---------------------------------------------------------------------------


class TestPhaseLabelEnum:
    REQUIRED = {"LIQUID", "TWO_PHASE", "VAPOR", "SUPERCRITICAL", "UNKNOWN"}

    def test_contains_required_labels(self):
        member_names = {m.name for m in PhaseLabel}
        missing = self.REQUIRED - member_names
        assert not missing, f"PhaseLabel is missing: {missing}"

    def test_labels_are_distinct(self):
        labels = list(PhaseLabel)
        assert len(labels) == len(set(labels))


# ---------------------------------------------------------------------------
# BackendCapability enum
# ---------------------------------------------------------------------------


class TestBackendCapabilityEnum:
    REQUIRED = {
        "DERIVATIVES",
        "SURFACE_TENSION",
        "ELECTRICAL_CONDUCTIVITY",
        "RELATIVE_PERMITTIVITY",
        "SATURATION_PROPERTIES",
        "VECTOR_QUERIES",
    }

    def test_contains_required_capabilities(self):
        member_names = {m.name for m in BackendCapability}
        missing = self.REQUIRED - member_names
        assert not missing, f"BackendCapability is missing: {missing}"


# ---------------------------------------------------------------------------
# QueryStatus
# ---------------------------------------------------------------------------


class TestQueryStatus:
    def test_has_ok(self):
        assert QueryStatus.OK is not None

    def test_has_unavailable(self):
        assert QueryStatus.UNAVAILABLE is not None

    def test_has_out_of_range(self):
        assert QueryStatus.OUT_OF_RANGE is not None


# ---------------------------------------------------------------------------
# PropertyResult value object
# ---------------------------------------------------------------------------


class TestPropertyResult:
    def test_ok_factory(self):
        vals = np.array([1.0, 2.0, 3.0])
        result = PropertyResult.ok(vals)
        assert len(result.values) == 3
        assert all(s == QueryStatus.OK for s in result.status)
        assert result.warning is None

    def test_unavailable_factory(self):
        result = PropertyResult.unavailable(4, warning="no data")
        assert len(result.values) == 4
        assert all(np.isnan(result.values))
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)
        assert result.warning == "no data"

    def test_out_of_range_factory(self):
        result = PropertyResult.out_of_range(2)
        assert all(np.isnan(result.values))
        assert all(s == QueryStatus.OUT_OF_RANGE for s in result.status)

    def test_mismatched_lengths_raise(self):
        with pytest.raises(ValueError, match="length"):
            PropertyResult(
                values=np.array([1.0, 2.0]),
                status=(QueryStatus.OK,),  # length 1 != 2
            )

    def test_frozen(self):
        result = PropertyResult.ok(np.array([1.0]))
        with pytest.raises(AttributeError):
            result.warning = "oops"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ValidRange value object
# ---------------------------------------------------------------------------


class TestValidRange:
    def test_construction(self):
        vr = ValidRange(P_min=1e4, P_max=5e6, h_min=1e5, h_max=6e5)
        assert vr.P_min == 1e4
        assert vr.P_max == 5e6
        assert vr.h_min == 1e5
        assert vr.h_max == 6e5

    def test_defaults_are_none(self):
        vr = ValidRange()
        assert vr.P_min is None
        assert vr.P_max is None

    def test_frozen(self):
        vr = ValidRange(P_min=1e4)
        with pytest.raises(AttributeError):
            vr.P_min = 2e4  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PropertyBackend abstract class
# ---------------------------------------------------------------------------


class TestPropertyBackendIsAbstract:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            PropertyBackend()  # type: ignore[abstract]

    def test_subclass_without_query_is_abstract(self):
        class Incomplete(PropertyBackend):
            def provides(self, cap):
                return False

            def valid_range(self, identity):
                return ValidRange()

            # query and query_derivative intentionally omitted

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Dummy backend — vector-first query behaviour
# ---------------------------------------------------------------------------


class TestDummyBackendVectorQuery:
    def test_vector_query_returns_same_length(self, backend: _DummyBackend):
        result = backend.query(PropertyName.T, _P, _H, _R134A)
        assert len(result.values) == len(_P)
        assert len(result.status) == len(_P)

    def test_scalar_length_one_query(self, backend: _DummyBackend):
        P1 = np.array([8.0e5])
        H1 = np.array([250_000.0])
        result = backend.query(PropertyName.T, P1, H1, _R134A)
        assert len(result.values) == 1
        assert result.status[0] == QueryStatus.OK

    def test_scalar_and_vector_agree_per_element(self, backend: _DummyBackend):
        """A scalar call (length-1) and the same element from a vector call must agree."""
        vec_result = backend.query(PropertyName.T, _P, _H, _R134A)
        for i in range(len(_P)):
            scalar_result = backend.query(
                PropertyName.T,
                np.array([_P[i]]),
                np.array([_H[i]]),
                _R134A,
            )
            assert scalar_result.values[0] == pytest.approx(vec_result.values[i])

    def test_all_ok_for_supported_prop(self, backend: _DummyBackend):
        result = backend.query(PropertyName.T, _P, _H, _R134A)
        assert all(s == QueryStatus.OK for s in result.status)
        assert not any(np.isnan(result.values))


# ---------------------------------------------------------------------------
# Dummy backend — unsupported capability
# ---------------------------------------------------------------------------


class TestDummyBackendCapability:
    def test_supported_cap_returns_true(self, backend: _DummyBackend):
        assert backend.provides(BackendCapability.VECTOR_QUERIES) is True

    def test_unsupported_cap_returns_false(self, backend: _DummyBackend):
        assert backend.provides(BackendCapability.DERIVATIVES) is False
        assert backend.provides(BackendCapability.ELECTRICAL_CONDUCTIVITY) is False

    def test_unsupported_prop_returns_unavailable_not_raises(self, backend: _DummyBackend):
        result = backend.query(PropertyName.SIGMA_E, _P, _H, _R134A)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)
        assert all(np.isnan(result.values))
        assert result.warning is not None

    def test_derivatives_not_supported_returns_unavailable(self, backend: _DummyBackend):
        result = backend.query_derivative(PropertyName.DRHO_DP_H, _P, _H, _R134A)
        assert all(s == QueryStatus.UNAVAILABLE for s in result.status)


# ---------------------------------------------------------------------------
# valid_range contract
# ---------------------------------------------------------------------------


class TestValidRangeContract:
    def test_valid_range_returns_valid_range_object(self, backend: _DummyBackend):
        vr = backend.valid_range(_R134A)
        assert isinstance(vr, ValidRange)

    def test_valid_range_fields_are_finite(self, backend: _DummyBackend):
        vr = backend.valid_range(_R134A)
        if vr.P_min is not None:
            assert np.isfinite(vr.P_min)
        if vr.P_max is not None:
            assert np.isfinite(vr.P_max)


# ---------------------------------------------------------------------------
# DAG / import boundary guards
# ---------------------------------------------------------------------------


class TestNoCoolPropInBackend:
    """ARCHITECTURE_MASTER §3, IMPLEMENTATION_PLAN §21-6: only properties/ may import CoolProp."""

    def test_no_coolprop_import_in_backend_source(self):
        """The word 'CoolProp' may appear in comments/docstrings; what must not
        appear is any actual import statement for CoolProp."""
        import mpl_sim.properties.backend as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        import_lines = [ln for ln in source.splitlines() if "import" in ln.lower()]
        for line in import_lines:
            stripped = line.lstrip()
            assert not stripped.startswith(
                "import CoolProp"
            ), f"backend.py must not import CoolProp: {line!r}"
            assert not stripped.startswith(
                "from CoolProp"
            ), f"backend.py must not import from CoolProp: {line!r}"

    def test_importing_properties_does_not_load_coolprop(self):
        before = "CoolProp" in sys.modules
        import mpl_sim.properties  # noqa: F401

        after = "CoolProp" in sys.modules
        if not before:
            assert not after, "Importing properties/ must not load CoolProp"


class TestCoreDoesNotImportProperties:
    """core/ is DAG layer 0; properties/ is layer 1.  Layer 0 must not depend on layer 1."""

    def test_fluid_state_source_has_no_properties_import(self):
        import mpl_sim.core.fluid_state as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "mpl_sim.properties" not in source
        assert "from mpl_sim.properties" not in source

    def test_fluid_identity_source_has_no_properties_import(self):
        import mpl_sim.core.fluid_identity as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "mpl_sim.properties" not in source

    def test_core_init_has_no_properties_import(self):
        import mpl_sim.core as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "mpl_sim.properties" not in source


class TestFluidStateRemainsBackendFree:
    """FluidState must not hold a backend reference (INTERFACE_SPEC §3.2)."""

    def test_fluid_state_has_no_backend_attribute(self):
        import dataclasses

        from mpl_sim.core.fluid_state import FluidState

        field_names = {f.name for f in dataclasses.fields(FluidState)}
        assert "backend" not in field_names
        assert "property_backend" not in field_names
        assert "_backend" not in field_names

    def test_fluid_state_instance_has_no_backend_attribute(self):
        state = FluidState(P=1e5, h=200_000.0, identity=_R134A)
        assert not hasattr(state, "backend")
        assert not hasattr(state, "property_backend")


# ---------------------------------------------------------------------------
# Phase 1 smoke guard — existing tests must still pass (not weakened)
# ---------------------------------------------------------------------------


class TestPhase1RegressionGuard:
    """Sanity check that Phase 1 exports remain intact after Phase 2A."""

    def test_core_exports_still_present(self):
        from mpl_sim.core import (  # noqa: F401
            FluidIdentity,
            FluidState,
            InternalStateHandle,
            Port,
            PortId,
            PortRole,
            PortVariableHandle,
            StateLayout,
            StateVariableId,
            SystemState,
            VariableKind,
        )

    def test_fluid_state_still_three_fields(self):
        import dataclasses

        from mpl_sim.core.fluid_state import FluidState

        assert len(dataclasses.fields(FluidState)) == 3
