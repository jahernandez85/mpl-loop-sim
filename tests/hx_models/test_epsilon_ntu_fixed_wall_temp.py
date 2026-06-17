"""Tests for EpsilonNTUModel — FixedWallTemp BC — Phase 11D.

Verifies:
  - Heating case (T_wall > primary_T_in) gives Q > 0
  - Cooling case (T_wall < primary_T_in) gives Q < 0
  - h_out = h_in + Q / primary_mdot
  - Missing primary_T_in raises ValueError
  - Missing A_ht raises ValueError
  - Invalid A_ht (zero, negative) raises ValueError
  - Missing htc_primary raises ValueError
  - Invalid HTC outputs (nan, inf, 0, negative) raise ValueError
  - htc_multiplier scales UA and therefore Q
  - DP path works and verdict is propagated
  - friction_multiplier affects DP only (not Q or h_out)
  - No secondary fluid properties are required

Architectural constraints respected:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes.
"""

from __future__ import annotations

import math

import pytest

from mpl_sim.core.fluid_identity import PureFluid
from mpl_sim.core.fluid_state import FluidState
from mpl_sim.correlations.contract import (
    AnyFluid,
    Bound,
    BoundedQuantity,
    ClosureMetadata,
    Correlation,
    CorrelationInput,
    CorrelationOutput,
    CorrelationRole,
    EnvelopeRef,
    SourceRef,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    FixedWallTemp,
    HXSolveRequest,
    HXSolveResult,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

# ---------------------------------------------------------------------------
# Fake correlations
# ---------------------------------------------------------------------------

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)

_FAKE_HTC_VALUE = 200.0  # W/m²K
_FAKE_DP_VALUE = 500.0  # Pa


def _make_htc_output(value: float) -> CorrelationOutput:
    return CorrelationOutput(
        value=(value,),
        verdict=ValidityVerdict(
            status=ValidityStatus.IN_ENVELOPE,
            envelope=EnvelopeRef(correlation_name="fake_htc", correlation_version="0"),
            violated=(),
        ),
        metadata=ClosureMetadata(
            name="fake_htc",
            version="0",
            source=SourceRef(citation="test"),
        ),
    )


class _FakeHTCCorrelation(Correlation):
    """Returns a configurable HTC value; ignores input."""

    def __init__(self, htc: float = _FAKE_HTC_VALUE) -> None:
        self._htc = htc

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_htc_output(self._htc)


