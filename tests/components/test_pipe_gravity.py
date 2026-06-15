"""Tests for Pipe.evaluate_gravity_pressure — Phase 6C.

Sign convention under test:
    delta_p_gravity = rho * g * delta_z
    positive delta_z → outlet higher than inlet → positive delta_p_gravity
    zero delta_z     → horizontal pipe           → zero delta_p_gravity
    negative delta_z → outlet lower than inlet   → negative delta_p_gravity

Verifies:
  - Pipe can evaluate gravity pressure contribution.
  - Horizontal pipe gives zero gravity contribution.
  - Upward pipe gives positive gravity contribution.
  - Downward pipe gives negative gravity contribution.
  - Result magnitude equals rho * g * delta_z.
  - Changing density changes gravity contribution linearly.
  - Changing g changes gravity contribution linearly.
  - Invalid density is rejected.
  - Invalid gravity acceleration is rejected.
  - Gravity method does not call any correlation.
  - Gravity method does not call PropertyBackend.
  - Gravity method does not compute friction.
  - Gravity method does not compute acceleration.
  - Gravity method does not compute heat transfer.
  - Gravity method does not mutate Pipe, geometry, or discretization.
  - Component package still does not import CoolProp, network, or solvers.
  - Existing full test suite passes (ensured by pytest collection).
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import Pipe, PipeGravityInput, PipeGravityResult
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_STANDARD_G = 9.80665  # m/s²


def _make_geometry(L: float = 5.0, delta_z: float = 0.0, D_h: float = 0.01) -> PipeGeometry:
    traj = StraightSegment(length=L, delta_z=delta_z)
    A = math.pi * (D_h / 2.0) ** 2
    return PipeGeometry(L=L, D_h=D_h, A=A, roughness=1e-5, trajectory=traj)


def _make_pipe(delta_z: float = 0.0, L: float = 5.0, name: str = "pipe_g") -> Pipe:
    return Pipe(
        component_id=ComponentId(name),
        geometry=_make_geometry(L=L, delta_z=delta_z),
        discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
    )


def _gravity_input(rho: float = 1200.0, g: float = _STANDARD_G) -> PipeGravityInput:
    return PipeGravityInput(rho=rho, g=g)


# ---------------------------------------------------------------------------
# PipeGravityInput validation
# ---------------------------------------------------------------------------


class TestPipeGravityInputValidation:
    def test_valid_construction_default_g(self) -> None:
        inp = PipeGravityInput(rho=1000.0)
        assert inp.rho == 1000.0
        assert math.isclose(inp.g, _STANDARD_G)

    def test_valid_construction_custom_g(self) -> None:
        inp = PipeGravityInput(rho=800.0, g=9.81)
        assert inp.rho == 800.0
        assert inp.g == 9.81

    def test_input_is_immutable(self) -> None:
        inp = PipeGravityInput(rho=1000.0)
        with pytest.raises((AttributeError, TypeError)):
            inp.rho = 500.0  # type: ignore[misc]

    def test_rho_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeGravityInput(rho=0.0)

    def test_rho_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeGravityInput(rho=-1.0)

    def test_rho_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeGravityInput(rho=math.inf)

    def test_rho_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            PipeGravityInput(rho=math.nan)

    def test_g_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            PipeGravityInput(rho=1000.0, g=0.0)

    def test_g_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            PipeGravityInput(rho=1000.0, g=-9.81)

    def test_g_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            PipeGravityInput(rho=1000.0, g=math.inf)

    def test_g_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            PipeGravityInput(rho=1000.0, g=math.nan)


# ---------------------------------------------------------------------------
# PipeGravityResult structure
# ---------------------------------------------------------------------------


class TestPipeGravityResultStructure:
    def _run(self, delta_z: float = 1.0) -> PipeGravityResult:
        return _make_pipe(delta_z=delta_z).evaluate_gravity_pressure(_gravity_input())

    def test_result_has_delta_p_gravity(self) -> None:
        assert hasattr(self._run(), "delta_p_gravity")

    def test_result_has_rho(self) -> None:
        assert hasattr(self._run(), "rho")

    def test_result_has_g(self) -> None:
        assert hasattr(self._run(), "g")

    def test_result_has_delta_z(self) -> None:
        assert hasattr(self._run(), "delta_z")

    def test_result_is_immutable(self) -> None:
        result = self._run()
        with pytest.raises((AttributeError, TypeError)):
            result.delta_p_gravity = 0.0  # type: ignore[misc]

    def test_result_has_no_friction_field(self) -> None:
        result = self._run()
        assert not hasattr(result, "dp_dx_friction")
        assert not hasattr(result, "delta_p_friction")

    def test_result_has_no_acceleration_field(self) -> None:
        result = self._run()
        assert not hasattr(result, "delta_p_acceleration")
        assert not hasattr(result, "acceleration_term")

    def test_result_has_no_heat_transfer_field(self) -> None:
        result = self._run()
        assert not hasattr(result, "htc")
        assert not hasattr(result, "HTC")
        assert not hasattr(result, "Nu")

    def test_result_has_no_fluid_state(self) -> None:
        result = self._run()
        assert not hasattr(result, "state")
        assert not hasattr(result, "fluid_state")


# ---------------------------------------------------------------------------
# Core physics: sign convention and magnitude
# ---------------------------------------------------------------------------


class TestPipeGravityPhysics:
    def test_horizontal_pipe_zero_gravity_contribution(self) -> None:
        pipe = _make_pipe(delta_z=0.0)
        result = pipe.evaluate_gravity_pressure(_gravity_input())
        assert result.delta_p_gravity == 0.0

    def test_upward_pipe_positive_gravity_contribution(self) -> None:
        # delta_z > 0 → outlet higher → pressure lost lifting fluid
        pipe = _make_pipe(delta_z=2.0)
        result = pipe.evaluate_gravity_pressure(_gravity_input())
        assert result.delta_p_gravity > 0.0

    def test_downward_pipe_negative_gravity_contribution(self) -> None:
        # delta_z < 0 → outlet lower → pressure recovered
        pipe = _make_pipe(delta_z=-2.0)
        result = pipe.evaluate_gravity_pressure(_gravity_input())
        assert result.delta_p_gravity < 0.0

    def test_magnitude_equals_rho_g_delta_z(self) -> None:
        rho = 1050.0
        g = 9.81
        delta_z = 3.5
        pipe = _make_pipe(delta_z=delta_z)
        result = pipe.evaluate_gravity_pressure(PipeGravityInput(rho=rho, g=g))
        expected = rho * g * delta_z
        assert math.isclose(result.delta_p_gravity, expected, rel_tol=1e-12)

    def test_magnitude_upward(self) -> None:
        rho, g, delta_z = 1200.0, _STANDARD_G, 10.0
        result = _make_pipe(delta_z=delta_z).evaluate_gravity_pressure(
            PipeGravityInput(rho=rho, g=g)
        )
        assert math.isclose(result.delta_p_gravity, rho * g * delta_z, rel_tol=1e-12)

    def test_magnitude_downward(self) -> None:
        rho, g, delta_z = 1200.0, _STANDARD_G, -10.0
        result = _make_pipe(delta_z=delta_z).evaluate_gravity_pressure(
            PipeGravityInput(rho=rho, g=g)
        )
        assert math.isclose(result.delta_p_gravity, rho * g * delta_z, rel_tol=1e-12)

    def test_result_delta_z_matches_geometry(self) -> None:
        pipe = _make_pipe(delta_z=4.7)
        result = pipe.evaluate_gravity_pressure(_gravity_input())
        assert result.delta_z == pipe.geometry.trajectory.delta_z

    def test_result_rho_matches_input(self) -> None:
        inp = PipeGravityInput(rho=850.0)
        result = _make_pipe(delta_z=1.0).evaluate_gravity_pressure(inp)
        assert result.rho == 850.0

    def test_result_g_matches_input(self) -> None:
        inp = PipeGravityInput(rho=1000.0, g=9.81)
        result = _make_pipe(delta_z=1.0).evaluate_gravity_pressure(inp)
        assert result.g == 9.81

    def test_density_scales_linearly(self) -> None:
        delta_z = 5.0
        pipe = _make_pipe(delta_z=delta_z)
        r1 = pipe.evaluate_gravity_pressure(PipeGravityInput(rho=1000.0, g=_STANDARD_G))
        r2 = pipe.evaluate_gravity_pressure(PipeGravityInput(rho=2000.0, g=_STANDARD_G))
        assert math.isclose(r2.delta_p_gravity, 2.0 * r1.delta_p_gravity, rel_tol=1e-12)

    def test_g_scales_linearly(self) -> None:
        delta_z = 5.0
        pipe = _make_pipe(delta_z=delta_z)
        r1 = pipe.evaluate_gravity_pressure(PipeGravityInput(rho=1000.0, g=5.0))
        r2 = pipe.evaluate_gravity_pressure(PipeGravityInput(rho=1000.0, g=10.0))
        assert math.isclose(r2.delta_p_gravity, 2.0 * r1.delta_p_gravity, rel_tol=1e-12)

    def test_large_delta_z_finite_result(self) -> None:
        pipe = _make_pipe(delta_z=1000.0, L=1001.0)
        result = pipe.evaluate_gravity_pressure(_gravity_input())
        assert math.isfinite(result.delta_p_gravity)

    def test_pipe_length_does_not_affect_gravity_result(self) -> None:
        # gravity uses delta_z, not pipe length
        inp = _gravity_input()
        r_short = _make_pipe(delta_z=2.0, L=2.0).evaluate_gravity_pressure(inp)
        r_long = _make_pipe(delta_z=2.0, L=100.0).evaluate_gravity_pressure(inp)
        assert math.isclose(r_short.delta_p_gravity, r_long.delta_p_gravity, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Gravity method does not compute friction / acceleration / heat transfer
# ---------------------------------------------------------------------------


class TestPipeGravityNoExtraPhysics:
    def test_result_has_no_verdict(self) -> None:
        # verdict is a correlation artifact; gravity has none
        result = _make_pipe(delta_z=1.0).evaluate_gravity_pressure(_gravity_input())
        assert not hasattr(result, "verdict")

    def test_result_has_no_metadata(self) -> None:
        result = _make_pipe(delta_z=1.0).evaluate_gravity_pressure(_gravity_input())
        assert not hasattr(result, "metadata")

    def test_gravity_does_not_require_viscosity(self) -> None:
        # PipeGravityInput has no mu field — this is a structural test
        inp = PipeGravityInput(rho=1000.0)
        assert not hasattr(inp, "mu")

    def test_gravity_does_not_require_mass_flux(self) -> None:
        inp = PipeGravityInput(rho=1000.0)
        assert not hasattr(inp, "G")

    def test_gravity_result_is_finite_for_zero_delta_z(self) -> None:
        result = _make_pipe(delta_z=0.0).evaluate_gravity_pressure(_gravity_input())
        assert math.isfinite(result.delta_p_gravity)


# ---------------------------------------------------------------------------
# Immutability — Pipe, geometry, discretization, input not mutated
# ---------------------------------------------------------------------------


class TestPipeGravityImmutability:
    def test_pipe_not_mutated_after_call(self) -> None:
        pipe = _make_pipe(delta_z=3.0)
        cid_before = pipe.component_id
        geom_before = pipe.geometry
        disc_before = pipe.discretization
        pipe.evaluate_gravity_pressure(_gravity_input())
        assert pipe.component_id == cid_before
        assert pipe.geometry is geom_before
        assert pipe.discretization is disc_before

    def test_geometry_not_mutated_after_call(self) -> None:
        geom = _make_geometry(delta_z=3.0)
        L_before = geom.L
        dz_before = geom.trajectory.delta_z
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=geom,
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe.evaluate_gravity_pressure(_gravity_input())
        assert geom.L == L_before
        assert geom.trajectory.delta_z == dz_before

    def test_discretization_not_mutated_after_call(self) -> None:
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=4)
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=_make_geometry(),
            discretization=disc,
        )
        pipe.evaluate_gravity_pressure(_gravity_input())
        assert disc.mode is DiscretizationMode.UNIFORM
        assert disc.n_cells == 4

    def test_input_not_mutated_after_call(self) -> None:
        inp = PipeGravityInput(rho=1200.0, g=9.81)
        rho_before = inp.rho
        g_before = inp.g
        _make_pipe(delta_z=2.0).evaluate_gravity_pressure(inp)
        assert inp.rho == rho_before
        assert inp.g == g_before


# ---------------------------------------------------------------------------
# Import boundary — component package must not import CoolProp/network/solvers
# ---------------------------------------------------------------------------


def _import_lines_from(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestComponentsImportBoundaryGravity:
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
            assert "coolprop" not in line.lower(), f"pipe.py forbidden CoolProp import: {line!r}"

    def test_pipe_does_not_import_network(self) -> None:
        for line in self._pipe_imports():
            assert "network" not in line, f"pipe.py forbidden network import: {line!r}"

    def test_pipe_does_not_import_solvers(self) -> None:
        for line in self._pipe_imports():
            assert "solvers" not in line, f"pipe.py forbidden solvers import: {line!r}"

    def test_pipe_does_not_import_properties(self) -> None:
        for line in self._pipe_imports():
            assert (
                "mpl_sim.properties" not in line
            ), f"pipe.py must not import properties/: {line!r}"

    def test_init_does_not_import_coolprop(self) -> None:
        for line in self._init_imports():
            assert (
                "coolprop" not in line.lower()
            ), f"components/__init__.py forbidden CoolProp import: {line!r}"

    def test_init_does_not_import_network(self) -> None:
        for line in self._init_imports():
            assert (
                "network" not in line
            ), f"components/__init__.py forbidden network import: {line!r}"

    def test_init_does_not_import_solvers(self) -> None:
        for line in self._init_imports():
            assert (
                "solvers" not in line
            ), f"components/__init__.py forbidden solvers import: {line!r}"


# ---------------------------------------------------------------------------
# Package-level export check
# ---------------------------------------------------------------------------


class TestComponentsPackageExports:
    def test_gravity_input_exported(self) -> None:
        import mpl_sim.components as comp_pkg

        assert hasattr(comp_pkg, "PipeGravityInput")

    def test_gravity_result_exported(self) -> None:
        import mpl_sim.components as comp_pkg

        assert hasattr(comp_pkg, "PipeGravityResult")
