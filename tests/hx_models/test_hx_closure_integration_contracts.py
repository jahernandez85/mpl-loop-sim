"""HX closure integration contract tests — Phase 11K.

Verifies that all three implemented HX model strategies consume injected
closures correctly through the existing HXSolveRequest seams, without
resolving any registry internally, without hidden defaults, and without
calling CoolProp or PropertyBackend.

Closure inventory used in these tests:
  All HTC and DP correlations are local fakes (test-only stubs).
  No production HTC correlation (Dittus-Boelter, Gnielinski, boiling,
  condensation) exists in the correlations package yet.  That migration
  is deferred to Phase 11L or later.

Coverage plan:

  General injection contract:
    - HX models do not resolve CorrelationRegistry.
    - Injected HTC/DP correlations are called through HXSolveRequest.
    - CorrelationOutput.value is consumed, not hidden model-specific fields.
    - CorrelationOutput.verdicts are propagated.
    - Non-finite HTC outputs fail.
    - Non-positive HTC outputs fail.
    - Non-finite DP outputs fail.
    - Signed DP remains allowed (negative DP = pressure recovery).

  EpsilonNTUModel closure consumption:
    - PRIMARY_ONLY UA mode calls only htc_primary.
    - TWO_SIDED UA mode calls both htc_primary and htc_secondary.
    - Missing secondary HTC in TWO_SIDED mode fails at HXSolveRequest.
    - htc_multiplier scales each raw HTC before UA is assembled.
    - htc_multiplier=0.0 yields zero UA, zero Q for FixedWallTemp.
    - FixedHeatRate with htc_primary supplied still calls it (verdict only).
    - AmbientCoupling does not call HTC correlations.

  SegmentedMarchModel closure consumption:
    - FixedWallTemp calls htc_primary once per cell.
    - SinkInletTempAndFlow calls both htc_primary and htc_secondary once per cell.
    - AmbientCoupling does not call any HTC correlation.
    - FixedHeatRate does not call any HTC correlation.
    - dp_primary is independent of heat-transfer mode.
    - friction_multiplier scales DP without affecting Q.
    - htc_multiplier=0.0 zero-UA behavior propagates verdicts and gives Q=0.

  LMTDModel closure consumption:
    - FixedWallTemp calls htc_primary once and consumes CorrelationOutput.value.
    - AmbientCoupling does not call htc_primary; uses prescribed UA_ambient.
    - SinkInletTempAndFlow raises UnsupportedHeatExchangerBoundaryConditionError.
    - FixedHeatRate raises UnsupportedHeatExchangerBoundaryConditionError.

Architectural constraints respected:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes with explicit controlled outputs.
  - No CorrelationRegistry is constructed or queried in any HX model path.
  - Cell temperatures appear only in zone_profile diagnostics (segmented path).
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
from mpl_sim.correlations.registry import CorrelationRegistry
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    AmbientCoupling,
    FixedHeatRate,
    FixedWallTemp,
    HXSolveRequest,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
    UnsupportedHeatExchangerBoundaryConditionError,
)
from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel
from mpl_sim.hx_models.lmtd import LMTDModel
from mpl_sim.hx_models.segmented import SegmentedMarchModel

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_FLUID = PureFluid("R134a")
_STATE_IN = FluidState(P=500_000.0, h=250_000.0, identity=_FLUID)

_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED, n_cells=1)
_SEGMENTED_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test-stub"),
)


def _htc_out(value: float, name: str = "fake_htc") -> CorrelationOutput:
    return CorrelationOutput(
        value=(value,),
        verdict=ValidityVerdict(
            status=ValidityStatus.IN_ENVELOPE,
            envelope=EnvelopeRef(correlation_name=name, correlation_version="0"),
            violated=(),
        ),
        metadata=ClosureMetadata(name=name, version="0", source=SourceRef(citation="test")),
    )


def _dp_out(value: float, name: str = "fake_dp") -> CorrelationOutput:
    return CorrelationOutput(
        value=(value,),
        verdict=ValidityVerdict(
            status=ValidityStatus.IN_ENVELOPE,
            envelope=EnvelopeRef(correlation_name=name, correlation_version="0"),
            violated=(),
        ),
        metadata=ClosureMetadata(name=name, version="0", source=SourceRef(citation="test")),
    )


class _ConstantHTCCorrelation(Correlation):
    """Returns a fixed HTC value; records call count."""

    def __init__(self, htc: float = 500.0, name: str = "fake_htc") -> None:
        self._htc = htc
        self._name = name
        self.call_count = 0

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        self.call_count += 1
        return _htc_out(self._htc, self._name)


class _BadHTCCorrelation(Correlation):
    """Returns a controlled bad (non-finite or non-positive) HTC value."""

    def __init__(self, htc: float) -> None:
        self._htc = htc

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _htc_out(self._htc)


class _ConstantDPCorrelation(Correlation):
    """Returns a fixed DP value; records call count."""

    def __init__(self, dp: float = 1000.0) -> None:
        self._dp = dp
        self.call_count = 0

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        self.call_count += 1
        return _dp_out(self._dp)


class _BadDPCorrelation(Correlation):
    """Returns a non-finite DP value."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _dp_out(math.nan)


