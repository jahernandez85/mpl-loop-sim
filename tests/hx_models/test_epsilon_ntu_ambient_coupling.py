"""Tests for EpsilonNTUModel — AmbientCoupling BC — Phase 11D.

Verifies:
  - Ambient hotter than primary gives Q > 0
  - Ambient colder than primary gives Q < 0
  - h_out = h_in + Q / primary_mdot
  - Missing primary_T_in raises ValueError
  - A_ht is not required for the energy calculation
  - htc_primary is not required for the energy calculation
  - htc_multiplier does NOT affect UA_ambient or Q
    (UA_ambient is the calibrated physical input — there is no primary-side HTC
    correlation whose output would be scaled by htc_multiplier)
  - DP path works and verdict is propagated if dp_primary is supplied
  - friction_multiplier affects DP only (not Q or h_out)
  - Empty verdicts when no correlation is called
  - No hidden physical defaults

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
    AmbientCoupling,
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

_FAKE_DP_VALUE = 600.0  # Pa


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

# Minimal geom_scalars for the DP path.
_GEOM_DP = {"G": 100.0, "D_h": 0.002, "rho": 1200.0, "mu": 2e-4, "L_cell": 0.1}


def _make_req(
    T_ambient: float = 350.0,
    UA_ambient: float = 5.0,
    primary_T_in: float | None = 300.0,
    dp_primary: Correlation | None = None,
    geom_scalars: dict | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    mdot: float = 0.05,
) -> HXSolveRequest:
    gs = geom_scalars if geom_scalars is not None else {}
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=AmbientCoupling(T_ambient=T_ambient, UA_ambient=UA_ambient),
        geometry=object(),
        discretization=_DISC,
        geom_scalars=gs,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=primary_T_in,
    )


# ---------------------------------------------------------------------------
# Sign convention — heating and cooling
# ---------------------------------------------------------------------------


class TestAmbientCouplingSignConvention:
    def test_ambient_hotter_q_positive(self) -> None:
        """T_ambient > primary_T_in → Q > 0 (primary absorbs heat)."""
        result = EpsilonNTUModel().solve(_make_req(T_ambient=380.0, primary_T_in=300.0))
        assert result.Q > 0.0

    def test_ambient_colder_q_negative(self) -> None:
        """T_ambient < primary_T_in → Q < 0 (primary rejects heat)."""
        result = EpsilonNTUModel().solve(_make_req(T_ambient=280.0, primary_T_in=320.0))
        assert result.Q < 0.0

    def test_equal_temps_gives_zero_q(self) -> None:
        result = EpsilonNTUModel().solve(_make_req(T_ambient=300.0, primary_T_in=300.0))
        assert result.Q == 0.0


# ---------------------------------------------------------------------------
# Energy balance — h_out = h_in + Q / mdot
# ---------------------------------------------------------------------------


class TestAmbientCouplingEnergyBalance:
    def test_q_equals_ua_times_delta_t(self) -> None:
        T_amb, T_in, UA = 380.0, 300.0, 5.0
        expected_Q = UA * (T_amb - T_in)

        result = EpsilonNTUModel().solve(
            _make_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in)
        )
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-12)

    def test_h_out_heating(self) -> None:
        T_amb, T_in, UA, mdot = 380.0, 300.0, 5.0, 0.05
        expected_Q = UA * (T_amb - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot

        result = EpsilonNTUModel().solve(
            _make_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in, mdot=mdot)
        )
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_h_out_cooling(self) -> None:
        T_amb, T_in, UA, mdot = 280.0, 330.0, 8.0, 0.08
        expected_Q = UA * (T_amb - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot

        result = EpsilonNTUModel().solve(
            _make_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in, mdot=mdot)
        )
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_result_is_hx_solve_result(self) -> None:
        assert isinstance(EpsilonNTUModel().solve(_make_req()), HXSolveResult)

    def test_identity_preserved(self) -> None:
        result = EpsilonNTUModel().solve(_make_req())
        assert result.primary_state_out.identity is _IDENTITY

    def test_primary_state_out_is_new_object(self) -> None:
        result = EpsilonNTUModel().solve(_make_req())
        assert result.primary_state_out is not _STATE_IN


# ---------------------------------------------------------------------------
# Validation — missing primary_T_in
# ---------------------------------------------------------------------------


class TestAmbientCouplingValidation:
    def test_missing_primary_t_in_raises(self) -> None:
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=AmbientCoupling(T_ambient=350.0, UA_ambient=5.0),
            geometry=object(),
            discretization=_DISC,
            primary_T_in=None,
        )
        with pytest.raises(ValueError, match="primary_T_in"):
            EpsilonNTUModel().solve(req)

    def test_a_ht_not_required(self) -> None:
        """Energy path must not look up A_ht from geom_scalars."""
        result = EpsilonNTUModel().solve(_make_req(geom_scalars={}))
        assert isinstance(result, HXSolveResult)

    def test_htc_primary_not_required(self) -> None:
        """Energy path must not require htc_primary."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=AmbientCoupling(T_ambient=350.0, UA_ambient=5.0),
            geometry=object(),
            discretization=_DISC,
            htc_primary=None,
            primary_T_in=300.0,
        )
        result = EpsilonNTUModel().solve(req)
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# htc_multiplier must NOT affect Q
# ---------------------------------------------------------------------------


