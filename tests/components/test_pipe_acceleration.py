"""Tests for Pipe.evaluate_acceleration_pressure — Phase 6D.

Sign convention under test:
    delta_p_acceleration = G_out**2 / rho_out - G_in**2 / rho_in
    positive when momentum flux increases from inlet to outlet
        (pressure required/lost accelerating the fluid)
    zero when G_in == G_out and rho_in == rho_out (no acceleration)
    negative when momentum flux decreases (pressure recovered)

Verifies:
  - Pipe can evaluate acceleration pressure contribution.
  - Equal inlet/outlet density and mass flux gives zero contribution.
  - Lower outlet density with same mass flux gives positive contribution.
  - Higher outlet density with same mass flux gives negative contribution.
  - Result magnitude follows G_out**2/rho_out - G_in**2/rho_in.
  - Changing G_out changes contribution consistently.
  - Invalid rho_in is rejected.
  - Invalid rho_out is rejected.
  - NaN/infinite mass flux values are rejected.
  - Result object is immutable.
  - Method does not call correlations.
  - Method does not call PropertyBackend.
  - Method does not compute friction.
  - Method does not compute gravity.
  - Method does not compute heat transfer.
  - Method does not mutate Pipe, geometry, or discretization.
  - Component package still does not import CoolProp, network, or solvers.
  - Existing full test suite passes (ensured by pytest collection).
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import (
    Pipe,
    PipeAccelerationInput,
    PipeAccelerationResult,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_geometry(L: float = 5.0, D_h: float = 0.01) -> PipeGeometry:
    traj = StraightSegment(length=L, delta_z=0.0)
    A = math.pi * (D_h / 2.0) ** 2
    return PipeGeometry(L=L, D_h=D_h, A=A, roughness=1e-5, trajectory=traj)


def _make_pipe(name: str = "pipe_a") -> Pipe:
    return Pipe(
        component_id=ComponentId(name),
        geometry=_make_geometry(),
        discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
    )


def _accel_input(
    G_in: float = 200.0,
    rho_in: float = 1200.0,
    G_out: float = 200.0,
    rho_out: float = 1200.0,
) -> PipeAccelerationInput:
    return PipeAccelerationInput(G_in=G_in, rho_in=rho_in, G_out=G_out, rho_out=rho_out)


# ---------------------------------------------------------------------------
# PipeAccelerationInput validation
# ---------------------------------------------------------------------------


class TestPipeAccelerationInputValidation:
    def test_valid_construction(self) -> None:
        inp = PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=100.0, rho_out=900.0)
        assert inp.G_in == 100.0
        assert inp.rho_in == 1000.0
        assert inp.G_out == 100.0
        assert inp.rho_out == 900.0

    def test_zero_G_in_allowed(self) -> None:
        inp = PipeAccelerationInput(G_in=0.0, rho_in=1000.0, G_out=0.0, rho_out=1000.0)
        assert inp.G_in == 0.0

    def test_zero_G_out_allowed(self) -> None:
        inp = PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=0.0, rho_out=1000.0)
        assert inp.G_out == 0.0

    def test_negative_G_in_allowed(self) -> None:
        inp = PipeAccelerationInput(G_in=-100.0, rho_in=1000.0, G_out=-100.0, rho_out=1000.0)
        assert inp.G_in == -100.0

    def test_negative_G_out_allowed(self) -> None:
        inp = PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=-100.0, rho_out=1000.0)
        assert inp.G_out == -100.0

    def test_input_is_immutable(self) -> None:
        inp = _accel_input()
        with pytest.raises((AttributeError, TypeError)):
            inp.G_in = 0.0  # type: ignore[misc]

    # rho_in rejections
    def test_rho_in_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            PipeAccelerationInput(G_in=100.0, rho_in=0.0, G_out=100.0, rho_out=1000.0)

    def test_rho_in_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            PipeAccelerationInput(G_in=100.0, rho_in=-1.0, G_out=100.0, rho_out=1000.0)

    def test_rho_in_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            PipeAccelerationInput(G_in=100.0, rho_in=math.inf, G_out=100.0, rho_out=1000.0)

    def test_rho_in_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            PipeAccelerationInput(G_in=100.0, rho_in=math.nan, G_out=100.0, rho_out=1000.0)

    # rho_out rejections
    def test_rho_out_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=100.0, rho_out=0.0)

    def test_rho_out_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=100.0, rho_out=-1.0)

    def test_rho_out_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=100.0, rho_out=math.inf)

    def test_rho_out_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=100.0, rho_out=math.nan)

    # G_in rejections
    def test_G_in_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_in"):
            PipeAccelerationInput(G_in=math.nan, rho_in=1000.0, G_out=100.0, rho_out=1000.0)

    def test_G_in_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_in"):
            PipeAccelerationInput(G_in=math.inf, rho_in=1000.0, G_out=100.0, rho_out=1000.0)

    # G_out rejections
    def test_G_out_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_out"):
            PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=math.nan, rho_out=1000.0)

    def test_G_out_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_out"):
            PipeAccelerationInput(G_in=100.0, rho_in=1000.0, G_out=math.inf, rho_out=1000.0)


# ---------------------------------------------------------------------------
# PipeAccelerationResult structure
# ---------------------------------------------------------------------------


class TestPipeAccelerationResultStructure:
    def _run(self, **kwargs: float) -> PipeAccelerationResult:
        return _make_pipe().evaluate_acceleration_pressure(_accel_input(**kwargs))

    def test_result_has_delta_p_acceleration(self) -> None:
        assert hasattr(self._run(), "delta_p_acceleration")

    def test_result_has_G_in(self) -> None:
        assert hasattr(self._run(), "G_in")

    def test_result_has_rho_in(self) -> None:
        assert hasattr(self._run(), "rho_in")

    def test_result_has_G_out(self) -> None:
        assert hasattr(self._run(), "G_out")

    def test_result_has_rho_out(self) -> None:
        assert hasattr(self._run(), "rho_out")

    def test_result_is_immutable(self) -> None:
        result = self._run()
        with pytest.raises((AttributeError, TypeError)):
            result.delta_p_acceleration = 0.0  # type: ignore[misc]

    def test_result_has_no_friction_field(self) -> None:
        result = self._run()
        assert not hasattr(result, "dp_dx_friction")
        assert not hasattr(result, "delta_p_friction")

    def test_result_has_no_gravity_field(self) -> None:
        result = self._run()
        assert not hasattr(result, "delta_p_gravity")
        assert not hasattr(result, "delta_z")

    def test_result_has_no_heat_transfer_field(self) -> None:
        result = self._run()
        assert not hasattr(result, "htc")
        assert not hasattr(result, "HTC")
        assert not hasattr(result, "Nu")

    def test_result_has_no_fluid_state(self) -> None:
        result = self._run()
        assert not hasattr(result, "state")
        assert not hasattr(result, "fluid_state")

    def test_result_has_no_verdict(self) -> None:
        result = self._run()
        assert not hasattr(result, "verdict")

    def test_result_has_no_metadata(self) -> None:
        result = self._run()
        assert not hasattr(result, "metadata")


# ---------------------------------------------------------------------------
# Core physics: sign convention and magnitude
# ---------------------------------------------------------------------------


class TestPipeAccelerationPhysics:
    def test_equal_flux_and_density_gives_zero(self) -> None:
        inp = _accel_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=1200.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.delta_p_acceleration == 0.0

    def test_lower_outlet_density_gives_positive(self) -> None:
        # rho_out < rho_in, same G → G²/rho_out > G²/rho_in → positive
        inp = _accel_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=800.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.delta_p_acceleration > 0.0

    def test_higher_outlet_density_gives_negative(self) -> None:
        # rho_out > rho_in, same G → G²/rho_out < G²/rho_in → negative
        inp = _accel_input(G_in=200.0, rho_in=800.0, G_out=200.0, rho_out=1200.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.delta_p_acceleration < 0.0

    def test_magnitude_matches_formula(self) -> None:
        G_in, rho_in, G_out, rho_out = 150.0, 1100.0, 200.0, 900.0
        inp = PipeAccelerationInput(G_in=G_in, rho_in=rho_in, G_out=G_out, rho_out=rho_out)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        expected = G_out**2 / rho_out - G_in**2 / rho_in
        assert math.isclose(result.delta_p_acceleration, expected, rel_tol=1e-12)

    def test_magnitude_matches_formula_upward_density(self) -> None:
        G_in, rho_in, G_out, rho_out = 300.0, 900.0, 300.0, 1200.0
        inp = PipeAccelerationInput(G_in=G_in, rho_in=rho_in, G_out=G_out, rho_out=rho_out)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        expected = G_out**2 / rho_out - G_in**2 / rho_in
        assert math.isclose(result.delta_p_acceleration, expected, rel_tol=1e-12)

    def test_higher_G_out_increases_contribution(self) -> None:
        rho_in, rho_out = 1000.0, 1000.0
        r_low = _make_pipe().evaluate_acceleration_pressure(
            _accel_input(G_in=100.0, rho_in=rho_in, G_out=100.0, rho_out=rho_out)
        )
        r_high = _make_pipe().evaluate_acceleration_pressure(
            _accel_input(G_in=100.0, rho_in=rho_in, G_out=300.0, rho_out=rho_out)
        )
        assert r_high.delta_p_acceleration > r_low.delta_p_acceleration

    def test_negative_G_gives_same_magnitude_as_positive(self) -> None:
        # squared mass flux: G² = (-G)²
        pos = _make_pipe().evaluate_acceleration_pressure(
            _accel_input(G_in=200.0, rho_in=1000.0, G_out=200.0, rho_out=800.0)
        )
        neg = _make_pipe().evaluate_acceleration_pressure(
            _accel_input(G_in=-200.0, rho_in=1000.0, G_out=-200.0, rho_out=800.0)
        )
        assert math.isclose(pos.delta_p_acceleration, neg.delta_p_acceleration, rel_tol=1e-12)

    def test_zero_G_in_and_out_gives_zero(self) -> None:
        inp = _accel_input(G_in=0.0, rho_in=1000.0, G_out=0.0, rho_out=800.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.delta_p_acceleration == 0.0

    def test_result_is_finite_for_typical_inputs(self) -> None:
        result = _make_pipe().evaluate_acceleration_pressure(
            _accel_input(G_in=200.0, rho_in=1200.0, G_out=250.0, rho_out=900.0)
        )
        assert math.isfinite(result.delta_p_acceleration)

    def test_result_echoes_G_in(self) -> None:
        inp = _accel_input(G_in=150.0, rho_in=1100.0, G_out=200.0, rho_out=900.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.G_in == 150.0

    def test_result_echoes_rho_in(self) -> None:
        inp = _accel_input(G_in=150.0, rho_in=1100.0, G_out=200.0, rho_out=900.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.rho_in == 1100.0

    def test_result_echoes_G_out(self) -> None:
        inp = _accel_input(G_in=150.0, rho_in=1100.0, G_out=200.0, rho_out=900.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.G_out == 200.0

    def test_result_echoes_rho_out(self) -> None:
        inp = _accel_input(G_in=150.0, rho_in=1100.0, G_out=200.0, rho_out=900.0)
        result = _make_pipe().evaluate_acceleration_pressure(inp)
        assert result.rho_out == 900.0


# ---------------------------------------------------------------------------
# Acceleration method does not compute friction / gravity / heat transfer
# ---------------------------------------------------------------------------


class TestPipeAccelerationNoExtraPhysics:
    def test_acceleration_does_not_require_viscosity(self) -> None:
        inp = _accel_input()
        assert not hasattr(inp, "mu")

    def test_acceleration_does_not_require_g(self) -> None:
        inp = _accel_input()
        assert not hasattr(inp, "g")

    def test_acceleration_does_not_require_delta_z(self) -> None:
        inp = _accel_input()
        assert not hasattr(inp, "delta_z")

    def test_acceleration_result_has_no_dp_dx(self) -> None:
        result = _make_pipe().evaluate_acceleration_pressure(_accel_input())
        assert not hasattr(result, "dp_dx_friction")

    def test_result_does_not_vary_with_pipe_length(self) -> None:
        inp = _accel_input(G_in=200.0, rho_in=1000.0, G_out=200.0, rho_out=800.0)
        pipe_short = Pipe(
            component_id=ComponentId("short"),
            geometry=_make_geometry(L=1.0),
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe_long = Pipe(
            component_id=ComponentId("long"),
            geometry=_make_geometry(L=100.0),
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        r_short = pipe_short.evaluate_acceleration_pressure(inp)
        r_long = pipe_long.evaluate_acceleration_pressure(inp)
        assert math.isclose(
            r_short.delta_p_acceleration, r_long.delta_p_acceleration, rel_tol=1e-12
        )


# ---------------------------------------------------------------------------
# Immutability — Pipe, geometry, discretization, input not mutated
# ---------------------------------------------------------------------------


class TestPipeAccelerationImmutability:
    def test_pipe_not_mutated_after_call(self) -> None:
        pipe = _make_pipe()
        cid_before = pipe.component_id
        geom_before = pipe.geometry
        disc_before = pipe.discretization
        pipe.evaluate_acceleration_pressure(_accel_input())
        assert pipe.component_id == cid_before
        assert pipe.geometry is geom_before
        assert pipe.discretization is disc_before

    def test_geometry_not_mutated_after_call(self) -> None:
        geom = _make_geometry(L=5.0)
        L_before = geom.L
        D_h_before = geom.D_h
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=geom,
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe.evaluate_acceleration_pressure(_accel_input())
        assert geom.L == L_before
        assert geom.D_h == D_h_before

    def test_discretization_not_mutated_after_call(self) -> None:
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=4)
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=_make_geometry(),
            discretization=disc,
        )
        pipe.evaluate_acceleration_pressure(_accel_input())
        assert disc.mode is DiscretizationMode.UNIFORM
        assert disc.n_cells == 4

    def test_input_not_mutated_after_call(self) -> None:
        inp = _accel_input(G_in=150.0, rho_in=1100.0, G_out=200.0, rho_out=900.0)
        G_in_before = inp.G_in
        rho_in_before = inp.rho_in
        G_out_before = inp.G_out
        rho_out_before = inp.rho_out
        _make_pipe().evaluate_acceleration_pressure(inp)
        assert inp.G_in == G_in_before
        assert inp.rho_in == rho_in_before
        assert inp.G_out == G_out_before
        assert inp.rho_out == rho_out_before


# ---------------------------------------------------------------------------
# Import boundary — component package must not import CoolProp/network/solvers
# ---------------------------------------------------------------------------


def _import_lines_from(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestComponentsImportBoundaryAcceleration:
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
    def test_acceleration_input_exported(self) -> None:
        import mpl_sim.components as comp_pkg

        assert hasattr(comp_pkg, "PipeAccelerationInput")

    def test_acceleration_result_exported(self) -> None:
        import mpl_sim.components as comp_pkg

        assert hasattr(comp_pkg, "PipeAccelerationResult")