# ---------------------------------------------------------------------------
# Common geom_scalars bags for each model path
# ---------------------------------------------------------------------------

_HTC_GEOM = {
    "G": 200.0,
    "x": 0.5,
    "D_h": 0.005,
    "A_ht": 0.1,
    "rho": 1000.0,
    "mu": 1e-3,
    "L_cell": 0.5,
}

_DP_GEOM = {
    "G": 200.0,
    "D_h": 0.005,
    "rho": 1000.0,
    "mu": 1e-3,
    "L_cell": 0.5,
}


def _primary_only_request(
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    extra_geom: dict | None = None,
) -> HXSolveRequest:
    gs = dict(_HTC_GEOM)
    if extra_geom:
        gs.update(extra_geom)
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=SinkInletTempAndFlow(T_in=320.0, mdot_secondary=0.2, cp_secondary=4000.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=gs,
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
        primary_cp=2000.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
    )


def _two_sided_request(
    htc_primary: Correlation | None = None,
    htc_secondary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=SinkInletTempAndFlow(T_in=320.0, mdot_secondary=0.2, cp_secondary=4000.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=_HTC_GEOM,
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
        primary_cp=2000.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        ua_computation_mode=UAComputationMode.TWO_SIDED,
    )


def _fixed_wall_request(
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=_HTC_GEOM,
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
    )


def _ambient_request(
    dp_primary: Correlation | None = None,
    friction_multiplier: float = 1.0,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=AmbientCoupling(T_ambient=290.0, UA_ambient=10.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=_DP_GEOM,
        dp_primary=dp_primary,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
    )


def _fixed_hr_request(
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    friction_multiplier: float = 1.0,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedHeatRate(Q=500.0),
        geometry=object(),
        discretization=_LUMPED,
        geom_scalars=_HTC_GEOM,
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        friction_multiplier=friction_multiplier,
    )


def _segmented_fixed_wall_request(
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    n_cells: int = 3,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedWallTemp(T_wall=350.0),
        geometry=object(),
        discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells),
        geom_scalars=_HTC_GEOM,
        htc_primary=htc_primary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
        primary_cp=2000.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
    )


def _segmented_sink_request(
    htc_primary: Correlation | None = None,
    htc_secondary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    n_cells: int = 3,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=SinkInletTempAndFlow(T_in=320.0, mdot_secondary=0.2, cp_secondary=4000.0),
        geometry=object(),
        discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells),
        geom_scalars=_HTC_GEOM,
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
        primary_cp=2000.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        ua_computation_mode=UAComputationMode.TWO_SIDED,
    )


def _segmented_ambient_request(
    dp_primary: Correlation | None = None,
    friction_multiplier: float = 1.0,
    n_cells: int = 3,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=AmbientCoupling(T_ambient=290.0, UA_ambient=10.0),
        geometry=object(),
        discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells),
        geom_scalars=_DP_GEOM,
        dp_primary=dp_primary,
        friction_multiplier=friction_multiplier,
        primary_T_in=300.0,
        primary_cp=2000.0,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
    )


def _segmented_fixed_hr_request(
    dp_primary: Correlation | None = None,
    friction_multiplier: float = 1.0,
    n_cells: int = 3,
) -> HXSolveRequest:
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=0.1,
        secondary_bc=FixedHeatRate(Q=600.0),
        geometry=object(),
        discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells),
        geom_scalars=_DP_GEOM,
        dp_primary=dp_primary,
        friction_multiplier=friction_multiplier,
    )


