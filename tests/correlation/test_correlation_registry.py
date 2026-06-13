"""Phase 3B — CorrelationRegistry tests.

Covers:
- Empty registry has no names
- Registering a dummy stateless correlation works
- Resolving by name returns the registered correlation
- Duplicate registration raises ValueError
- Unknown name raises KeyError
- is_registered works
- correlation_names() returns deterministic sorted names
- by_role() returns only correlations of requested role
- roles() returns the registered role set
- Registering without envelope is rejected
- Registering with invalid role is rejected
- Resolved dummy evaluates to CorrelationOutput
- Registry does not mutate the correlation
- Registry is separate from PropertyBackendRegistry
- Registry does not import CoolProp, properties, components, geometry,
  network, solvers, or calibration
- All existing Phase 3A tests still pass (by not breaking anything here)
"""

import subprocess
import sys

import pytest

from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SinglePhaseDPInput,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
    VolumePressureLawInput,
)
from mpl_sim.correlations.registry import (
    CorrelationRegistry,
    create_empty_correlation_registry,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _source() -> SourceRef:
    return SourceRef(citation="Dummy source", doi=None)


def _envelope() -> ValidityEnvelope:
    return ValidityEnvelope(
        fluid_families=(AnyFluid(),),
        bounds=(Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-"),),
        source=_source(),
    )


def _verdict() -> ValidityVerdict:
    return ValidityVerdict(
        status=ValidityStatus.IN_ENVELOPE,
        envelope=EnvelopeRef(correlation_name="dummy", correlation_version="0.1"),
        violated=(),
    )


def _metadata(name: str = "dummy") -> ClosureMetadata:
    return ClosureMetadata(name=name, version="0.1", source=_source())


# ---------------------------------------------------------------------------
# Dummy correlation implementations (no physics)
# ---------------------------------------------------------------------------


class DummySinglePhaseDP(Correlation):
    """Minimal stateless SINGLE_PHASE_DP correlation for testing."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _envelope()

    def evaluate(self, inp: SinglePhaseDPInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(0.0,),
            verdict=_verdict(),
            metadata=_metadata("dummy_single_phase_dp"),
        )


class DummyVolumePressureLaw(Correlation):
    """Minimal stateless VOLUME_PRESSURE_LAW correlation for testing."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.VOLUME_PRESSURE_LAW

    def envelope(self) -> ValidityEnvelope:
        return _envelope()

    def evaluate(self, inp: VolumePressureLawInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(inp.V_g / inp.V_total,),
            verdict=_verdict(),
            metadata=_metadata("dummy_vpl"),
        )


class DummyHTC(Correlation):
    """Minimal stateless HTC correlation for testing."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _envelope()

    def evaluate(self, inp) -> CorrelationOutput:
        return CorrelationOutput(
            value=(1000.0,),
            verdict=_verdict(),
            metadata=_metadata("dummy_htc"),
        )


class EnvelopelessCorrelation(Correlation):
    """A correlation that returns None for envelope() — inadmissible."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self):
        return None  # type: ignore[return-value]

    def evaluate(self, inp) -> CorrelationOutput:  # pragma: no cover
        return CorrelationOutput(
            value=(0.0,),
            verdict=_verdict(),
            metadata=_metadata(),
        )


class EmptyFluidsCorrelation(Correlation):
    """A correlation whose envelope has no fluid_families — inadmissible."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return ValidityEnvelope(
            fluid_families=(),
            bounds=(Bound(BoundedQuantity.REYNOLDS, min=1e3, max=1e6, units="-"),),
            source=_source(),
        )

    def evaluate(self, inp) -> CorrelationOutput:  # pragma: no cover
        return CorrelationOutput(
            value=(0.0,),
            verdict=_verdict(),
            metadata=_metadata(),
        )


class EmptyBoundsCorrelation(Correlation):
    """A correlation whose envelope has no bounds — inadmissible."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return ValidityEnvelope(
            fluid_families=(AnyFluid(),),
            bounds=(),
            source=_source(),
        )

    def evaluate(self, inp) -> CorrelationOutput:  # pragma: no cover
        return CorrelationOutput(
            value=(0.0,),
            verdict=_verdict(),
            metadata=_metadata(),
        )


class InvalidRoleCorrelation(Correlation):
    """A correlation that returns a non-CorrelationRole from role()."""

    def role(self):
        return "not_a_role"  # type: ignore[return-value]

    def envelope(self) -> ValidityEnvelope:
        return _envelope()

    def evaluate(self, inp) -> CorrelationOutput:  # pragma: no cover
        return CorrelationOutput(
            value=(0.0,),
            verdict=_verdict(),
            metadata=_metadata(),
        )


# ---------------------------------------------------------------------------
# Tests: empty registry
# ---------------------------------------------------------------------------


class TestEmptyRegistry:
    def test_no_names(self):
        reg = CorrelationRegistry()
        assert reg.correlation_names() == ()

    def test_no_roles(self):
        reg = CorrelationRegistry()
        assert reg.roles() == set()

    def test_is_registered_false(self):
        reg = CorrelationRegistry()
        assert not reg.is_registered("anything")

    def test_by_role_empty(self):
        reg = CorrelationRegistry()
        assert reg.by_role(CorrelationRole.HTC) == {}

    def test_resolve_unknown_raises_key_error(self):
        reg = CorrelationRegistry()
        with pytest.raises(KeyError):
            reg.resolve("nonexistent")

    def test_factory_returns_empty_registry(self):
        reg = create_empty_correlation_registry()
        assert isinstance(reg, CorrelationRegistry)
        assert reg.correlation_names() == ()


# ---------------------------------------------------------------------------
# Tests: registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_single_correlation(self):
        reg = CorrelationRegistry()
        corr = DummySinglePhaseDP()
        reg.register("single_dp", corr)
        assert reg.is_registered("single_dp")

    def test_resolve_returns_same_instance(self):
        reg = CorrelationRegistry()
        corr = DummySinglePhaseDP()
        reg.register("single_dp", corr)
        assert reg.resolve("single_dp") is corr

    def test_register_multiple_correlations(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        reg.register("vpl", DummyVolumePressureLaw())
        reg.register("htc", DummyHTC())
        assert len(reg.correlation_names()) == 3

    def test_registry_does_not_mutate_correlation(self):
        reg = CorrelationRegistry()
        corr = DummySinglePhaseDP()
        original_role = corr.role()
        original_envelope = corr.envelope()
        reg.register("single_dp", corr)
        assert corr.role() == original_role
        assert corr.envelope() == original_envelope

    def test_register_non_correlation_raises_type_error(self):
        reg = CorrelationRegistry()
        with pytest.raises(TypeError):
            reg.register("bad", object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: duplicate and unknown names
# ---------------------------------------------------------------------------


class TestNameErrors:
    def test_duplicate_name_raises_value_error(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        with pytest.raises(ValueError, match="already registered"):
            reg.register("single_dp", DummySinglePhaseDP())

    def test_unknown_name_raises_key_error(self):
        reg = CorrelationRegistry()
        with pytest.raises(KeyError):
            reg.resolve("unknown")

    def test_is_registered_false_before_registration(self):
        reg = CorrelationRegistry()
        assert not reg.is_registered("single_dp")

    def test_is_registered_true_after_registration(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        assert reg.is_registered("single_dp")


# ---------------------------------------------------------------------------
# Tests: correlation_names() determinism
# ---------------------------------------------------------------------------


class TestCorrelationNames:
    def test_names_are_sorted(self):
        reg = CorrelationRegistry()
        reg.register("zebra", DummyHTC())
        reg.register("alpha", DummySinglePhaseDP())
        reg.register("middle", DummyVolumePressureLaw())
        assert reg.correlation_names() == ("alpha", "middle", "zebra")

    def test_names_is_tuple(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        assert isinstance(reg.correlation_names(), tuple)

    def test_names_deterministic_across_calls(self):
        reg = CorrelationRegistry()
        reg.register("b_corr", DummySinglePhaseDP())
        reg.register("a_corr", DummyHTC())
        assert reg.correlation_names() == reg.correlation_names()


# ---------------------------------------------------------------------------
# Tests: by_role
# ---------------------------------------------------------------------------


class TestByRole:
    def test_by_role_returns_matching_only(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        reg.register("htc", DummyHTC())
        result = reg.by_role(CorrelationRole.HTC)
        assert set(result.keys()) == {"htc"}

    def test_by_role_empty_for_absent_role(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        assert reg.by_role(CorrelationRole.VOID_FRACTION) == {}

    def test_by_role_multiple_same_role(self):
        reg = CorrelationRegistry()
        reg.register("htc_a", DummyHTC())
        reg.register("htc_b", DummyHTC())
        result = reg.by_role(CorrelationRole.HTC)
        assert set(result.keys()) == {"htc_a", "htc_b"}

    def test_by_role_returns_dict(self):
        reg = CorrelationRegistry()
        reg.register("htc", DummyHTC())
        assert isinstance(reg.by_role(CorrelationRole.HTC), dict)


# ---------------------------------------------------------------------------
# Tests: roles()
# ---------------------------------------------------------------------------


class TestRoles:
    def test_roles_empty_initially(self):
        reg = CorrelationRegistry()
        assert reg.roles() == set()

    def test_roles_returns_registered_set(self):
        reg = CorrelationRegistry()
        reg.register("single_dp", DummySinglePhaseDP())
        reg.register("htc", DummyHTC())
        assert reg.roles() == {CorrelationRole.SINGLE_PHASE_DP, CorrelationRole.HTC}

    def test_roles_deduplicates(self):
        reg = CorrelationRegistry()
        reg.register("htc_a", DummyHTC())
        reg.register("htc_b", DummyHTC())
        assert reg.roles() == {CorrelationRole.HTC}

    def test_roles_returns_set(self):
        reg = CorrelationRegistry()
        assert isinstance(reg.roles(), set)


# ---------------------------------------------------------------------------
# Tests: envelope enforcement
# ---------------------------------------------------------------------------


class TestEnvelopeEnforcement:
    def test_none_envelope_rejected(self):
        reg = CorrelationRegistry()
        with pytest.raises(ValueError, match="ValidityEnvelope"):
            reg.register("bad", EnvelopelessCorrelation())

    def test_empty_fluid_families_rejected(self):
        reg = CorrelationRegistry()
        with pytest.raises(ValueError, match="fluid_families"):
            reg.register("bad", EmptyFluidsCorrelation())

    def test_empty_bounds_rejected(self):
        reg = CorrelationRegistry()
        with pytest.raises(ValueError, match="bounds"):
            reg.register("bad", EmptyBoundsCorrelation())

    def test_invalid_role_rejected(self):
        reg = CorrelationRegistry()
        with pytest.raises(ValueError, match="CorrelationRole"):
            reg.register("bad", InvalidRoleCorrelation())


# ---------------------------------------------------------------------------
# Tests: resolved correlation evaluates correctly
# ---------------------------------------------------------------------------


class TestEvaluation:
    def test_resolved_dummy_returns_correlation_output(self):
        reg = CorrelationRegistry()
        corr = DummySinglePhaseDP()
        reg.register("single_dp", corr)
        resolved = reg.resolve("single_dp")
        from mpl_sim.core.fluid_identity import PureFluid
        from mpl_sim.core.fluid_state import FluidState

        state = FluidState(P=1e6, h=2e5, identity=PureFluid("R134a"))
        inp = SinglePhaseDPInput(
            state=(state,),
            G=300.0,
            D_h=0.01,
            roughness=1e-6,
            L_cell=0.1,
        )
        out = resolved.evaluate(inp)
        assert isinstance(out, CorrelationOutput)
        assert isinstance(out.value, tuple)
        assert out.verdict is not None
        assert out.metadata is not None

    def test_output_has_value_verdict_metadata(self):
        reg = CorrelationRegistry()
        reg.register("vpl", DummyVolumePressureLaw())
        resolved = reg.resolve("vpl")
        inp = VolumePressureLawInput(V_g=0.5, V_total=1.0, law_params={})
        out = resolved.evaluate(inp)
        assert isinstance(out.value, tuple)
        assert len(out.value) >= 1
        assert isinstance(out.verdict, ValidityVerdict)
        assert isinstance(out.metadata, ClosureMetadata)


# ---------------------------------------------------------------------------
# Tests: separation from PropertyBackendRegistry
# ---------------------------------------------------------------------------


class TestSeparation:
    def test_registry_is_not_property_backend_registry(self):
        from mpl_sim.properties.registry import PropertyBackendRegistry

        reg = CorrelationRegistry()
        assert not isinstance(reg, PropertyBackendRegistry)
        assert type(reg) is CorrelationRegistry

    def test_two_registries_are_independent(self):
        reg_a = CorrelationRegistry()
        reg_b = CorrelationRegistry()
        reg_a.register("htc", DummyHTC())
        assert not reg_b.is_registered("htc")


# ---------------------------------------------------------------------------
# Tests: import boundary
# ---------------------------------------------------------------------------


class TestImportBoundary:
    def _run_import_check(self, module: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                f"import mpl_sim.correlations.registry; import {module}; "
                f"raise AssertionError('Forbidden import {module} succeeded')",
            ],
            capture_output=True,
            text=True,
        )

    def test_registry_does_not_import_coolprop(self):
        code = (
            "import sys; "
            "import mpl_sim.correlations.registry; "
            "assert 'CoolProp' not in sys.modules, "
            "'CoolProp found in sys.modules after importing registry'"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def _assert_module_absent(self, forbidden_prefix: str) -> None:
        code = (
            "import sys; "
            "import mpl_sim.correlations.registry; "
            f"loaded = [m for m in sys.modules if m.startswith({forbidden_prefix!r})]; "
            f"assert not loaded, f'Forbidden modules loaded: {{loaded}}'"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_registry_does_not_import_properties(self):
        self._assert_module_absent("mpl_sim.properties")

    def test_registry_does_not_import_components(self):
        self._assert_module_absent("mpl_sim.components")

    def test_registry_does_not_import_geometry(self):
        self._assert_module_absent("mpl_sim.geometry")

    def test_registry_does_not_import_calibration(self):
        self._assert_module_absent("mpl_sim.calibration")

    def test_registry_does_not_import_network(self):
        self._assert_module_absent("mpl_sim.network")

    def test_registry_does_not_import_solvers(self):
        self._assert_module_absent("mpl_sim.solvers")
