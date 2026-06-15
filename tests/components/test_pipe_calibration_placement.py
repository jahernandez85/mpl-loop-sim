"""Tests for Pipe calibration placement — Phase 6F.

Proves that friction_multiplier (R* seam) scales only the friction
contribution.  Gravity, acceleration, and the direct total are never
scaled independently — the total changes only because the friction term changes.

Verifies:
  - default friction_multiplier of 1.0 preserves previous total
  - multiplier > 1 scales only the friction contribution
  - multiplier < 1 scales only the friction contribution
  - multiplier == 0 suppresses only friction; gravity and acceleration unchanged
  - gravity is unchanged by any friction multiplier
  - acceleration is unchanged by any friction multiplier
  - total equals calibrated friction + gravity + acceleration
  - raw_friction is inspectable on PipeMechanicalPressureSummary
  - calibrated friction delta_p is inspectable on PipeMechanicalPressureSummary
  - friction_multiplier is stored on PipeMechanicalPressureSummary
  - calibrated = multiplier × raw for both delta_p_friction and dp_dx_friction
  - when multiplier == 1.0, calibrated equals raw
  - when multiplier == 0.0, calibrated is zero but raw is positive for nonzero flow
  - invalid friction_multiplier (NaN, inf) is rejected by PipeMechanicalPressureInput
  - negative friction_multiplier is rejected by PipeMechanicalPressureInput
  - method does not import CalibrationRegistry
  - method does not import fitting or optimization
  - method does not mutate Pipe, geometry, discretization, or inputs
  - existing full test suite passes (ensured by pytest collection)
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import (
    Pipe,
    PipeFrictionResult,
    PipeMechanicalPressureInput,
    PipeMechanicalPressureSummary,
)
from mpl_sim.correlations.single_phase_dp import ChurchillFrictionGradient
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CHURCHILL = ChurchillFrictionGradient()
_STANDARD_G = 9.80665


def _make_geometry(
    L: float = 5.0,
    delta_z: float = 0.0,
    D_h: float = 0.01,
) -> PipeGeometry:
    traj = StraightSegment(length=L, delta_z=delta_z)
    A = math.pi * (D_h / 2.0) ** 2
    return PipeGeometry(L=L, D_h=D_h, A=A, roughness=1e-5, trajectory=traj)


def _make_pipe(L: float = 5.0, delta_z: float = 0.0) -> Pipe:
    return Pipe(
        component_id=ComponentId("pipe_cal"),
        geometry=_make_geometry(L=L, delta_z=delta_z),
        discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
    )


def _mech_input(
    G: float = 200.0,
    rho: float = 1200.0,
    mu: float = 2e-4,
    G_in: float = 200.0,
    rho_in: float = 1200.0,
    G_out: float = 200.0,
    rho_out: float = 1200.0,
    g: float = _STANDARD_G,
    friction_multiplier: float = 1.0,
) -> PipeMechanicalPressureInput:
    return PipeMechanicalPressureInput(
        G=G,
        rho=rho,
        mu=mu,
        G_in=G_in,
        rho_in=rho_in,
        G_out=G_out,
        rho_out=rho_out,
        g=g,
        friction_multiplier=friction_multiplier,
    )


def _run(
    multiplier: float,
    pipe: Pipe | None = None,
    delta_z: float = 0.0,
    rho_in: float = 1200.0,
    rho_out: float = 1200.0,
) -> PipeMechanicalPressureSummary:
    p = pipe if pipe is not None else _make_pipe(delta_z=delta_z)
    inp = _mech_input(
        G_in=200.0,
        rho_in=rho_in,
        G_out=200.0,
        rho_out=rho_out,
        friction_multiplier=multiplier,
    )
    return p.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)


# ---------------------------------------------------------------------------
# Summary structure: new Phase 6F fields
# ---------------------------------------------------------------------------


class TestCalibrationPlacementSummaryStructure:
    def test_summary_has_raw_friction(self) -> None:
        result = _run(1.0)
        assert hasattr(result, "raw_friction")

    def test_summary_raw_friction_is_pipe_friction_result(self) -> None:
        result = _run(1.0)
        assert isinstance(result.raw_friction, PipeFrictionResult)

    def test_summary_has_friction_multiplier(self) -> None:
        result = _run(1.0)
        assert hasattr(result, "friction_multiplier")

    def test_summary_friction_multiplier_is_float(self) -> None:
        result = _run(2.5)
        assert isinstance(result.friction_multiplier, float)

    def test_summary_still_has_friction(self) -> None:
        result = _run(1.0)
        assert hasattr(result, "friction")

    def test_summary_still_has_gravity(self) -> None:
        result = _run(1.0)
        assert hasattr(result, "gravity")

    def test_summary_still_has_acceleration(self) -> None:
        result = _run(1.0)
        assert hasattr(result, "acceleration")

    def test_summary_still_has_delta_p_total(self) -> None:
        result = _run(1.0)
        assert hasattr(result, "delta_p_total")

    def test_summary_is_immutable(self) -> None:
        result = _run(1.0)
        with pytest.raises((AttributeError, TypeError)):
            result.friction_multiplier = 99.0  # type: ignore[misc]

    def test_raw_friction_is_immutable(self) -> None:
        result = _run(1.0)
        with pytest.raises((AttributeError, TypeError)):
            result.raw_friction.delta_p_friction = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Friction multiplier stored in summary
# ---------------------------------------------------------------------------


class TestCalibrationPlacementMultiplierStored:
    def test_default_multiplier_stored(self) -> None:
        result = _run(1.0)
        assert result.friction_multiplier == 1.0

    def test_custom_multiplier_stored(self) -> None:
        result = _run(2.5)
        assert result.friction_multiplier == 2.5

    def test_zero_multiplier_stored(self) -> None:
        result = _run(0.0)
        assert result.friction_multiplier == 0.0

    def test_fractional_multiplier_stored(self) -> None:
        result = _run(0.7)
        assert math.isclose(result.friction_multiplier, 0.7)


# ---------------------------------------------------------------------------
# Raw vs calibrated friction relationship
# ---------------------------------------------------------------------------


class TestCalibrationPlacementRawVsCalibrated:
    def test_default_multiplier_calibrated_equals_raw_dp(self) -> None:
        result = _run(1.0)
        assert math.isclose(
            result.friction.delta_p_friction,
            result.raw_friction.delta_p_friction,
            rel_tol=1e-12,
        )

    def test_default_multiplier_calibrated_equals_raw_dp_dx(self) -> None:
        result = _run(1.0)
        assert math.isclose(
            result.friction.dp_dx_friction,
            result.raw_friction.dp_dx_friction,
            rel_tol=1e-12,
        )

    def test_multiplier_two_calibrated_dp_equals_two_times_raw(self) -> None:
        result = _run(2.0)
        assert math.isclose(
            result.friction.delta_p_friction,
            2.0 * result.raw_friction.delta_p_friction,
            rel_tol=1e-12,
        )

    def test_multiplier_two_calibrated_dp_dx_equals_two_times_raw(self) -> None:
        result = _run(2.0)
        assert math.isclose(
            result.friction.dp_dx_friction,
            2.0 * result.raw_friction.dp_dx_friction,
            rel_tol=1e-12,
        )

    def test_multiplier_half_calibrated_dp_equals_half_raw(self) -> None:
        result = _run(0.5)
        assert math.isclose(
            result.friction.delta_p_friction,
            0.5 * result.raw_friction.delta_p_friction,
            rel_tol=1e-12,
        )

    def test_multiplier_zero_calibrated_dp_is_zero(self) -> None:
        result = _run(0.0)
        assert result.friction.delta_p_friction == 0.0

    def test_multiplier_zero_raw_dp_is_positive_for_nonzero_flow(self) -> None:
        result = _run(0.0)
        assert result.raw_friction.delta_p_friction > 0.0

    def test_raw_friction_verdict_preserved_under_multiplier(self) -> None:
        r1 = _run(1.0)
        r2 = _run(3.0)
        assert r1.raw_friction.verdict.status is r2.raw_friction.verdict.status

    def test_raw_friction_metadata_name_preserved_under_multiplier(self) -> None:
        r1 = _run(1.0)
        r2 = _run(5.0)
        assert r1.raw_friction.metadata.name == r2.raw_friction.metadata.name

    def test_calibrated_friction_times_multiplier_relation_holds_general(self) -> None:
        for m in (0.1, 0.5, 1.0, 1.5, 3.0, 10.0):
            result = _run(m)
            expected = m * result.raw_friction.delta_p_friction
            assert math.isclose(result.friction.delta_p_friction, expected, rel_tol=1e-12), (
                f"multiplier={m}: calibrated={result.friction.delta_p_friction} "
                f"expected={expected}"
            )


# ---------------------------------------------------------------------------
# Default multiplier of 1.0 preserves previous total
# ---------------------------------------------------------------------------


class TestCalibrationPlacementDefaultPreservesTotal:
    def test_default_total_equals_friction_plus_gravity_plus_accel(self) -> None:
        result = _run(1.0)
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_default_total_is_finite(self) -> None:
        result = _run(1.0)
        assert math.isfinite(result.delta_p_total)

    def test_default_total_with_elevation_equals_friction_plus_gravity(self) -> None:
        result = _run(1.0, delta_z=3.0)
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Multiplier scales only friction — gravity unchanged
# ---------------------------------------------------------------------------


class TestCalibrationPlacementGravityIndependence:
    def test_gravity_unchanged_by_multiplier_2(self) -> None:
        r1 = _run(1.0, delta_z=3.0)
        r2 = _run(2.0, delta_z=3.0)
        assert math.isclose(
            r1.gravity.delta_p_gravity,
            r2.gravity.delta_p_gravity,
            rel_tol=1e-12,
        )

    def test_gravity_unchanged_by_multiplier_zero(self) -> None:
        r1 = _run(1.0, delta_z=3.0)
        r2 = _run(0.0, delta_z=3.0)
        assert math.isclose(
            r1.gravity.delta_p_gravity,
            r2.gravity.delta_p_gravity,
            rel_tol=1e-12,
        )

    def test_gravity_unchanged_by_multiplier_large(self) -> None:
        r1 = _run(1.0, delta_z=2.0)
        r2 = _run(50.0, delta_z=2.0)
        assert math.isclose(
            r1.gravity.delta_p_gravity,
            r2.gravity.delta_p_gravity,
            rel_tol=1e-12,
        )

    def test_gravity_unchanged_for_several_multipliers(self) -> None:
        r_base = _run(1.0, delta_z=1.5)
        for m in (0.0, 0.3, 2.0, 7.0):
            r = _run(m, delta_z=1.5)
            assert math.isclose(
                r.gravity.delta_p_gravity,
                r_base.gravity.delta_p_gravity,
                rel_tol=1e-12,
            ), f"gravity changed for multiplier={m}"


# ---------------------------------------------------------------------------
# Multiplier scales only friction — acceleration unchanged
# ---------------------------------------------------------------------------


class TestCalibrationPlacementAccelerationIndependence:
    def _run_accel(self, multiplier: float) -> PipeMechanicalPressureSummary:
        pipe = _make_pipe()
        inp = _mech_input(
            G_in=200.0,
            rho_in=1200.0,
            G_out=200.0,
            rho_out=800.0,
            friction_multiplier=multiplier,
        )
        return pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)

    def test_acceleration_unchanged_by_multiplier_2(self) -> None:
        r1 = self._run_accel(1.0)
        r2 = self._run_accel(2.0)
        assert math.isclose(
            r1.acceleration.delta_p_acceleration,
            r2.acceleration.delta_p_acceleration,
            rel_tol=1e-12,
        )

    def test_acceleration_unchanged_by_multiplier_zero(self) -> None:
        r1 = self._run_accel(1.0)
        r2 = self._run_accel(0.0)
        assert math.isclose(
            r1.acceleration.delta_p_acceleration,
            r2.acceleration.delta_p_acceleration,
            rel_tol=1e-12,
        )

    def test_acceleration_unchanged_by_multiplier_large(self) -> None:
        r1 = self._run_accel(1.0)
        r2 = self._run_accel(20.0)
        assert math.isclose(
            r1.acceleration.delta_p_acceleration,
            r2.acceleration.delta_p_acceleration,
            rel_tol=1e-12,
        )

    def test_acceleration_unchanged_for_several_multipliers(self) -> None:
        r_base = self._run_accel(1.0)
        for m in (0.0, 0.5, 3.0, 10.0):
            r = self._run_accel(m)
            assert math.isclose(
                r.acceleration.delta_p_acceleration,
                r_base.acceleration.delta_p_acceleration,
                rel_tol=1e-12,
            ), f"acceleration changed for multiplier={m}"


# ---------------------------------------------------------------------------
# Total equals calibrated friction + gravity + acceleration
# ---------------------------------------------------------------------------


class TestCalibrationPlacementTotalEquality:
    def test_total_equals_sum_multiplier_1(self) -> None:
        result = _run(1.0)
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_total_equals_sum_multiplier_2(self) -> None:
        result = _run(2.0, delta_z=3.0)
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_total_equals_sum_multiplier_zero(self) -> None:
        result = _run(0.0, delta_z=2.0, rho_in=1200.0, rho_out=900.0)
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_total_equals_sum_for_several_multipliers(self) -> None:
        for m in (0.0, 0.5, 1.0, 2.0, 5.0):
            result = _run(m, delta_z=1.0, rho_in=1100.0, rho_out=900.0)
            expected = (
                result.friction.delta_p_friction
                + result.gravity.delta_p_gravity
                + result.acceleration.delta_p_acceleration
            )
            assert math.isclose(
                result.delta_p_total, expected, rel_tol=1e-12
            ), f"total != sum for multiplier={m}"

    def test_horizontal_no_accel_zero_multiplier_total_is_zero(self) -> None:
        # friction suppressed, gravity=0 (horizontal), accel=0 (equal densities)
        result = _run(0.0, delta_z=0.0, rho_in=1200.0, rho_out=1200.0)
        assert result.delta_p_total == 0.0

    def test_total_is_not_directly_scaled(self) -> None:
        # total changes only because the friction term changes, not via direct scaling
        r1 = _run(1.0, delta_z=2.0)
        r2 = _run(2.0, delta_z=2.0)
        # If total were directly scaled: r2.total == 2 * r1.total — this should NOT hold
        # (gravity makes total > friction, so scaling total != scaling only friction)
        expected_if_direct_scale = 2.0 * r1.delta_p_total
        assert not math.isclose(
            r2.delta_p_total, expected_if_direct_scale, rel_tol=1e-6
        ), "total appears to be directly scaled; calibration placement is incorrect"


# ---------------------------------------------------------------------------
# Negative multiplier rejected
# ---------------------------------------------------------------------------


class TestCalibrationPlacementNegativeMultiplierRejected:
    def test_negative_multiplier_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=-1.0)

    def test_small_negative_multiplier_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=-0.001)

    def test_large_negative_multiplier_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=-100.0)

    def test_nan_multiplier_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=math.nan)

    def test_inf_multiplier_still_rejected(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=math.inf)

    def test_zero_multiplier_is_allowed(self) -> None:
        inp = _mech_input(friction_multiplier=0.0)
        assert inp.friction_multiplier == 0.0


# ---------------------------------------------------------------------------
# Import boundary — no CalibrationRegistry, no fitting, no optimization
# ---------------------------------------------------------------------------


def _import_lines_from(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestCalibrationPlacementImportBoundary:
    def _pipe_imports(self) -> list[str]:
        import mpl_sim.components.pipe as pipe_mod

        assert pipe_mod.__file__ is not None
        return _import_lines_from(pipe_mod.__file__)

    def test_pipe_does_not_import_calibration_registry(self) -> None:
        for line in self._pipe_imports():
            assert (
                "CalibrationRegistry" not in line
            ), f"pipe.py must not import CalibrationRegistry: {line!r}"

    def test_pipe_does_not_import_calibration_package(self) -> None:
        for line in self._pipe_imports():
            assert (
                "mpl_sim.calibration" not in line
            ), f"pipe.py must not import calibration package: {line!r}"

    def test_pipe_does_not_import_fitting(self) -> None:
        for line in self._pipe_imports():
            assert "fitting" not in line.lower(), f"pipe.py must not import fitting: {line!r}"

    def test_pipe_does_not_import_optimization(self) -> None:
        for line in self._pipe_imports():
            assert "optim" not in line.lower(), f"pipe.py must not import optimization: {line!r}"

    def test_pipe_does_not_import_network(self) -> None:
        for line in self._pipe_imports():
            assert "network" not in line, f"pipe.py must not import network: {line!r}"

    def test_pipe_does_not_import_solvers(self) -> None:
        for line in self._pipe_imports():
            assert "solvers" not in line, f"pipe.py must not import solvers: {line!r}"

    def test_pipe_does_not_import_coolprop(self) -> None:
        for line in self._pipe_imports():
            assert "coolprop" not in line.lower(), f"pipe.py must not import CoolProp: {line!r}"


# ---------------------------------------------------------------------------
# Immutability — pipe, geometry, discretization, input not mutated
# ---------------------------------------------------------------------------


class TestCalibrationPlacementImmutability:
    def test_pipe_not_mutated(self) -> None:
        pipe = _make_pipe(delta_z=2.0)
        cid_before = pipe.component_id
        geom_before = pipe.geometry
        disc_before = pipe.discretization
        inp = _mech_input(friction_multiplier=3.0)
        pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert pipe.component_id == cid_before
        assert pipe.geometry is geom_before
        assert pipe.discretization is disc_before

    def test_input_not_mutated(self) -> None:
        inp = _mech_input(G=150.0, friction_multiplier=2.5)
        G_before = inp.G
        m_before = inp.friction_multiplier
        _make_pipe().evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert inp.G == G_before
        assert inp.friction_multiplier == m_before

    def test_geometry_not_mutated(self) -> None:
        geom = _make_geometry(L=4.0, delta_z=1.0)
        L_before = geom.L
        dz_before = geom.trajectory.delta_z
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=geom,
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe.evaluate_mechanical_pressure_summary(_mech_input(friction_multiplier=2.0), _CHURCHILL)
        assert geom.L == L_before
        assert geom.trajectory.delta_z == dz_before
