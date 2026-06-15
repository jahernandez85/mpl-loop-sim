"""Tests for Pipe.evaluate_mechanical_pressure_summary — Phase 6E.

Total:
    delta_p_total = delta_p_friction + delta_p_gravity + delta_p_acceleration

Verifies:
  - Pipe can evaluate mechanical pressure summary.
  - Summary result is immutable.
  - Summary contains separate friction, gravity, and acceleration results.
  - Total equals friction + gravity + acceleration.
  - Friction validity verdict is preserved inside the summary.
  - Friction metadata is preserved inside the summary.
  - Summary does not hide individual terms.
  - Horizontal constant-density no-acceleration case reduces to friction only.
  - Zero-flow horizontal case gives zero total.
  - Upward pipe adds positive gravity contribution to total.
  - Downward pipe subtracts gravity contribution from total.
  - Acceleration contribution affects total independently of friction and gravity.
  - Changing pipe length changes friction total but not gravity or acceleration.
  - Method rejects invalid density/viscosity/gravity inputs.
  - Method rejects non-SINGLE_PHASE_DP correlation.
  - Method does not call PropertyBackend.
  - Method does not call CoolProp.
  - Method does not create network or solver objects.
  - Method does not mutate Pipe, geometry, discretization, or input objects.
  - Optional friction multiplier scales only friction, not gravity or acceleration.
  - Existing full test suite passes (ensured by pytest collection).
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.components.base import ComponentId
from mpl_sim.components.pipe import (
    Pipe,
    PipeMechanicalPressureInput,
    PipeMechanicalPressureSummary,
)
from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
)
from mpl_sim.correlations.single_phase_dp import ChurchillFrictionGradient
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.geometry.primitives import PipeGeometry, StraightSegment

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_CHURCHILL = ChurchillFrictionGradient()
_STANDARD_G = 9.80665  # m/s²


def _make_geometry(
    L: float = 5.0,
    delta_z: float = 0.0,
    D_h: float = 0.01,
) -> PipeGeometry:
    traj = StraightSegment(length=L, delta_z=delta_z)
    A = math.pi * (D_h / 2.0) ** 2
    return PipeGeometry(L=L, D_h=D_h, A=A, roughness=1e-5, trajectory=traj)


def _make_pipe(
    L: float = 5.0,
    delta_z: float = 0.0,
    name: str = "pipe_mech",
) -> Pipe:
    return Pipe(
        component_id=ComponentId(name),
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


# ---------------------------------------------------------------------------
# PipeMechanicalPressureInput validation
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureInputValidation:
    def test_valid_construction_defaults(self) -> None:
        inp = PipeMechanicalPressureInput(
            G=200.0,
            rho=1200.0,
            mu=2e-4,
            G_in=200.0,
            rho_in=1200.0,
            G_out=200.0,
            rho_out=1200.0,
        )
        assert inp.G == 200.0
        assert inp.rho == 1200.0
        assert inp.mu == 2e-4
        assert math.isclose(inp.g, _STANDARD_G)
        assert inp.friction_multiplier == 1.0

    def test_valid_construction_explicit_all(self) -> None:
        inp = _mech_input(g=9.81, friction_multiplier=2.0)
        assert inp.g == 9.81
        assert inp.friction_multiplier == 2.0

    def test_input_is_immutable(self) -> None:
        inp = _mech_input()
        with pytest.raises((AttributeError, TypeError)):
            inp.G = 0.0  # type: ignore[misc]

    def test_zero_G_allowed(self) -> None:
        inp = _mech_input(G=0.0)
        assert inp.G == 0.0

    def test_negative_G_allowed(self) -> None:
        inp = _mech_input(G=-100.0)
        assert inp.G == -100.0

    def test_zero_G_in_and_out_allowed(self) -> None:
        inp = _mech_input(G_in=0.0, G_out=0.0)
        assert inp.G_in == 0.0

    def test_friction_multiplier_zero_allowed(self) -> None:
        inp = _mech_input(friction_multiplier=0.0)
        assert inp.friction_multiplier == 0.0

    # rho rejections
    def test_rho_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            _mech_input(rho=0.0)

    def test_rho_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            _mech_input(rho=-1.0)

    def test_rho_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            _mech_input(rho=math.inf)

    def test_rho_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho"):
            _mech_input(rho=math.nan)

    # mu rejections
    def test_mu_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="mu"):
            _mech_input(mu=0.0)

    def test_mu_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="mu"):
            _mech_input(mu=-1e-4)

    def test_mu_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="mu"):
            _mech_input(mu=math.inf)

    # g rejections
    def test_g_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            _mech_input(g=0.0)

    def test_g_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            _mech_input(g=-9.81)

    def test_g_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            _mech_input(g=math.inf)

    def test_g_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="g"):
            _mech_input(g=math.nan)

    # G rejections
    def test_G_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="G"):
            _mech_input(G=math.nan)

    def test_G_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="G"):
            _mech_input(G=math.inf)

    # rho_in rejections
    def test_rho_in_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            _mech_input(rho_in=0.0)

    def test_rho_in_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            _mech_input(rho_in=-1.0)

    def test_rho_in_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_in"):
            _mech_input(rho_in=math.nan)

    # rho_out rejections
    def test_rho_out_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            _mech_input(rho_out=0.0)

    def test_rho_out_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            _mech_input(rho_out=-1.0)

    def test_rho_out_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="rho_out"):
            _mech_input(rho_out=math.nan)

    # G_in / G_out rejections
    def test_G_in_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_in"):
            _mech_input(G_in=math.nan)

    def test_G_in_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_in"):
            _mech_input(G_in=math.inf)

    def test_G_out_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_out"):
            _mech_input(G_out=math.nan)

    def test_G_out_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="G_out"):
            _mech_input(G_out=math.inf)

    # friction_multiplier rejections
    def test_friction_multiplier_nan_rejected(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=math.nan)

    def test_friction_multiplier_inf_rejected(self) -> None:
        with pytest.raises(ValueError, match="friction_multiplier"):
            _mech_input(friction_multiplier=math.inf)


# ---------------------------------------------------------------------------
# PipeMechanicalPressureSummary structure
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureSummaryStructure:
    def _run(self) -> PipeMechanicalPressureSummary:
        return _make_pipe().evaluate_mechanical_pressure_summary(_mech_input(), _CHURCHILL)

    def test_result_has_friction(self) -> None:
        assert hasattr(self._run(), "friction")

    def test_result_has_gravity(self) -> None:
        assert hasattr(self._run(), "gravity")

    def test_result_has_acceleration(self) -> None:
        assert hasattr(self._run(), "acceleration")

    def test_result_has_delta_p_total(self) -> None:
        assert hasattr(self._run(), "delta_p_total")

    def test_result_is_immutable(self) -> None:
        result = self._run()
        with pytest.raises((AttributeError, TypeError)):
            result.delta_p_total = 0.0  # type: ignore[misc]

    def test_friction_sub_result_is_immutable(self) -> None:
        result = self._run()
        with pytest.raises((AttributeError, TypeError)):
            result.friction.delta_p_friction = 0.0  # type: ignore[misc]

    def test_summary_does_not_hide_friction_dp_dx(self) -> None:
        result = self._run()
        assert hasattr(result.friction, "dp_dx_friction")

    def test_summary_does_not_hide_friction_verdict(self) -> None:
        result = self._run()
        assert hasattr(result.friction, "verdict")

    def test_summary_does_not_hide_friction_metadata(self) -> None:
        result = self._run()
        assert hasattr(result.friction, "metadata")

    def test_summary_does_not_hide_gravity_delta_z(self) -> None:
        result = self._run()
        assert hasattr(result.gravity, "delta_z")

    def test_summary_does_not_hide_acceleration_G_in(self) -> None:
        result = self._run()
        assert hasattr(result.acceleration, "G_in")

    def test_result_type_is_summary(self) -> None:
        result = self._run()
        assert isinstance(result, PipeMechanicalPressureSummary)


# ---------------------------------------------------------------------------
# Total equals sum of three contributions
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureSummaryTotal:
    def _run(
        self,
        pipe: Pipe | None = None,
        inp: PipeMechanicalPressureInput | None = None,
    ) -> PipeMechanicalPressureSummary:
        p = pipe if pipe is not None else _make_pipe()
        i = inp if inp is not None else _mech_input()
        return p.evaluate_mechanical_pressure_summary(i, _CHURCHILL)

    def test_total_equals_sum_horizontal_no_accel(self) -> None:
        result = self._run()
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_total_equals_sum_upward_pipe(self) -> None:
        result = self._run(pipe=_make_pipe(delta_z=3.0))
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_total_equals_sum_with_acceleration(self) -> None:
        inp = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=900.0)
        result = self._run(inp=inp)
        expected = (
            result.friction.delta_p_friction
            + result.gravity.delta_p_gravity
            + result.acceleration.delta_p_acceleration
        )
        assert math.isclose(result.delta_p_total, expected, rel_tol=1e-12)

    def test_total_is_finite_for_typical_inputs(self) -> None:
        result = self._run()
        assert math.isfinite(result.delta_p_total)


# ---------------------------------------------------------------------------
# Physics: horizontal constant-density no-acceleration case
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureHorizontalNoAcceleration:
    def test_horizontal_no_accel_gravity_is_zero(self) -> None:
        # delta_z = 0, G_in = G_out, rho_in = rho_out
        pipe = _make_pipe(delta_z=0.0)
        inp = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=1200.0)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert result.gravity.delta_p_gravity == 0.0

    def test_horizontal_no_accel_acceleration_is_zero(self) -> None:
        pipe = _make_pipe(delta_z=0.0)
        inp = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=1200.0)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert result.acceleration.delta_p_acceleration == 0.0

    def test_horizontal_no_accel_total_equals_friction(self) -> None:
        pipe = _make_pipe(delta_z=0.0)
        inp = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=1200.0)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert math.isclose(result.delta_p_total, result.friction.delta_p_friction, rel_tol=1e-12)

    def test_horizontal_no_accel_friction_is_positive(self) -> None:
        pipe = _make_pipe(delta_z=0.0)
        inp = _mech_input(G=200.0, G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=1200.0)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert result.friction.delta_p_friction > 0.0


# ---------------------------------------------------------------------------
# Physics: zero-flow horizontal case
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureZeroFlow:
    def test_zero_flow_horizontal_total_is_zero(self) -> None:
        # G=0, delta_z=0, G_in=G_out=0 → all three contributions are zero
        pipe = _make_pipe(delta_z=0.0)
        inp = _mech_input(G=0.0, G_in=0.0, rho_in=1200.0, G_out=0.0, rho_out=1200.0)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert result.delta_p_total == 0.0

    def test_zero_flow_horizontal_friction_is_zero(self) -> None:
        pipe = _make_pipe(delta_z=0.0)
        inp = _mech_input(G=0.0, G_in=0.0, rho_in=1200.0, G_out=0.0, rho_out=1200.0)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert result.friction.delta_p_friction == 0.0


# ---------------------------------------------------------------------------
# Physics: upward and downward pipe gravity
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureGravityDirection:
    def _run_no_accel(
        self,
        delta_z: float,
        rho: float = 1200.0,
    ) -> PipeMechanicalPressureSummary:
        pipe = _make_pipe(delta_z=delta_z)
        # Use equal rho_in / rho_out so acceleration is zero
        inp = _mech_input(rho=rho, G_in=200.0, rho_in=rho, G_out=200.0, rho_out=rho)
        return pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)

    def test_upward_pipe_gravity_is_positive(self) -> None:
        result = self._run_no_accel(delta_z=3.0)
        assert result.gravity.delta_p_gravity > 0.0

    def test_upward_pipe_total_greater_than_friction_alone(self) -> None:
        result = self._run_no_accel(delta_z=3.0)
        assert result.delta_p_total > result.friction.delta_p_friction

    def test_downward_pipe_gravity_is_negative(self) -> None:
        result = self._run_no_accel(delta_z=-3.0)
        assert result.gravity.delta_p_gravity < 0.0

    def test_downward_pipe_total_less_than_friction_alone(self) -> None:
        result = self._run_no_accel(delta_z=-3.0)
        assert result.delta_p_total < result.friction.delta_p_friction

    def test_gravity_magnitude_matches_formula(self) -> None:
        rho, g, delta_z = 1050.0, 9.81, 4.0
        pipe = _make_pipe(delta_z=delta_z)
        inp = _mech_input(rho=rho, g=g, G_in=200.0, rho_in=rho, G_out=200.0, rho_out=rho)
        result = pipe.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert math.isclose(result.gravity.delta_p_gravity, rho * g * delta_z, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Physics: acceleration contribution
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureAcceleration:
    def test_lower_outlet_density_increases_total(self) -> None:
        # rho_out < rho_in → positive acceleration → larger total
        pipe = _make_pipe(delta_z=0.0)
        inp_no_accel = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=1200.0)
        inp_accel = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=800.0)
        r_no = pipe.evaluate_mechanical_pressure_summary(inp_no_accel, _CHURCHILL)
        r_ac = pipe.evaluate_mechanical_pressure_summary(inp_accel, _CHURCHILL)
        assert r_ac.delta_p_total > r_no.delta_p_total

    def test_acceleration_contribution_is_independent_of_friction_and_gravity(self) -> None:
        # Use two pipes — different lengths → different friction.
        # Same scalar accel inputs → same acceleration contribution.
        G_in, rho_in, G_out, rho_out = 200.0, 1200.0, 200.0, 800.0
        inp_short = _mech_input(G_in=G_in, rho_in=rho_in, G_out=G_out, rho_out=rho_out)
        inp_long = _mech_input(G_in=G_in, rho_in=rho_in, G_out=G_out, rho_out=rho_out)
        r_short = _make_pipe(L=1.0).evaluate_mechanical_pressure_summary(inp_short, _CHURCHILL)
        r_long = _make_pipe(L=10.0).evaluate_mechanical_pressure_summary(inp_long, _CHURCHILL)
        assert math.isclose(
            r_short.acceleration.delta_p_acceleration,
            r_long.acceleration.delta_p_acceleration,
            rel_tol=1e-12,
        )

    def test_acceleration_magnitude_matches_formula(self) -> None:
        G_in, rho_in, G_out, rho_out = 150.0, 1100.0, 250.0, 900.0
        inp = _mech_input(G_in=G_in, rho_in=rho_in, G_out=G_out, rho_out=rho_out)
        result = _make_pipe().evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        expected = G_out**2 / rho_out - G_in**2 / rho_in
        assert math.isclose(result.acceleration.delta_p_acceleration, expected, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Physics: pipe length affects friction but not gravity or acceleration
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureLengthEffect:
    def test_longer_pipe_increases_friction(self) -> None:
        inp = _mech_input()
        r_short = _make_pipe(L=1.0).evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        r_long = _make_pipe(L=10.0).evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert r_long.friction.delta_p_friction > r_short.friction.delta_p_friction

    def test_longer_pipe_does_not_change_gravity_for_fixed_delta_z(self) -> None:
        inp = _mech_input()
        pipe_short = Pipe(
            component_id=ComponentId("short"),
            geometry=_make_geometry(L=1.0, delta_z=2.0),
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe_long = Pipe(
            component_id=ComponentId("long"),
            geometry=_make_geometry(L=10.0, delta_z=2.0),
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        r_short = pipe_short.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        r_long = pipe_long.evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert math.isclose(
            r_short.gravity.delta_p_gravity,
            r_long.gravity.delta_p_gravity,
            rel_tol=1e-12,
        )

    def test_longer_pipe_does_not_change_acceleration_for_fixed_scalar_inputs(self) -> None:
        inp = _mech_input(G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=900.0)
        r_short = _make_pipe(L=1.0).evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        r_long = _make_pipe(L=10.0).evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert math.isclose(
            r_short.acceleration.delta_p_acceleration,
            r_long.acceleration.delta_p_acceleration,
            rel_tol=1e-12,
        )


# ---------------------------------------------------------------------------
# Friction verdict and metadata preservation
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureSummaryVerdictAndMetadata:
    def _run(self, G: float = 200.0) -> PipeMechanicalPressureSummary:
        return _make_pipe().evaluate_mechanical_pressure_summary(_mech_input(G=G), _CHURCHILL)

    def test_friction_verdict_is_in_envelope_for_typical_flow(self) -> None:
        result = self._run(G=200.0)
        assert result.friction.verdict.status is ValidityStatus.IN_ENVELOPE

    def test_friction_verdict_is_extrapolated_for_zero_flow(self) -> None:
        result = self._run(G=0.0)
        assert result.friction.verdict.status is ValidityStatus.EXTRAPOLATED

    def test_friction_metadata_name_matches_churchill(self) -> None:
        result = self._run()
        assert result.friction.metadata.name == "churchill_friction_gradient"

    def test_friction_metadata_has_version(self) -> None:
        result = self._run()
        assert result.friction.metadata.version

    def test_friction_metadata_has_source(self) -> None:
        result = self._run()
        assert result.friction.metadata.source is not None

    def test_verdict_envelope_has_correlation_name(self) -> None:
        result = self._run()
        assert result.friction.verdict.envelope.correlation_name == "churchill_friction_gradient"


# ---------------------------------------------------------------------------
# Correlation role guard
# ---------------------------------------------------------------------------


class _FakeTwoPhaseDPCorrelation(Correlation):
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


class TestPipeMechanicalPressureSummaryCorrelationGuard:
    def test_rejects_non_correlation_instance(self) -> None:
        pipe = _make_pipe()
        with pytest.raises(TypeError, match="Correlation instance"):
            pipe.evaluate_mechanical_pressure_summary(_mech_input(), "bad")  # type: ignore[arg-type]

    def test_rejects_none_as_correlation(self) -> None:
        pipe = _make_pipe()
        with pytest.raises(TypeError, match="Correlation instance"):
            pipe.evaluate_mechanical_pressure_summary(_mech_input(), None)  # type: ignore[arg-type]

    def test_rejects_wrong_role_correlation(self) -> None:
        pipe = _make_pipe()
        with pytest.raises(ValueError, match="SINGLE_PHASE_DP"):
            pipe.evaluate_mechanical_pressure_summary(_mech_input(), _FakeTwoPhaseDPCorrelation())


# ---------------------------------------------------------------------------
# Optional friction multiplier
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureSummaryFrictionMultiplier:
    def _run(self, multiplier: float, pipe: Pipe | None = None) -> PipeMechanicalPressureSummary:
        p = pipe if pipe is not None else _make_pipe()
        return p.evaluate_mechanical_pressure_summary(
            _mech_input(friction_multiplier=multiplier), _CHURCHILL
        )

    def test_multiplier_two_doubles_friction_dp(self) -> None:
        r1 = self._run(multiplier=1.0)
        r2 = self._run(multiplier=2.0)
        assert math.isclose(
            r2.friction.delta_p_friction,
            2.0 * r1.friction.delta_p_friction,
            rel_tol=1e-12,
        )

    def test_multiplier_two_doubles_friction_dp_dx(self) -> None:
        r1 = self._run(multiplier=1.0)
        r2 = self._run(multiplier=2.0)
        assert math.isclose(
            r2.friction.dp_dx_friction,
            2.0 * r1.friction.dp_dx_friction,
            rel_tol=1e-12,
        )

    def test_multiplier_zero_zeros_friction_dp(self) -> None:
        result = self._run(multiplier=0.0)
        assert result.friction.delta_p_friction == 0.0

    def test_multiplier_does_not_scale_gravity(self) -> None:
        pipe = _make_pipe(delta_z=3.0)
        r1 = self._run(multiplier=1.0, pipe=pipe)
        r2 = self._run(multiplier=5.0, pipe=pipe)
        assert math.isclose(
            r1.gravity.delta_p_gravity,
            r2.gravity.delta_p_gravity,
            rel_tol=1e-12,
        )

    def test_multiplier_does_not_scale_acceleration(self) -> None:
        pipe = _make_pipe()
        inp_m1 = _mech_input(
            G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=800.0, friction_multiplier=1.0
        )
        inp_m5 = _mech_input(
            G_in=200.0, rho_in=1200.0, G_out=200.0, rho_out=800.0, friction_multiplier=5.0
        )
        r1 = pipe.evaluate_mechanical_pressure_summary(inp_m1, _CHURCHILL)
        r5 = pipe.evaluate_mechanical_pressure_summary(inp_m5, _CHURCHILL)
        assert math.isclose(
            r1.acceleration.delta_p_acceleration,
            r5.acceleration.delta_p_acceleration,
            rel_tol=1e-12,
        )

    def test_multiplier_scales_total_via_friction_term_only(self) -> None:
        # With delta_z=0 and equal rho_in/rho_out, total == scaled friction only
        pipe = _make_pipe(delta_z=0.0)
        r1 = self._run(multiplier=1.0, pipe=pipe)
        r3 = self._run(multiplier=3.0, pipe=pipe)
        expected_total = 3.0 * r1.friction.delta_p_friction
        assert math.isclose(r3.delta_p_total, expected_total, rel_tol=1e-12)

    def test_multiplier_preserves_verdict(self) -> None:
        r1 = self._run(multiplier=1.0)
        r2 = self._run(multiplier=2.0)
        assert r1.friction.verdict.status is r2.friction.verdict.status

    def test_multiplier_preserves_metadata_name(self) -> None:
        r1 = self._run(multiplier=1.0)
        r2 = self._run(multiplier=7.0)
        assert r1.friction.metadata.name == r2.friction.metadata.name


# ---------------------------------------------------------------------------
# Immutability — pipe, geometry, discretization, input not mutated
# ---------------------------------------------------------------------------


class TestPipeMechanicalPressureSummaryImmutability:
    def test_pipe_not_mutated_after_call(self) -> None:
        pipe = _make_pipe()
        cid_before = pipe.component_id
        geom_before = pipe.geometry
        disc_before = pipe.discretization
        pipe.evaluate_mechanical_pressure_summary(_mech_input(), _CHURCHILL)
        assert pipe.component_id == cid_before
        assert pipe.geometry is geom_before
        assert pipe.discretization is disc_before

    def test_geometry_not_mutated_after_call(self) -> None:
        geom = _make_geometry(L=5.0, delta_z=2.0)
        L_before = geom.L
        dz_before = geom.trajectory.delta_z
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=geom,
            discretization=DiscretizationSpec(mode=DiscretizationMode.LUMPED),
        )
        pipe.evaluate_mechanical_pressure_summary(_mech_input(), _CHURCHILL)
        assert geom.L == L_before
        assert geom.trajectory.delta_z == dz_before

    def test_discretization_not_mutated_after_call(self) -> None:
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=4)
        pipe = Pipe(
            component_id=ComponentId("p"),
            geometry=_make_geometry(),
            discretization=disc,
        )
        pipe.evaluate_mechanical_pressure_summary(_mech_input(), _CHURCHILL)
        assert disc.mode is DiscretizationMode.UNIFORM
        assert disc.n_cells == 4

    def test_input_not_mutated_after_call(self) -> None:
        inp = _mech_input(G=150.0, rho=1100.0, mu=3e-4)
        G_before = inp.G
        rho_before = inp.rho
        mu_before = inp.mu
        _make_pipe().evaluate_mechanical_pressure_summary(inp, _CHURCHILL)
        assert inp.G == G_before
        assert inp.rho == rho_before
        assert inp.mu == mu_before


# ---------------------------------------------------------------------------
# Import boundary — no CoolProp, network, solvers, or PropertyBackend
# ---------------------------------------------------------------------------


def _import_lines_from(module_file: str) -> list[str]:
    with open(module_file) as f:
        lines = f.readlines()
    return [line.strip() for line in lines if line.strip().startswith(("import ", "from "))]


class TestPipeMechanicalSummaryImportBoundary:
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


class TestComponentsPackageExportsMechanical:
    def test_mechanical_input_exported(self) -> None:
        import mpl_sim.components as comp_pkg

        assert hasattr(comp_pkg, "PipeMechanicalPressureInput")

    def test_mechanical_summary_exported(self) -> None:
        import mpl_sim.components as comp_pkg

        assert hasattr(comp_pkg, "PipeMechanicalPressureSummary")