class _FakeDPCorrelation(Correlation):
    """Returns _FAKE_DP_VALUE; ignores input."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return CorrelationOutput(
            value=(_FAKE_DP_VALUE,),
            verdict=ValidityVerdict(
                status=ValidityStatus.IN_ENVELOPE,
                envelope=EnvelopeRef(correlation_name="fake_dp", correlation_version="0"),
                violated=(),
            ),
            metadata=ClosureMetadata(
                name="fake_dp",
                version="0",
                source=SourceRef(citation="test"),
            ),
        )


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

# Minimal geom_scalars for the energy path (no DP).
_GEOM_ENERGY = {"G": 100.0, "D_h": 0.002, "x": 0.5, "A_ht": 0.1}

# Full geom_scalars for energy + DP.
_GEOM_FULL = {**_GEOM_ENERGY, "rho": 1200.0, "mu": 2e-4, "L_cell": 0.1}


def _make_req(
    T_wall: float = 350.0,
    primary_T_in: float | None = 300.0,
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    geom_scalars: dict | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    mdot: float = 0.05,
) -> HXSolveRequest:
    if htc_primary is None:
        htc_primary = _FakeHTCCorrelation()
    gs = geom_scalars if geom_scalars is not None else _GEOM_ENERGY
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=FixedWallTemp(T_wall=T_wall),
        geometry=object(),
        discretization=_DISC,
        geom_scalars=gs,
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=primary_T_in,
    )


# ---------------------------------------------------------------------------
# Sign convention — heating and cooling
# ---------------------------------------------------------------------------


class TestFixedWallTempSignConvention:
    def test_heating_case_q_positive(self) -> None:
        """T_wall > primary_T_in → Q > 0 (primary gains heat)."""
        result = EpsilonNTUModel().solve(_make_req(T_wall=350.0, primary_T_in=300.0))
        assert result.Q > 0.0

    def test_cooling_case_q_negative(self) -> None:
        """T_wall < primary_T_in → Q < 0 (primary rejects heat)."""
        result = EpsilonNTUModel().solve(_make_req(T_wall=290.0, primary_T_in=320.0))
        assert result.Q < 0.0

    def test_equal_temps_gives_zero_q(self) -> None:
        """T_wall == primary_T_in → Q == 0."""
        result = EpsilonNTUModel().solve(_make_req(T_wall=300.0, primary_T_in=300.0))
        assert result.Q == 0.0


# ---------------------------------------------------------------------------
# Energy balance — h_out = h_in + Q / mdot
# ---------------------------------------------------------------------------


class TestFixedWallTempEnergyBalance:
    def test_h_out_heating(self) -> None:
        T_wall, T_in, mdot = 370.0, 300.0, 0.05
        htc, A_ht = _FAKE_HTC_VALUE, _GEOM_ENERGY["A_ht"]
        expected_Q = htc * A_ht * (T_wall - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot

        result = EpsilonNTUModel().solve(_make_req(T_wall=T_wall, primary_T_in=T_in, mdot=mdot))
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-12)

    def test_h_out_cooling(self) -> None:
        T_wall, T_in, mdot = 280.0, 330.0, 0.08
        htc, A_ht = _FAKE_HTC_VALUE, _GEOM_ENERGY["A_ht"]
        expected_Q = htc * A_ht * (T_wall - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot

        result = EpsilonNTUModel().solve(_make_req(T_wall=T_wall, primary_T_in=T_in, mdot=mdot))
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-12)

    def test_result_is_hx_solve_result(self) -> None:
        assert isinstance(EpsilonNTUModel().solve(_make_req()), HXSolveResult)

    def test_identity_preserved(self) -> None:
        result = EpsilonNTUModel().solve(_make_req())
        assert result.primary_state_out.identity is _IDENTITY

    def test_primary_state_out_is_new_object(self) -> None:
        result = EpsilonNTUModel().solve(_make_req())
        assert result.primary_state_out is not _STATE_IN


# ---------------------------------------------------------------------------
# Validation — missing / invalid inputs
# ---------------------------------------------------------------------------


class TestFixedWallTempValidation:
    def test_missing_primary_t_in_raises(self) -> None:
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=_GEOM_ENERGY,
            htc_primary=_FakeHTCCorrelation(),
            primary_T_in=None,
        )
        with pytest.raises(ValueError, match="primary_T_in"):
            EpsilonNTUModel().solve(req)

    def test_missing_a_ht_raises(self) -> None:
        # geom_scalars without A_ht but with HTC keys
        gs = {"G": 100.0, "D_h": 0.002, "x": 0.5}
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=gs,
            htc_primary=_FakeHTCCorrelation(),
            primary_T_in=300.0,
        )
        with pytest.raises(ValueError, match="A_ht"):
            EpsilonNTUModel().solve(req)

    def test_zero_a_ht_raises(self) -> None:
        gs = {**_GEOM_ENERGY, "A_ht": 0.0}
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=gs,
            htc_primary=_FakeHTCCorrelation(),
            primary_T_in=300.0,
        )
        with pytest.raises(ValueError, match="A_ht"):
            EpsilonNTUModel().solve(req)

    def test_negative_a_ht_raises(self) -> None:
        gs = {**_GEOM_ENERGY, "A_ht": -0.5}
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=gs,
            htc_primary=_FakeHTCCorrelation(),
            primary_T_in=300.0,
        )
        with pytest.raises(ValueError, match="A_ht"):
            EpsilonNTUModel().solve(req)

    def test_missing_htc_primary_raises(self) -> None:
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC,
            geom_scalars=_GEOM_ENERGY,
            htc_primary=None,
            primary_T_in=300.0,
        )
        with pytest.raises(ValueError, match="htc_primary"):
            EpsilonNTUModel().solve(req)

    @pytest.mark.parametrize("bad_htc", [math.nan, math.inf, 0.0, -50.0])
    def test_invalid_htc_output_raises(self, bad_htc: float) -> None:
        with pytest.raises(ValueError, match="HTC"):
            EpsilonNTUModel().solve(_make_req(htc_primary=_FakeHTCCorrelation(htc=bad_htc)))

    def test_no_secondary_fluid_props_required(self) -> None:
        """FixedWallTemp must not require cp_secondary, mdot_secondary, or T_in."""
        result = EpsilonNTUModel().solve(_make_req())
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# Calibration — htc_multiplier scales Q; friction_multiplier affects DP only
# ---------------------------------------------------------------------------


class TestFixedWallTempCalibration:
    def test_htc_multiplier_scales_q(self) -> None:
        """Doubling htc_multiplier doubles UA and therefore Q."""
        T_wall, T_in = 350.0, 300.0
        r1 = EpsilonNTUModel().solve(
            _make_req(T_wall=T_wall, primary_T_in=T_in, htc_multiplier=1.0)
        )
        r2 = EpsilonNTUModel().solve(
            _make_req(T_wall=T_wall, primary_T_in=T_in, htc_multiplier=2.0)
        )
        assert math.isclose(r2.Q, 2.0 * r1.Q, rel_tol=1e-12)

    def test_zero_htc_multiplier_gives_zero_q(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(T_wall=400.0, primary_T_in=300.0, htc_multiplier=0.0)
        )
        assert result.Q == 0.0

    def test_htc_multiplier_stored_in_result(self) -> None:
        m = 1.5
        result = EpsilonNTUModel().solve(_make_req(htc_multiplier=m))
        assert math.isclose(result.htc_multiplier, m, rel_tol=1e-12)

    def test_friction_multiplier_does_not_affect_q(self) -> None:
        T_wall, T_in = 360.0, 300.0
        r1 = EpsilonNTUModel().solve(
            _make_req(
                T_wall=T_wall,
                primary_T_in=T_in,
                dp_primary=_FakeDPCorrelation(),
                geom_scalars=_GEOM_FULL,
                friction_multiplier=1.0,
            )
        )
        r2 = EpsilonNTUModel().solve(
            _make_req(
                T_wall=T_wall,
                primary_T_in=T_in,
                dp_primary=_FakeDPCorrelation(),
                geom_scalars=_GEOM_FULL,
                friction_multiplier=3.0,
            )
        )
        assert math.isclose(r1.Q, r2.Q, rel_tol=1e-12)

    def test_friction_multiplier_scales_dp(self) -> None:
        m = 2.5
        result = EpsilonNTUModel().solve(
            _make_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL, friction_multiplier=m
            )
        )
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_friction_multiplier_stored_in_result(self) -> None:
        m = 0.8
        result = EpsilonNTUModel().solve(
            _make_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL, friction_multiplier=m
            )
        )
        assert math.isclose(result.friction_multiplier, m, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Pressure drop path and verdict propagation
# ---------------------------------------------------------------------------


class TestFixedWallTempDP:
    def test_no_dp_gives_zero_dp(self) -> None:
        result = EpsilonNTUModel().solve(_make_req(dp_primary=None))
        assert result.dP_primary == 0.0

    def test_no_dp_p_out_equals_p_in(self) -> None:
        result = EpsilonNTUModel().solve(_make_req(dp_primary=None))
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P, rel_tol=1e-12)

    def test_dp_path_produces_nonzero_dp(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert math.isclose(result.dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_decreases_outlet_pressure(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P - _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_verdict_propagated(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        dp_names = [v.metadata.name for v in result.verdicts]
        assert "fake_dp" in dp_names

    def test_htc_verdict_propagated(self) -> None:
        result = EpsilonNTUModel().solve(_make_req())
        htc_names = [v.metadata.name for v in result.verdicts]
        assert "fake_htc" in htc_names

    def test_both_correlations_give_two_verdicts(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert len(result.verdicts) == 2

    def test_raw_dp_is_pre_calibration(self) -> None:
        m = 3.0
        result = EpsilonNTUModel().solve(
            _make_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL, friction_multiplier=m
            )
        )
        assert math.isclose(result.raw_dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)
