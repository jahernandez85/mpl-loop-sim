"""Tests for LMTDModel — Phase 11E.

Verifies:
  Model identity and registry:
    - LMTDModel.kind() returns HeatExchangerModelKind.LMTD
    - LMTDModel is exported from hx_models
    - LMTDModel can be registered and resolved in HeatExchangerModelRegistry

  FixedWallTemp path:
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

  AmbientCoupling path:
    - Ambient hotter than primary gives Q > 0
    - Ambient colder than primary gives Q < 0
    - h_out = h_in + Q / primary_mdot
    - Missing primary_T_in raises ValueError
    - A_ht is not required for the energy calculation
    - htc_primary is not required for the energy calculation
    - htc_multiplier does NOT affect Q
    - DP path works and verdict is propagated if supplied
    - Empty verdicts when no correlation is called
    - friction_multiplier affects DP only

  Unsupported BCs:
    - SinkInletTempAndFlow raises UnsupportedHeatExchangerBoundaryConditionError
    - FixedHeatRate raises UnsupportedHeatExchangerBoundaryConditionError

  Architecture:
    - lmtd.py does not import CoolProp
    - lmtd.py does not import PropertyBackend
    - lmtd.py does not import network/ or solvers/
    - lmtd.py does not resolve CorrelationRegistry

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
    FixedHeatRate,
    FixedWallTemp,
    HeatExchangerModelKind,
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
    UnsupportedHeatExchangerBoundaryConditionError,
)
from mpl_sim.hx_models.lmtd import LMTDModel
from mpl_sim.hx_models.registry import create_empty_hx_model_registry

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
# Shared test fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_STATE_IN = FluidState(P=1e6, h=250e3, identity=_IDENTITY)
_DISC = DiscretizationSpec(mode=DiscretizationMode.LUMPED)

# Minimal geom_scalars for energy path (FixedWallTemp, no DP).
_GEOM_ENERGY = {"G": 100.0, "D_h": 0.002, "x": 0.5, "A_ht": 0.1}

# Full geom_scalars for energy + DP (FixedWallTemp).
_GEOM_FULL = {**_GEOM_ENERGY, "rho": 1200.0, "mu": 2e-4, "L_cell": 0.1}

# DP-only geom_scalars for AmbientCoupling path.
_GEOM_DP = {"G": 100.0, "D_h": 0.002, "rho": 1200.0, "mu": 2e-4, "L_cell": 0.1}


def _make_wall_req(
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


def _make_ambient_req(
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
# Model identity and registry
# ---------------------------------------------------------------------------


class TestLMTDModelIdentity:
    def test_kind_returns_lmtd(self) -> None:
        assert LMTDModel().kind() is HeatExchangerModelKind.LMTD

    def test_kind_is_not_epsilon_ntu(self) -> None:
        assert LMTDModel().kind() is not HeatExchangerModelKind.EPSILON_NTU

    def test_exported_from_hx_models(self) -> None:
        import mpl_sim.hx_models as pkg

        assert hasattr(pkg, "LMTDModel")
        assert pkg.LMTDModel is LMTDModel

    def test_registry_can_register_lmtd(self) -> None:
        reg = create_empty_hx_model_registry()
        model = LMTDModel()
        reg.register("lmtd", model)
        assert reg.is_registered("lmtd")

    def test_registry_can_resolve_lmtd(self) -> None:
        reg = create_empty_hx_model_registry()
        model = LMTDModel()
        reg.register("lmtd", model)
        assert reg.resolve("lmtd") is model


# ---------------------------------------------------------------------------
# FixedWallTemp — sign convention
# ---------------------------------------------------------------------------


class TestFixedWallTempSignConvention:
    def test_heating_case_q_positive(self) -> None:
        """T_wall > primary_T_in → Q > 0 (primary gains heat)."""
        result = LMTDModel().solve(_make_wall_req(T_wall=350.0, primary_T_in=300.0))
        assert result.Q > 0.0

    def test_cooling_case_q_negative(self) -> None:
        """T_wall < primary_T_in → Q < 0 (primary rejects heat)."""
        result = LMTDModel().solve(_make_wall_req(T_wall=290.0, primary_T_in=320.0))
        assert result.Q < 0.0

    def test_equal_temps_gives_zero_q(self) -> None:
        result = LMTDModel().solve(_make_wall_req(T_wall=300.0, primary_T_in=300.0))
        assert result.Q == 0.0


# ---------------------------------------------------------------------------
# FixedWallTemp — energy balance
# ---------------------------------------------------------------------------


class TestFixedWallTempEnergyBalance:
    def test_h_out_heating(self) -> None:
        T_wall, T_in, mdot = 370.0, 300.0, 0.05
        htc, A_ht = _FAKE_HTC_VALUE, _GEOM_ENERGY["A_ht"]
        expected_Q = htc * A_ht * (T_wall - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot

        result = LMTDModel().solve(_make_wall_req(T_wall=T_wall, primary_T_in=T_in, mdot=mdot))
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-12)

    def test_h_out_cooling(self) -> None:
        T_wall, T_in, mdot = 280.0, 330.0, 0.08
        htc, A_ht = _FAKE_HTC_VALUE, _GEOM_ENERGY["A_ht"]
        expected_Q = htc * A_ht * (T_wall - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot

        result = LMTDModel().solve(_make_wall_req(T_wall=T_wall, primary_T_in=T_in, mdot=mdot))
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-12)

    def test_result_is_hx_solve_result(self) -> None:
        assert isinstance(LMTDModel().solve(_make_wall_req()), HXSolveResult)

    def test_identity_preserved(self) -> None:
        result = LMTDModel().solve(_make_wall_req())
        assert result.primary_state_out.identity is _IDENTITY

    def test_primary_state_out_is_new_object(self) -> None:
        result = LMTDModel().solve(_make_wall_req())
        assert result.primary_state_out is not _STATE_IN


# ---------------------------------------------------------------------------
# FixedWallTemp — validation
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
            LMTDModel().solve(req)

    def test_missing_a_ht_raises(self) -> None:
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
            LMTDModel().solve(req)

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
            LMTDModel().solve(req)

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
            LMTDModel().solve(req)

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
            LMTDModel().solve(req)

    @pytest.mark.parametrize("bad_htc", [math.nan, math.inf, 0.0, -50.0])
    def test_invalid_htc_output_raises(self, bad_htc: float) -> None:
        with pytest.raises(ValueError, match="HTC"):
            LMTDModel().solve(_make_wall_req(htc_primary=_FakeHTCCorrelation(htc=bad_htc)))


# ---------------------------------------------------------------------------
# FixedWallTemp — calibration
# ---------------------------------------------------------------------------


class TestFixedWallTempCalibration:
    def test_htc_multiplier_scales_q(self) -> None:
        """Doubling htc_multiplier doubles UA and therefore Q."""
        T_wall, T_in = 350.0, 300.0
        r1 = LMTDModel().solve(_make_wall_req(T_wall=T_wall, primary_T_in=T_in, htc_multiplier=1.0))
        r2 = LMTDModel().solve(_make_wall_req(T_wall=T_wall, primary_T_in=T_in, htc_multiplier=2.0))
        assert math.isclose(r2.Q, 2.0 * r1.Q, rel_tol=1e-12)

    def test_zero_htc_multiplier_gives_zero_q(self) -> None:
        result = LMTDModel().solve(
            _make_wall_req(T_wall=400.0, primary_T_in=300.0, htc_multiplier=0.0)
        )
        assert result.Q == 0.0

    def test_htc_multiplier_stored_in_result(self) -> None:
        m = 1.5
        result = LMTDModel().solve(_make_wall_req(htc_multiplier=m))
        assert math.isclose(result.htc_multiplier, m, rel_tol=1e-12)

    def test_friction_multiplier_does_not_affect_q(self) -> None:
        T_wall, T_in = 360.0, 300.0
        r1 = LMTDModel().solve(
            _make_wall_req(
                T_wall=T_wall,
                primary_T_in=T_in,
                dp_primary=_FakeDPCorrelation(),
                geom_scalars=_GEOM_FULL,
                friction_multiplier=1.0,
            )
        )
        r2 = LMTDModel().solve(
            _make_wall_req(
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
        result = LMTDModel().solve(
            _make_wall_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL, friction_multiplier=m
            )
        )
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_friction_multiplier_stored_in_result(self) -> None:
        m = 0.8
        result = LMTDModel().solve(
            _make_wall_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL, friction_multiplier=m
            )
        )
        assert math.isclose(result.friction_multiplier, m, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# FixedWallTemp — pressure drop path
# ---------------------------------------------------------------------------


class TestFixedWallTempDP:
    def test_no_dp_gives_zero_dp(self) -> None:
        result = LMTDModel().solve(_make_wall_req(dp_primary=None))
        assert result.dP_primary == 0.0

    def test_no_dp_p_out_equals_p_in(self) -> None:
        result = LMTDModel().solve(_make_wall_req(dp_primary=None))
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P, rel_tol=1e-12)

    def test_dp_path_produces_nonzero_dp(self) -> None:
        result = LMTDModel().solve(
            _make_wall_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert math.isclose(result.dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_decreases_outlet_pressure(self) -> None:
        result = LMTDModel().solve(
            _make_wall_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P - _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_verdict_propagated(self) -> None:
        result = LMTDModel().solve(
            _make_wall_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert any(v.metadata.name == "fake_dp" for v in result.verdicts)

    def test_htc_verdict_propagated(self) -> None:
        result = LMTDModel().solve(_make_wall_req())
        assert any(v.metadata.name == "fake_htc" for v in result.verdicts)

    def test_both_correlations_give_two_verdicts(self) -> None:
        result = LMTDModel().solve(
            _make_wall_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL)
        )
        assert len(result.verdicts) == 2

    def test_raw_dp_is_pre_calibration(self) -> None:
        m = 3.0
        result = LMTDModel().solve(
            _make_wall_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FULL, friction_multiplier=m
            )
        )
        assert math.isclose(result.raw_dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# AmbientCoupling — sign convention
# ---------------------------------------------------------------------------


class TestAmbientCouplingSignConvention:
    def test_ambient_hotter_q_positive(self) -> None:
        """T_ambient > primary_T_in → Q > 0 (primary absorbs heat)."""
        result = LMTDModel().solve(_make_ambient_req(T_ambient=380.0, primary_T_in=300.0))
        assert result.Q > 0.0

    def test_ambient_colder_q_negative(self) -> None:
        """T_ambient < primary_T_in → Q < 0 (primary rejects heat)."""
        result = LMTDModel().solve(_make_ambient_req(T_ambient=280.0, primary_T_in=320.0))
        assert result.Q < 0.0

    def test_equal_temps_gives_zero_q(self) -> None:
        result = LMTDModel().solve(_make_ambient_req(T_ambient=300.0, primary_T_in=300.0))
        assert result.Q == 0.0


# ---------------------------------------------------------------------------
# AmbientCoupling — energy balance
# ---------------------------------------------------------------------------


class TestAmbientCouplingEnergyBalance:
    def test_q_equals_ua_times_delta_t(self) -> None:
        T_amb, T_in, UA = 380.0, 300.0, 5.0
        expected_Q = UA * (T_amb - T_in)
        result = LMTDModel().solve(
            _make_ambient_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in)
        )
        assert math.isclose(result.Q, expected_Q, rel_tol=1e-12)

    def test_h_out_heating(self) -> None:
        T_amb, T_in, UA, mdot = 380.0, 300.0, 5.0, 0.05
        expected_Q = UA * (T_amb - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot
        result = LMTDModel().solve(
            _make_ambient_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in, mdot=mdot)
        )
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_h_out_cooling(self) -> None:
        T_amb, T_in, UA, mdot = 280.0, 330.0, 8.0, 0.08
        expected_Q = UA * (T_amb - T_in)
        expected_h = _STATE_IN.h + expected_Q / mdot
        result = LMTDModel().solve(
            _make_ambient_req(T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in, mdot=mdot)
        )
        assert math.isclose(result.primary_state_out.h, expected_h, rel_tol=1e-12)

    def test_result_is_hx_solve_result(self) -> None:
        assert isinstance(LMTDModel().solve(_make_ambient_req()), HXSolveResult)

    def test_identity_preserved(self) -> None:
        result = LMTDModel().solve(_make_ambient_req())
        assert result.primary_state_out.identity is _IDENTITY

    def test_primary_state_out_is_new_object(self) -> None:
        result = LMTDModel().solve(_make_ambient_req())
        assert result.primary_state_out is not _STATE_IN


# ---------------------------------------------------------------------------
# AmbientCoupling — validation
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
            LMTDModel().solve(req)

    def test_a_ht_not_required(self) -> None:
        """AmbientCoupling must not look up A_ht from geom_scalars."""
        result = LMTDModel().solve(_make_ambient_req(geom_scalars={}))
        assert isinstance(result, HXSolveResult)

    def test_htc_primary_not_required(self) -> None:
        """AmbientCoupling must not require htc_primary."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=AmbientCoupling(T_ambient=350.0, UA_ambient=5.0),
            geometry=object(),
            discretization=_DISC,
            htc_primary=None,
            primary_T_in=300.0,
        )
        result = LMTDModel().solve(req)
        assert isinstance(result, HXSolveResult)