class TestAmbientCouplingHTCMultiplier:
    def test_htc_multiplier_does_not_change_q(self) -> None:
        """UA_ambient is a fixed physical input; htc_multiplier must not scale it."""
        T_amb, T_in, UA = 370.0, 300.0, 5.0
        for m in (0.5, 1.0, 2.0):
            result = EpsilonNTUModel().solve(
                _make_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in, htc_multiplier=m)
            )
            expected_Q = UA * (T_amb - T_in)
            assert math.isclose(
                result.Q, expected_Q, rel_tol=1e-12
            ), f"htc_multiplier={m} altered Q; expected {expected_Q}, got {result.Q}"

    def test_htc_multiplier_stored_in_result(self) -> None:
        m = 1.7
        result = EpsilonNTUModel().solve(_make_req(htc_multiplier=m))
        assert math.isclose(result.htc_multiplier, m, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Pressure drop path and verdict propagation
# ---------------------------------------------------------------------------


class TestAmbientCouplingDP:
    def test_no_dp_gives_zero_dp(self) -> None:
        result = EpsilonNTUModel().solve(_make_req(dp_primary=None))
        assert result.dP_primary == 0.0

    def test_no_dp_p_out_equals_p_in(self) -> None:
        result = EpsilonNTUModel().solve(_make_req(dp_primary=None))
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P, rel_tol=1e-12)

    def test_empty_verdicts_when_no_correlation(self) -> None:
        """No HTC or DP correlation → verdicts must be empty."""
        result = EpsilonNTUModel().solve(_make_req(dp_primary=None))
        assert result.verdicts == ()

    def test_dp_path_works(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert math.isclose(result.dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_decreases_outlet_pressure(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P - _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_verdict_propagated(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert any(v.metadata.name == "fake_dp" for v in result.verdicts)

    def test_one_verdict_when_only_dp(self) -> None:
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert len(result.verdicts) == 1

    def test_friction_multiplier_scales_dp(self) -> None:
        m = 2.0
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP, friction_multiplier=m)
        )
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_friction_multiplier_does_not_affect_q(self) -> None:
        T_amb, T_in, UA = 370.0, 300.0, 5.0
        r1 = EpsilonNTUModel().solve(
            _make_req(
                T_ambient=T_amb,
                UA_ambient=UA,
                primary_T_in=T_in,
                dp_primary=_FakeDPCorrelation(),
                geom_scalars=_GEOM_DP,
                friction_multiplier=1.0,
            )
        )
        r2 = EpsilonNTUModel().solve(
            _make_req(
                T_ambient=T_amb,
                UA_ambient=UA,
                primary_T_in=T_in,
                dp_primary=_FakeDPCorrelation(),
                geom_scalars=_GEOM_DP,
                friction_multiplier=3.0,
            )
        )
        assert math.isclose(r1.Q, r2.Q, rel_tol=1e-12)

    def test_friction_multiplier_stored_in_result(self) -> None:
        m = 1.2
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP, friction_multiplier=m)
        )
        assert math.isclose(result.friction_multiplier, m, rel_tol=1e-12)

    def test_raw_dp_is_pre_calibration(self) -> None:
        m = 4.0
        result = EpsilonNTUModel().solve(
            _make_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP, friction_multiplier=m)
        )
        assert math.isclose(result.raw_dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)