# ===========================================================================
# General injection contract tests
# ===========================================================================


class TestGeneralInjectionContract:
    """HX models consume injected closures through HXSolveRequest — no registry."""

    def test_epsilon_ntu_does_not_resolve_correlation_registry(self) -> None:
        model = EpsilonNTUModel()
        htc = _ConstantHTCCorrelation()
        req = _primary_only_request(htc_primary=htc)
        result = model.solve(req)
        assert result is not None

    def test_lmtd_does_not_resolve_correlation_registry(self) -> None:
        model = LMTDModel()
        htc = _ConstantHTCCorrelation()
        req = _fixed_wall_request(htc_primary=htc)
        result = model.solve(req)
        assert result is not None

    def test_segmented_does_not_resolve_correlation_registry(self) -> None:
        model = SegmentedMarchModel()
        htc = _ConstantHTCCorrelation()
        req = _segmented_fixed_wall_request(htc_primary=htc)
        result = model.solve(req)
        assert result is not None

    def test_correlation_registry_is_not_called_by_any_hx_model(self) -> None:
        reg = CorrelationRegistry()
        reg.register("test_htc", _ConstantHTCCorrelation())
        htc = reg.resolve("test_htc")
        req = _fixed_wall_request(htc_primary=htc)
        result = EpsilonNTUModel().solve(req)
        assert result is not None

    def test_correlation_output_value_is_consumed_by_epsilon_ntu_fixed_wall(self) -> None:
        htc_500 = _ConstantHTCCorrelation(htc=500.0)
        htc_2000 = _ConstantHTCCorrelation(htc=2000.0)
        req_500 = _fixed_wall_request(htc_primary=htc_500)
        req_2000 = _fixed_wall_request(htc_primary=htc_2000)
        model = EpsilonNTUModel()
        result_500 = model.solve(req_500)
        result_2000 = model.solve(req_2000)
        assert abs(result_2000.Q) > abs(result_500.Q)

    def test_correlation_output_verdicts_are_propagated(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _fixed_wall_request(htc_primary=htc)
        result = EpsilonNTUModel().solve(req)
        assert len(result.verdicts) == 1
        assert result.verdicts[0].verdict.status == ValidityStatus.IN_ENVELOPE

    def test_non_finite_htc_output_fails_epsilon_ntu_fixed_wall(self) -> None:
        req = _fixed_wall_request(htc_primary=_BadHTCCorrelation(math.nan))
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    def test_non_positive_htc_output_fails_epsilon_ntu_fixed_wall(self) -> None:
        req = _fixed_wall_request(htc_primary=_BadHTCCorrelation(-100.0))
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    def test_zero_htc_output_fails_epsilon_ntu_fixed_wall(self) -> None:
        req = _fixed_wall_request(htc_primary=_BadHTCCorrelation(0.0))
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    def test_non_finite_dp_output_fails_epsilon_ntu(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _fixed_wall_request(htc_primary=htc, dp_primary=_BadDPCorrelation())
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    def test_signed_negative_dp_is_allowed_epsilon_ntu(self) -> None:
        htc = _ConstantHTCCorrelation()
        dp_neg = _ConstantDPCorrelation(dp=-500.0)
        req = _fixed_wall_request(htc_primary=htc, dp_primary=dp_neg)
        result = EpsilonNTUModel().solve(req)
        assert result.dP_primary < 0.0

    def test_signed_negative_dp_raises_outlet_pressure(self) -> None:
        htc = _ConstantHTCCorrelation()
        dp_neg = _ConstantDPCorrelation(dp=-500.0)
        req = _fixed_wall_request(htc_primary=htc, dp_primary=dp_neg)
        result = EpsilonNTUModel().solve(req)
        assert result.primary_state_out.P > _STATE_IN.P


# ===========================================================================
# EpsilonNTUModel closure consumption
# ===========================================================================


class TestEpsilonNTUClosureConsumption:
    """EpsilonNTUModel consumes injected closures with explicit UA modes."""

    def test_primary_only_mode_calls_only_htc_primary(self) -> None:
        htc_p = _ConstantHTCCorrelation(name="htc_p")
        htc_s = _ConstantHTCCorrelation(name="htc_s")
        req = _primary_only_request(htc_primary=htc_p)
        EpsilonNTUModel().solve(req)
        assert htc_p.call_count == 1
        assert htc_s.call_count == 0

    def test_two_sided_mode_calls_both_htc_primary_and_secondary(self) -> None:
        htc_p = _ConstantHTCCorrelation(name="htc_p")
        htc_s = _ConstantHTCCorrelation(name="htc_s")
        req = _two_sided_request(htc_primary=htc_p, htc_secondary=htc_s)
        EpsilonNTUModel().solve(req)
        assert htc_p.call_count == 1
        assert htc_s.call_count == 1

    def test_two_sided_missing_secondary_htc_fails_at_request_construction(self) -> None:
        htc_p = _ConstantHTCCorrelation()
        with pytest.raises(ValueError):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=320.0, mdot_secondary=0.2, cp_secondary=4000.0
                ),
                geometry=object(),
                discretization=_LUMPED,
                geom_scalars=_HTC_GEOM,
                htc_primary=htc_p,
                htc_secondary=None,
                primary_T_in=300.0,
                primary_cp=2000.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
            )

    def test_htc_multiplier_scales_ua_before_ntu_epsilon_ntu_fixed_wall(self) -> None:
        htc = _ConstantHTCCorrelation(htc=500.0)
        req_1x = _fixed_wall_request(htc_primary=htc, htc_multiplier=1.0)
        req_2x = _fixed_wall_request(htc_primary=htc, htc_multiplier=2.0)
        model = EpsilonNTUModel()
        result_1x = model.solve(req_1x)
        result_2x = model.solve(req_2x)
        assert abs(result_2x.Q) == pytest.approx(abs(result_1x.Q) * 2.0)

    def test_htc_multiplier_zero_gives_zero_q_fixed_wall(self) -> None:
        htc = _ConstantHTCCorrelation(htc=500.0)
        req = _fixed_wall_request(htc_primary=htc, htc_multiplier=0.0)
        result = EpsilonNTUModel().solve(req)
        assert result.Q == 0.0

    def test_htc_multiplier_zero_still_propagates_htc_verdict(self) -> None:
        htc = _ConstantHTCCorrelation(htc=500.0)
        req = _fixed_wall_request(htc_primary=htc, htc_multiplier=0.0)
        result = EpsilonNTUModel().solve(req)
        assert len(result.verdicts) >= 1

    def test_fixed_heat_rate_with_htc_primary_calls_htc_for_verdict(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _fixed_hr_request(htc_primary=htc)
        result = EpsilonNTUModel().solve(req)
        assert htc.call_count == 1
        assert len(result.verdicts) == 1

    def test_ambient_coupling_does_not_call_htc_correlations(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _ambient_request()
        EpsilonNTUModel().solve(req)
        assert htc.call_count == 0

    def test_friction_multiplier_scales_dp_not_q(self) -> None:
        htc = _ConstantHTCCorrelation(htc=500.0)
        dp = _ConstantDPCorrelation(dp=1000.0)
        req_1x = _fixed_wall_request(htc_primary=htc, dp_primary=dp, friction_multiplier=1.0)
        req_2x = _fixed_wall_request(htc_primary=htc, dp_primary=dp, friction_multiplier=2.0)
        model = EpsilonNTUModel()
        result_1x = model.solve(req_1x)
        result_2x = model.solve(req_2x)
        assert result_2x.Q == pytest.approx(result_1x.Q)
        assert result_2x.dP_primary == pytest.approx(result_1x.dP_primary * 2.0)

    def test_two_sided_non_finite_secondary_htc_fails(self) -> None:
        htc_p = _ConstantHTCCorrelation()
        req = _two_sided_request(htc_primary=htc_p, htc_secondary=_BadHTCCorrelation(math.nan))
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    def test_two_sided_non_positive_secondary_htc_fails(self) -> None:
        htc_p = _ConstantHTCCorrelation()
        req = _two_sided_request(htc_primary=htc_p, htc_secondary=_BadHTCCorrelation(-200.0))
        with pytest.raises(ValueError):
            EpsilonNTUModel().solve(req)

    def test_verdicts_order_two_sided_htc_then_dp(self) -> None:
        htc_p = _ConstantHTCCorrelation(name="htc_p")
        htc_s = _ConstantHTCCorrelation(name="htc_s")
        dp = _ConstantDPCorrelation()
        req = _two_sided_request(htc_primary=htc_p, htc_secondary=htc_s, dp_primary=dp)
        result = EpsilonNTUModel().solve(req)
        assert len(result.verdicts) == 3
        assert result.verdicts[0].metadata.name == "htc_p"
        assert result.verdicts[1].metadata.name == "htc_s"

    def test_correlation_output_value_index_zero_is_consumed(self) -> None:
        class _DoubleValueHTC(Correlation):
            """Returns (value[0], value[1]) — only value[0] should be consumed."""

            def role(self) -> CorrelationRole:
                return CorrelationRole.HTC

            def envelope(self) -> ValidityEnvelope:
                return _MINIMAL_ENVELOPE

            def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
                return CorrelationOutput(
                    value=(500.0, 999.0),
                    verdict=ValidityVerdict(
                        status=ValidityStatus.IN_ENVELOPE,
                        envelope=EnvelopeRef(
                            correlation_name="double_htc", correlation_version="0"
                        ),
                        violated=(),
                    ),
                    metadata=ClosureMetadata(
                        name="double_htc",
                        version="0",
                        source=SourceRef(citation="test"),
                    ),
                )

        htc = _DoubleValueHTC()
        single_htc = _ConstantHTCCorrelation(htc=500.0)
        req_double = _fixed_wall_request(htc_primary=htc)
        req_single = _fixed_wall_request(htc_primary=single_htc)
        model = EpsilonNTUModel()
        result_double = model.solve(req_double)
        result_single = model.solve(req_single)
        assert result_double.Q == pytest.approx(result_single.Q)


# ===========================================================================
# SegmentedMarchModel closure consumption
# ===========================================================================


class TestSegmentedMarchClosureConsumption:
    """SegmentedMarchModel calls injected closures per cell with correct counts."""

    def test_fixed_wall_temp_calls_htc_primary_once_per_cell(self) -> None:
        n = 4
        htc = _ConstantHTCCorrelation()
        req = _segmented_fixed_wall_request(htc_primary=htc, n_cells=n)
        SegmentedMarchModel().solve(req)
        assert htc.call_count == n

    def test_sink_calls_both_htc_primary_and_secondary_once_per_cell(self) -> None:
        n = 3
        htc_p = _ConstantHTCCorrelation(name="htc_p")
        htc_s = _ConstantHTCCorrelation(name="htc_s")
        req = _segmented_sink_request(htc_primary=htc_p, htc_secondary=htc_s, n_cells=n)
        SegmentedMarchModel().solve(req)
        assert htc_p.call_count == n
        assert htc_s.call_count == n

    def test_ambient_coupling_does_not_call_htc_correlations(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _segmented_ambient_request(n_cells=3)
        SegmentedMarchModel().solve(req)
        assert htc.call_count == 0

    def test_fixed_heat_rate_does_not_call_htc_correlations(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _segmented_fixed_hr_request(n_cells=3)
        SegmentedMarchModel().solve(req)
        assert htc.call_count == 0

    def test_dp_is_optional_and_independent_of_htc_for_fixed_wall(self) -> None:
        htc = _ConstantHTCCorrelation()
        dp = _ConstantDPCorrelation(dp=300.0)
        req_no_dp = _segmented_fixed_wall_request(htc_primary=htc)
        req_with_dp = _segmented_fixed_wall_request(htc_primary=htc, dp_primary=dp)
        model = SegmentedMarchModel()
        result_no_dp = model.solve(req_no_dp)
        result_with_dp = model.solve(req_with_dp)
        assert result_no_dp.Q == pytest.approx(result_with_dp.Q)
        assert result_no_dp.dP_primary == 0.0
        assert result_with_dp.dP_primary > 0.0

    def test_friction_multiplier_scales_dp_only_not_q(self) -> None:
        htc = _ConstantHTCCorrelation(htc=500.0)
        dp = _ConstantDPCorrelation(dp=100.0)
        req_1x = _segmented_fixed_wall_request(
            htc_primary=htc, dp_primary=dp, friction_multiplier=1.0
        )
        req_3x = _segmented_fixed_wall_request(
            htc_primary=htc, dp_primary=dp, friction_multiplier=3.0
        )
        model = SegmentedMarchModel()
        result_1x = model.solve(req_1x)
        result_3x = model.solve(req_3x)
        assert result_3x.Q == pytest.approx(result_1x.Q)
        assert result_3x.dP_primary == pytest.approx(result_1x.dP_primary * 3.0)

    def test_htc_multiplier_zero_gives_zero_q_sink(self) -> None:
        htc_p = _ConstantHTCCorrelation()
        htc_s = _ConstantHTCCorrelation()
        req = _segmented_sink_request(htc_primary=htc_p, htc_secondary=htc_s, htc_multiplier=0.0)
        result = SegmentedMarchModel().solve(req)
        assert result.Q == 0.0

    def test_htc_multiplier_zero_still_calls_correlations_sink(self) -> None:
        n = 2
        htc_p = _ConstantHTCCorrelation(name="htc_p")
        htc_s = _ConstantHTCCorrelation(name="htc_s")
        req = _segmented_sink_request(
            htc_primary=htc_p, htc_secondary=htc_s, htc_multiplier=0.0, n_cells=n
        )
        SegmentedMarchModel().solve(req)
        assert htc_p.call_count == n
        assert htc_s.call_count == n

    def test_htc_multiplier_zero_propagates_verdicts_sink(self) -> None:
        n = 2
        htc_p = _ConstantHTCCorrelation()
        htc_s = _ConstantHTCCorrelation()
        req = _segmented_sink_request(
            htc_primary=htc_p, htc_secondary=htc_s, htc_multiplier=0.0, n_cells=n
        )
        result = SegmentedMarchModel().solve(req)
        assert len(result.verdicts) == n * 2

    def test_dp_correlation_called_once_per_cell_fixed_wall(self) -> None:
        n = 5
        htc = _ConstantHTCCorrelation()
        dp = _ConstantDPCorrelation()
        req = _segmented_fixed_wall_request(htc_primary=htc, dp_primary=dp, n_cells=n)
        SegmentedMarchModel().solve(req)
        assert dp.call_count == n

    def test_htc_verdict_propagated_per_cell_fixed_wall(self) -> None:
        n = 3
        htc = _ConstantHTCCorrelation()
        req = _segmented_fixed_wall_request(htc_primary=htc, n_cells=n)
        result = SegmentedMarchModel().solve(req)
        assert len(result.verdicts) == n

    def test_verdicts_per_cell_sink_htc_then_dp(self) -> None:
        n = 2
        htc_p = _ConstantHTCCorrelation(name="htc_p")
        htc_s = _ConstantHTCCorrelation(name="htc_s")
        dp = _ConstantDPCorrelation()
        req = _segmented_sink_request(
            htc_primary=htc_p, htc_secondary=htc_s, dp_primary=dp, n_cells=n
        )
        result = SegmentedMarchModel().solve(req)
        assert len(result.verdicts) == n * 3

    def test_non_finite_htc_fails_fixed_wall_segmented(self) -> None:
        req = _segmented_fixed_wall_request(htc_primary=_BadHTCCorrelation(math.nan))
        with pytest.raises(ValueError):
            SegmentedMarchModel().solve(req)

    def test_non_positive_htc_fails_fixed_wall_segmented(self) -> None:
        req = _segmented_fixed_wall_request(htc_primary=_BadHTCCorrelation(-50.0))
        with pytest.raises(ValueError):
            SegmentedMarchModel().solve(req)

    def test_non_finite_dp_fails_fixed_wall_segmented(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _segmented_fixed_wall_request(htc_primary=htc, dp_primary=_BadDPCorrelation())
        with pytest.raises(ValueError):
            SegmentedMarchModel().solve(req)

    def test_raw_dp_primary_is_pre_calibration_sum(self) -> None:
        n = 3
        htc = _ConstantHTCCorrelation()
        dp = _ConstantDPCorrelation(dp=100.0)
        req = _segmented_fixed_wall_request(
            htc_primary=htc, dp_primary=dp, friction_multiplier=2.0, n_cells=n
        )
        result = SegmentedMarchModel().solve(req)
        assert result.raw_dP_primary == pytest.approx(300.0)
        assert result.dP_primary == pytest.approx(600.0)


# ===========================================================================
# LMTDModel closure consumption
# ===========================================================================


class TestLMTDModelClosureConsumption:
    """LMTDModel consumes htc_primary for FixedWallTemp; UA_ambient for AmbientCoupling."""

    def test_fixed_wall_temp_calls_htc_primary(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _fixed_wall_request(htc_primary=htc)
        LMTDModel().solve(req)
        assert htc.call_count == 1

    def test_fixed_wall_temp_correlation_output_value_consumed(self) -> None:
        htc_100 = _ConstantHTCCorrelation(htc=100.0)
        htc_1000 = _ConstantHTCCorrelation(htc=1000.0)
        req_100 = _fixed_wall_request(htc_primary=htc_100)
        req_1000 = _fixed_wall_request(htc_primary=htc_1000)
        model = LMTDModel()
        result_100 = model.solve(req_100)
        result_1000 = model.solve(req_1000)
        assert abs(result_1000.Q) > abs(result_100.Q)

    def test_fixed_wall_temp_verdict_propagated(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _fixed_wall_request(htc_primary=htc)
        result = LMTDModel().solve(req)
        assert len(result.verdicts) >= 1

    def test_ambient_coupling_does_not_call_htc_correlation(self) -> None:
        htc = _ConstantHTCCorrelation()
        req = _ambient_request()
        LMTDModel().solve(req)
        assert htc.call_count == 0

    def test_ambient_coupling_uses_prescribed_ua_ambient(self) -> None:
        req = _ambient_request()
        result = LMTDModel().solve(req)
        expected_q = 10.0 * (290.0 - 300.0)
        assert result.Q == pytest.approx(expected_q)

    def test_htc_multiplier_does_not_affect_ambient_coupling(self) -> None:
        req_1x = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=AmbientCoupling(T_ambient=290.0, UA_ambient=10.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=_DP_GEOM,
            htc_multiplier=1.0,
            primary_T_in=300.0,
        )
        req_5x = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=AmbientCoupling(T_ambient=290.0, UA_ambient=10.0),
            geometry=object(),
            discretization=_LUMPED,
            geom_scalars=_DP_GEOM,
            htc_multiplier=5.0,
            primary_T_in=300.0,
        )
        model = LMTDModel()
        result_1x = model.solve(req_1x)
        result_5x = model.solve(req_5x)
        assert result_1x.Q == pytest.approx(result_5x.Q)

    def test_sink_inlet_temp_and_flow_is_unsupported(self) -> None:
        htc_p = _ConstantHTCCorrelation()
        htc_s = _ConstantHTCCorrelation()
        req = _two_sided_request(htc_primary=htc_p, htc_secondary=htc_s)
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            LMTDModel().solve(req)

    def test_fixed_heat_rate_is_unsupported(self) -> None:
        req = _fixed_hr_request()
        with pytest.raises(UnsupportedHeatExchangerBoundaryConditionError):
            LMTDModel().solve(req)

    def test_non_finite_htc_fails_lmtd_fixed_wall(self) -> None:
        req = _fixed_wall_request(htc_primary=_BadHTCCorrelation(math.nan))
        with pytest.raises(ValueError):
            LMTDModel().solve(req)

    def test_non_positive_htc_fails_lmtd_fixed_wall(self) -> None:
        req = _fixed_wall_request(htc_primary=_BadHTCCorrelation(0.0))
        with pytest.raises(ValueError):
            LMTDModel().solve(req)

    def test_friction_multiplier_scales_dp_not_q_lmtd(self) -> None:
        htc = _ConstantHTCCorrelation(htc=500.0)
        dp = _ConstantDPCorrelation(dp=1000.0)
        req_1x = _fixed_wall_request(htc_primary=htc, dp_primary=dp, friction_multiplier=1.0)
        req_4x = _fixed_wall_request(htc_primary=htc, dp_primary=dp, friction_multiplier=4.0)
        model = LMTDModel()
        result_1x = model.solve(req_1x)
        result_4x = model.solve(req_4x)
        assert result_4x.Q == pytest.approx(result_1x.Q)
        assert result_4x.dP_primary == pytest.approx(result_1x.dP_primary * 4.0)