# ---------------------------------------------------------------------------
# AmbientCoupling — htc_multiplier must NOT affect Q
# ---------------------------------------------------------------------------


class TestAmbientCouplingHTCMultiplier:
    def test_htc_multiplier_does_not_change_q(self) -> None:
        """UA_ambient is a fixed physical input; htc_multiplier must not scale it."""
        T_amb, T_in, UA = 370.0, 300.0, 5.0
        for m in (0.5, 1.0, 2.0):
            result = LMTDModel().solve(
                _make_ambient_req(
                    T_ambient=T_amb, UA_ambient=UA, primary_T_in=T_in, htc_multiplier=m
                )
            )
            expected_Q = UA * (T_amb - T_in)
            assert math.isclose(
                result.Q, expected_Q, rel_tol=1e-12
            ), f"htc_multiplier={m} altered Q; expected {expected_Q}, got {result.Q}"

    def test_htc_multiplier_stored_in_result(self) -> None:
        m = 1.7
        result = LMTDModel().solve(_make_ambient_req(htc_multiplier=m))
        assert math.isclose(result.htc_multiplier, m, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# AmbientCoupling — pressure drop path and verdict propagation
# ---------------------------------------------------------------------------


class TestAmbientCouplingDP:
    def test_no_dp_gives_zero_dp(self) -> None:
        result = LMTDModel().solve(_make_ambient_req(dp_primary=None))
        assert result.dP_primary == 0.0

    def test_no_dp_p_out_equals_p_in(self) -> None:
        result = LMTDModel().solve(_make_ambient_req(dp_primary=None))
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P, rel_tol=1e-12)

    def test_empty_verdicts_when_no_correlation(self) -> None:
        """No HTC or DP correlation → verdicts must be empty."""
        result = LMTDModel().solve(_make_ambient_req(dp_primary=None))
        assert result.verdicts == ()

    def test_dp_path_works(self) -> None:
        result = LMTDModel().solve(
            _make_ambient_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert math.isclose(result.dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_decreases_outlet_pressure(self) -> None:
        result = LMTDModel().solve(
            _make_ambient_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert math.isclose(result.primary_state_out.P, _STATE_IN.P - _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_dp_verdict_propagated(self) -> None:
        result = LMTDModel().solve(
            _make_ambient_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert any(v.metadata.name == "fake_dp" for v in result.verdicts)

    def test_one_verdict_when_only_dp(self) -> None:
        result = LMTDModel().solve(
            _make_ambient_req(dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        )
        assert len(result.verdicts) == 1

    def test_friction_multiplier_scales_dp(self) -> None:
        m = 2.0
        result = LMTDModel().solve(
            _make_ambient_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP, friction_multiplier=m
            )
        )
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)

    def test_friction_multiplier_does_not_affect_q(self) -> None:
        T_amb, T_in, UA = 370.0, 300.0, 5.0
        r1 = LMTDModel().solve(
            _make_ambient_req(
                T_ambient=T_amb,
                UA_ambient=UA,
                primary_T_in=T_in,
                dp_primary=_FakeDPCorrelation(),
                geom_scalars=_GEOM_DP,
                friction_multiplier=1.0,
            )
        )
        r2 = LMTDModel().solve(
            _make_ambient_req(
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
        result = LMTDModel().solve(
            _make_ambient_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP, friction_multiplier=m
            )
        )
        assert math.isclose(result.friction_multiplier, m, rel_tol=1e-12)

    def test_raw_dp_is_pre_calibration(self) -> None:
        m = 4.0
        result = LMTDModel().solve(
            _make_ambient_req(
                dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP, friction_multiplier=m
            )
        )
        assert math.isclose(result.raw_dP_primary, _FAKE_DP_VALUE, rel_tol=1e-12)
        assert math.isclose(result.dP_primary, m * _FAKE_DP_VALUE, rel_tol=1e-12)


# ---------------------------------------------------------------------------
# Unsupported BCs
# ---------------------------------------------------------------------------


def _make_sink_inlet_req() -> HXSolveRequest:
    """Build a valid SinkInletTempAndFlow request that passes HXSolveRequest construction."""
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.05,
        secondary_bc=SinkInletTempAndFlow(T_in=280.0, mdot_secondary=0.1, cp_secondary=4180.0),
        geometry=object(),
        discretization=_DISC,
        geom_scalars=_GEOM_ENERGY,
        htc_primary=_FakeHTCCorrelation(),
        primary_T_in=300.0,
        primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
        ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
    )


class TestUnsupportedBCs:
    def test_sink_inlet_raises_unsupported(self) -> None:
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            LMTDModel().solve(_make_sink_inlet_req())

    def test_fixed_heat_rate_raises_unsupported(self) -> None:
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC,
        )
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            LMTDModel().solve(req)

    def test_sink_inlet_message_mentions_lmtd(self) -> None:
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError, match="LMTDModel"):
            LMTDModel().solve(_make_sink_inlet_req())

    def test_fixed_heat_rate_message_mentions_lmtd(self) -> None:
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC,
        )
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError, match="LMTDModel"):
            LMTDModel().solve(req)

    def test_unsupported_error_is_not_implemented_error_subclass(self) -> None:
        """UnsupportedHeatExchangerBoundaryConditionError subclasses NotImplementedError."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.05,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC,
        )
        with pytest.raises(NotImplementedError):
            LMTDModel().solve(req)


# ---------------------------------------------------------------------------
# Architecture — lmtd.py import boundaries
# ---------------------------------------------------------------------------


def _import_lines_from_file(filepath: str) -> list[str]:
    with open(filepath) as f:
        return [ln.strip() for ln in f if ln.strip().startswith(("import ", "from "))]


class TestLMTDArchitectureBoundaries:
    def test_lmtd_does_not_import_coolprop(self) -> None:
        import mpl_sim.hx_models.lmtd as m

        assert m.__file__ is not None
        for ln in _import_lines_from_file(m.__file__):
            assert "coolprop" not in ln.lower(), f"lmtd.py: forbidden import: {ln!r}"

    def test_lmtd_does_not_import_property_backend(self) -> None:
        import mpl_sim.hx_models.lmtd as m

        assert m.__file__ is not None
        for ln in _import_lines_from_file(m.__file__):
            assert "propertybackend" not in ln.lower(), f"lmtd.py: forbidden import: {ln!r}"
            assert "properties" not in ln.lower(), f"lmtd.py: forbidden import: {ln!r}"

    def test_lmtd_does_not_import_network(self) -> None:
        import mpl_sim.hx_models.lmtd as m

        assert m.__file__ is not None
        for ln in _import_lines_from_file(m.__file__):
            assert "network" not in ln.lower(), f"lmtd.py: forbidden import: {ln!r}"

    def test_lmtd_does_not_import_solvers(self) -> None:
        import mpl_sim.hx_models.lmtd as m

        assert m.__file__ is not None
        for ln in _import_lines_from_file(m.__file__):
            assert "solvers" not in ln.lower(), f"lmtd.py: forbidden import: {ln!r}"

    def test_lmtd_does_not_import_correlation_registry(self) -> None:
        import mpl_sim.hx_models.lmtd as m

        assert m.__file__ is not None
        source = open(m.__file__).read()
        assert "CorrelationRegistry" not in source, "lmtd.py must not reference CorrelationRegistry"

    def test_lmtd_kind_is_not_a_correlation_role(self) -> None:
        assert HeatExchangerModelKind.LMTD not in list(CorrelationRole)
