"""Tests for Pipe.evaluate_single_phase_friction — Phase 6B.

Verifies:
  - Pipe can evaluate single-phase friction using ChurchillFrictionGradient.
  - Result contains friction gradient [Pa/m].
  - Result contains total friction ΔP [Pa].
  - total ΔP == gradient × pipe length.
  - Result preserves correlation validity verdict.
  - Result preserves correlation metadata.
  - Result is non-negative for valid nonzero flow.
  - Zero flow returns zero friction result with documented verdict.
  - Increasing mass flux increases friction ΔP.
  - Increasing pipe length increases total ΔP but not friction gradient.
  - Method rejects non-SINGLE_PHASE_DP correlation.
  - Method rejects invalid rho and viscosity.
  - Method does not compute gravity.
  - Method does not compute acceleration.
  - Method does not compute heat transfer.
  - Method does not mutate geometry, discretization, or pipe.
  - Component package does not import CoolProp, network, or solvers.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import Pipe, PipeFrictionResult, PipeSinglePhaseFrictionInput
from mpl_sim.correlations.contract import Correlation, CorrelationRole, ValidityStatus
from mpl_sim.correlations.single_phase_dp import ChurchillFrictionGradient
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_CHURCHILL = ChurchillFrictionGradient()


def _make_geometry(L: float = 1.0, D_h: float = 0.01) -> PipeGeometry:
    traj = StraightSegment(length=L, delta_z=0.0)
    A = math.pi * (D_h / 2.0) ** 2
    return PipeGeometry(L=L, D_h=D_h, A=A, roughness=1e-5, trajectory=traj)


def _make_pipe(L: float = 1.0, D_h: float = 0.01, name: str = "pipe_1") -> Pipe:
    return Pipe(
        component_id=ComponentId(name),
        geometry=_make_geometry(L=L, D_h=D_h),
        discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
    )


def _typical_inp(G: float = 200.0) -> PipeSinglePhaseFrictionInput:
    """Typical single-phase input: liquid refrigerant-like properties."""
    return PipeSinglePhaseFrictionInput(G=G, rho=1200.0, mu=2e-4)


# ---------------------------------------------------------------------------
# PipeSinglePhaseFrictionInput validation
# ---------------------------------------------------------------------------


class TestPipeSinglePhaseFrictionInputValidation:
    def test_valid_construction(self) -> None:
        inp = PipeSinglePhaseFrictionInput(G=100.0, rho=1000.0, mu=1e-3)
        assert inp.G == 100.0
        assert inp.rho == 1000.0
        assert inp.mu == 1e-3

    def test_zero_G_allowed(self) -> None:
        inp = PipeSinglePhaseFrictionInput(G=0.0, rho=1000.0, mu=1e-3)
        assert inp.G == 0.0

    def test_negative_G_allowed(self) -> None:
        inp = PipeSinglePhaseFrictionInput(G=-100.0, rho=1000.0, mu=1e-3)
        assert inp.G == -100.0

    def test_rho_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeSinglePhaseFrictionInput(G=100.0, rho=0.0, mu=1e-3)

    def test_rho_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeSinglePhaseFrictionInput(G=100.0, rho=-1.0, mu=1e-3)

    def test_rho_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeSinglePhaseFrictionInput(G=100.0, rho=math.inf, mu=1e-3)

    def test_mu_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="mu"):
            PipeSinglePhaseFrictionInput(G=100.0, rho=1000.0, mu=0.0)

    def test_mu_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="mu"):
            PipeSinglePhaseFrictionInput(G=100.0, rho=1000.0, mu=-1e-3)

    def test_G_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="G"):
            PipeSinglePhaseFrictionInput(G=math.nan, rho=1000.0, mu=1e-3)

    def test_G_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="G"):
            PipeSinglePhaseFrictionInput(G=math.inf, rho=1000.0, mu=1e-3)

    def test_input_is_immutable(self) -> None:
        inp = PipeSinglePhaseFrictionInput(G=100.0, rho=1000.0, mu=1e-3)
        with pytest.raises((AttributeError, TypeError)):
            inp.G = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PipeFrictionResult structure
# ---------------------------------------------------------------------------


class TestPipeFrictionResultStructure:
    def _run(self, L: float = 1.0, G: float = 200.0) -> PipeFrictionResult:
        pipe = _make_pipe(L=L)
        return pipe.evaluate_single_phase_friction(_typical_inp(G=G), _CHURCHILL)

    def test_result_has_dp_dx_friction(self) -> None:
        result = self._run()
        assert hasattr(result, "dp_dx_friction")

    def test_result_has_delta_p_friction(self) -> None:
        result = self._run()
        assert hasattr(result, "delta_p_friction")

    def test_result_has_verdict(self) -> None:
        result = self._run()
        assert hasattr(result, "verdict")

    def test_result_has_metadata(self) -> None:
        result = self._run()
        assert hasattr(result, "metadata")

    def test_result_is_immutable(self) -> None:
        result = self._run()
        with pytest.raises((AttributeError, TypeError)):
            result.dp_dx_friction = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Core physics: gradient and total ΔP
# ---------------------------------------------------------------------------


class TestPipeFrictionPhysics:
    def test_gradient_positive_for_nonzero_flow(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.dp_dx_friction > 0.0

    def test_total_dp_positive_for_nonzero_flow(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.delta_p_friction > 0.0

    def test_total_dp_equals_gradient_times_length(self) -> None:
        L = 3.7
        pipe = _make_pipe(L=L)
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert math.isclose(result.delta_p_friction, result.dp_dx_friction * L, rel_tol=1e-12)

    def test_total_dp_equals_gradient_times_length_short_pipe(self) -> None:
        L = 0.05
        pipe = _make_pipe(L=L)
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert math.isclose(result.delta_p_friction, result.dp_dx_friction * L, rel_tol=1e-12)

    def test_zero_flow_returns_zero_friction(self) -> None:
        pipe = _make_pipe()
        inp = PipeSinglePhaseFrictionInput(G=0.0, rho=1200.0, mu=2e-4)
        result = pipe.evaluate_single_phase_friction(inp, _CHURCHILL)
        assert result.dp_dx_friction == 0.0
        assert result.delta_p_friction == 0.0

    def test_zero_flow_verdict_is_extrapolated(self) -> None:
        # Churchill documents G=0 as EXTRAPOLATED (Re=0 outside its domain).
        pipe = _make_pipe()
        inp = PipeSinglePhaseFrictionInput(G=0.0, rho=1200.0, mu=2e-4)
        result = pipe.evaluate_single_phase_friction(inp, _CHURCHILL)
        assert result.verdict.status is ValidityStatus.EXTRAPOLATED

    def test_higher_mass_flux_gives_higher_total_dp(self) -> None:
        pipe = _make_pipe()
        r_low = pipe.evaluate_single_phase_friction(_typical_inp(G=100.0), _CHURCHILL)
        r_high = pipe.evaluate_single_phase_friction(_typical_inp(G=400.0), _CHURCHILL)
        assert r_high.delta_p_friction > r_low.delta_p_friction

    def test_longer_pipe_gives_higher_total_dp(self) -> None:
        inp = _typical_inp(G=200.0)
        r_short = _make_pipe(L=1.0).evaluate_single_phase_friction(inp, _CHURCHILL)
        r_long = _make_pipe(L=5.0).evaluate_single_phase_friction(inp, _CHURCHILL)
        assert r_long.delta_p_friction > r_short.delta_p_friction

    def test_longer_pipe_does_not_change_gradient(self) -> None:
        # dp_dx is a local property; only delta_p scales with L.
        inp = _typical_inp(G=200.0)
        r_short = _make_pipe(L=1.0).evaluate_single_phase_friction(inp, _CHURCHILL)
        r_long = _make_pipe(L=5.0).evaluate_single_phase_friction(inp, _CHURCHILL)
        assert math.isclose(r_short.dp_dx_friction, r_long.dp_dx_friction, rel_tol=1e-12)

    def test_negative_G_gives_same_result_as_positive(self) -> None:
        pipe = _make_pipe()
        inp_pos = PipeSinglePhaseFrictionInput(G=200.0, rho=1200.0, mu=2e-4)
        inp_neg = PipeSinglePhaseFrictionInput(G=-200.0, rho=1200.0, mu=2e-4)
        r_pos = pipe.evaluate_single_phase_friction(inp_pos, _CHURCHILL)
        r_neg = pipe.evaluate_single_phase_friction(inp_neg, _CHURCHILL)
        assert r_pos.dp_dx_friction == r_neg.dp_dx_friction
        assert r_pos.delta_p_friction == r_neg.delta_p_friction


# ---------------------------------------------------------------------------
# Correlation validity verdict and metadata
# ---------------------------------------------------------------------------


class TestPipeFrictionVerdictAndMetadata:
    def test_in_envelope_verdict_for_typical_flow(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.verdict.status is ValidityStatus.IN_ENVELOPE

    def test_verdict_envelope_ref_has_correlation_name(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.verdict.envelope.correlation_name == "churchill_friction_gradient"

    def test_metadata_name_matches_churchill(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.metadata.name == "churchill_friction_gradient"

    def test_metadata_has_version(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.metadata.version

    def test_metadata_has_source(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(G=200.0), _CHURCHILL)
        assert result.metadata.source is not None

    def test_low_re_extrapolated(self) -> None:
        # Re = G * D_h / mu; very low Re (< 1) triggers EXTRAPOLATED.
        pipe = _make_pipe()
        inp = PipeSinglePhaseFrictionInput(G=1e-6, rho=1200.0, mu=2e-4)
        result = pipe.evaluate_single_phase_friction(inp, _CHURCHILL)
        assert result.verdict.status is ValidityStatus.EXTRAPOLATED


# ---------------------------------------------------------------------------
# Correlation role guard
# ---------------------------------------------------------------------------


class TestPipeFrictionCorrelationGuard:
    def test_rejects_non_correlation_instance(self) -> None:
        pipe = _make_pipe()
        with pytest.raises(TypeError, match="Correlation instance"):
            pipe.evaluate_single_phase_friction(_typical_inp(), "not_a_correlation")  # type: ignore[arg-type]

    def test_rejects_wrong_role_correlation(self) -> None:
        from mpl_sim.correlations.contract import (
            AnyFluid,
            Bound,
            BoundedQuantity,
            CorrelationInput,
            CorrelationOutput,
            SourceRef,
            ValidityEnvelope,
        )

        class _FakeTwoPhaseDP(Correlation):
            def role(self) -> CorrelationRole:
                return CorrelationRole.TWO_PHASE_DP

            def envelope(self) -> ValidityEnvelope:
                return ValidityEnvelope(
                    fluid_families=(AnyFluid(),),
                    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=1.0, max=1e8, units="-"),),
                    source=SourceRef(citation="test"),
                )

            def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
                raise NotImplementedError

        pipe = _make_pipe()
        with pytest.raises(ValueError, match="SINGLE_PHASE_DP"):
            pipe.evaluate_single_phase_friction(_typical_inp(), _FakeTwoPhaseDP())

    def test_rejects_none_as_correlation(self) -> None:
        pipe = _make_pipe()
        with pytest.raises(TypeError, match="Correlation instance"):
            pipe.evaluate_single_phase_friction(_typical_inp(), None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# No gravity / acceleration / heat transfer in result
# ---------------------------------------------------------------------------


class TestPipeFrictionNoExtraPhysics:
    def test_result_has_no_gravity_field(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert not hasattr(result, "dp_gravity")
        assert not hasattr(result, "delta_p_gravity")
        assert not hasattr(result, "gravity_term")

    def test_result_has_no_acceleration_field(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert not hasattr(result, "dp_acceleration")
        assert not hasattr(result, "delta_p_acceleration")
        assert not hasattr(result, "acceleration_term")

    def test_result_has_no_heat_transfer_field(self) -> None:
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert not hasattr(result, "htc")
        assert not hasattr(result, "HTC")
        assert not hasattr(result, "Nu")
        assert not hasattr(result, "heat_flux")

    def test_gradient_equals_friction_only(self) -> None:
        # With D_h=0.01, L=1, rho=1200, mu=2e-4, G=200 the result is
        # deterministic from Churchill (1977). We just verify it's finite
        # and positive — not checking for a specific number to avoid
        # coupling the test to the formula internals.
        pipe = _make_pipe()
        result = pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert math.isfinite(result.dp_dx_friction)
        assert result.dp_dx_friction > 0.0


# ---------------------------------------------------------------------------
# Immutability — pipe, geometry, discretization not mutated
# ---------------------------------------------------------------------------


class TestPipeFrictionImmutability:
    def test_pipe_not_mutated_after_call(self) -> None:
        pipe = _make_pipe()
        cid_before = pipe.component_id
        geom_before = pipe.geometry
        disc_before = pipe.discretization
        pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert pipe.component_id == cid_before
        assert pipe.geometry is geom_before
        assert pipe.discretization is disc_before

    def test_geometry_not_mutated_after_call(self) -> None:
        geom = _make_geometry()
        L_before = geom.L
        D_h_before = geom.D_h
        roughness_before = geom.roughness
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=geom,
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert geom.L == L_before
        assert geom.D_h == D_h_before
        assert geom.roughness == roughness_before

    def test_discretization_not_mutated_after_call(self) -> None:
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=4)
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=_make_geometry(),
            discretization=disc,
        )
        pipe.evaluate_single_phase_friction(_typical_inp(), _CHURCHILL)
        assert disc.mode is DiscretizationMode.UNIFORM
        assert disc.n_cells == 4

    def test_input_not_mutated_after_call(self) -> None:
        inp = _typical_inp(G=200.0)
        G_before = inp.G
        rho_before = inp.rho
        mu_before = inp.mu
        _make_pipe().evaluate_single_phase_friction(inp, _CHURCHILL)
        assert inp.G == G_before
        assert inp.rho == rho_before
        assert inp.mu == mu_before


# ---------------------------------------------------------------------------
# Import boundary — components package must not import CoolProp/network/solvers
# ---------------------------------------------------------------------------


def _import_lines_from(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestComponentsImportBoundary:
    def _pipe_imports(self) -> list[str]:
        import mpl_sim.components.pipe as pipe_mod

        assert pipe_mod.__file__ is not None
        return _import_lines_from(pipe_mod.__file__)

    def _init_imports(self) -> list[str]:
        import mpl_sim.components as comp_pkg

        assert comp_pkg.__file__ is not None
        return _import_lines_from(comp_pkg.__file__)

    def test_pipe_does_not_import_coolprop(self) -> None:
        for line in self._pipe_imports():
            assert (
                "coolprop" not in line.lower()
            ), f"pipe.py has forbidden CoolProp import: {line!r}"

    def test_pipe_does_not_import_network(self) -> None:
        for line in self._pipe_imports():
            assert "network" not in line, f"pipe.py has forbidden network import: {line!r}"

    def test_pipe_does_not_import_solvers(self) -> None:
        for line in self._pipe_imports():
            assert "solvers" not in line, f"pipe.py has forbidden solvers import: {line!r}"

    def test_pipe_does_not_import_properties(self) -> None:
        for line in self._pipe_imports():
            assert (
                "mpl_sim.properties" not in line
            ), f"pipe.py must not import properties/: {line!r}"

    def test_pipe_does_not_import_correlation_registry(self) -> None:
        for line in self._pipe_imports():
            assert (
                "correlations.registry" not in line
            ), f"pipe.py must not import CorrelationRegistry: {line!r}"

    def test_init_does_not_import_coolprop(self) -> None:
        for line in self._init_imports():
            assert (
                "coolprop" not in line.lower()
            ), f"components/__init__.py has forbidden CoolProp import: {line!r}"

    def test_init_does_not_import_network(self) -> None:
        for line in self._init_imports():
            assert (
                "network" not in line
            ), f"components/__init__.py has forbidden network import: {line!r}"

    def test_init_does_not_import_solvers(self) -> None:
        for line in self._init_imports():
            assert (
                "solvers" not in line
            ), f"components/__init__.py has forbidden solvers import: {line!r}"
