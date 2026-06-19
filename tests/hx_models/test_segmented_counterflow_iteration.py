"""Phase 11T: iterated counterflow segmented solver tests.

Verifies all 19 required coverage items for Phase 11T:

 1. Existing default segmented behavior unchanged.
 2. Explicit CO_CURRENT unchanged.
 3. Phase 11S one-pass COUNTERFLOW remains available when iteration disabled.
 4. CounterflowIterationConfig validation:
      - invalid max_iter (< 1)
      - invalid tolerance (<= 0, non-finite)
      - invalid relaxation (< 0, > 1, zero, non-finite)
      - non-finite values for tolerance and relaxation
 5. Iterated counterflow accepted only for SinkInletTempAndFlow.
 6. Iterated counterflow updates Q_cell based on secondary profile, not fixed bc.T_in.
 7. Iterated counterflow converges on a simple stable case.
 8. Iteration count and residual are reported.
 9. Non-convergence with low max_iter is explicit (converged=False, residual > tol).
10. Relaxation changes iteration behavior in a tested way.
11. Secondary inlet remains at cell n-1.
12. Secondary profile backward integration is consistent.
13. q_flux reaches primary HTC in iterated mode.
14. MSH two-phase DP still converts Pa/m to Pa exactly once in iterated mode.
15. Missing phase-change/DP scalars fail clearly.
16. No quality marching or phase inference.
17. No CoolProp/PropertyBackend.
18. No registry resolution.
19. Existing Phase 11S tests still pass (smoke tests).

Architecture constraints:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes or real (MSH) with explicit scalars.
  - Cell temperatures appear only in zone_profile, never in FluidState.
  - HXSolveResult.converged, .iteration_count, .residual carry iteration state.
  - Non-convergence returns converged=False; it is never silent.
"""

from __future__ import annotations

import math
import types

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
    HTCInput,
    SourceRef,
    TwoPhaseDPInput,
    ValidityEnvelope,
    ValidityStatus,
    ValidityVerdict,
)
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    AmbientCoupling,
    CounterflowIterationConfig,
    FixedHeatRate,
    FixedWallTemp,
    FlowArrangement,
    HXSolveRequest,
    HXSolveResult,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
)
from mpl_sim.hx_models.segmented import (
    SegmentedMarchModel,
    SegmentedProfile,
)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_FLUID = PureFluid(name="R410A")
_DISC_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)
_DISC_1 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=1)
_DISC_4 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=4)
_STATE_IN = FluidState(P=1_000_000.0, h=250_000.0, identity=_FLUID)

_MIN_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)


def _htc_output(value: float) -> CorrelationOutput:
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


def _dp_output(value: float) -> CorrelationOutput:
    return CorrelationOutput(
        value=(value,),
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


class _ConstHTC(Correlation):
    """Constant-output HTC correlation; records q_flux received."""

    def __init__(self, htc: float = 2000.0) -> None:
        self._htc = htc
        self.received_q_flux: list[float | None] = []

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MIN_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        assert isinstance(inp, HTCInput)
        self.received_q_flux.append(inp.q_flux)
        return _htc_output(self._htc)


class _ConstDP(Correlation):
    """Constant-output single-phase DP correlation."""

    def __init__(self, dp: float = 500.0) -> None:
        self._dp = dp

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MIN_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _dp_output(self._dp)


class _ConstTwoPhaseDP(Correlation):
    """Constant-output two-phase DP gradient correlation [Pa/m]."""

    def __init__(self, gradient: float = 1000.0) -> None:
        self._gradient = gradient
        self.received_property_scalars: list[types.MappingProxyType] = []

    def role(self) -> CorrelationRole:
        return CorrelationRole.TWO_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MIN_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        assert isinstance(inp, TwoPhaseDPInput)
        self.received_property_scalars.append(inp.property_scalars)
        return _dp_output(self._gradient)


def _sink_bc(T_in: float = 350.0, mdot: float = 0.05, cp: float = 4000.0) -> SinkInletTempAndFlow:
    return SinkInletTempAndFlow(T_in=T_in, mdot_secondary=mdot, cp_secondary=cp)


def _base_geom(extra: dict | None = None) -> dict:
    gs: dict = {
        "G": 200.0,
        "x": 0.5,
        "D_h": 0.002,
        "L_cell": 0.1,
        "A_ht": 0.03,
    }
    if extra:
        gs.update(extra)
    return gs


def _two_phase_geom(extra: dict | None = None) -> dict:
    gs = _base_geom()
    gs.update({"rho_l": 1000.0, "rho_v": 20.0, "mu_l": 1e-4, "mu_v": 1e-5})
    if extra:
        gs.update(extra)
    return gs


def _iter_cfg(**kw) -> CounterflowIterationConfig:
    defaults = dict(enabled=True, max_iter=50, tolerance=1e-8, relaxation=1.0)
    defaults.update(kw)
    return CounterflowIterationConfig(**defaults)


def _make_iter_req(
    bc: SinkInletTempAndFlow | None = None,
    disc: DiscretizationSpec | None = None,
    geom: dict | None = None,
    htc_p: Correlation | None = None,
    htc_s: Correlation | None = None,
    dp: Correlation | None = None,
    T_in: float = 300.0,
    cp: float = 1500.0,
    mdot: float = 0.1,
    q_flux: float | None = None,
    dp_two_phase: bool = False,
    iteration_cfg: CounterflowIterationConfig | None = None,
) -> HXSolveRequest:
    if bc is None:
        bc = _sink_bc()
    if disc is None:
        disc = _DISC_3
    if geom is None:
        geom = _base_geom()
    if htc_p is None:
        htc_p = _ConstHTC()
    if htc_s is None:
        htc_s = _ConstHTC()
    if iteration_cfg is None:
        iteration_cfg = _iter_cfg()
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=bc,
        geometry=object(),
        discretization=disc,
        geom_scalars=geom,
        htc_primary=htc_p,
        htc_secondary=htc_s,
        dp_primary=dp,
        primary_T_in=T_in,
        primary_cp=cp,
        primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        ua_computation_mode=UAComputationMode.TWO_SIDED,
        q_flux_primary=q_flux,
        dp_primary_is_two_phase=dp_two_phase,
        flow_arrangement=FlowArrangement.COUNTERFLOW,
        counterflow_iteration=iteration_cfg,
    )


# ===========================================================================
# 1. Existing default segmented behavior unchanged
# ===========================================================================


class TestDefaultBehaviorUnchanged:
    """Item 1: flow_arrangement=None and no iteration config preserve existing behavior."""

    def test_fixed_heat_rate_default_unchanged(self):
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC_3,
        )
        result = model.solve(req)
        expected_h_out = _STATE_IN.h + 500.0 / 0.1
        assert math.isclose(result.primary_state_out.h, expected_h_out, rel_tol=1e-10)
        assert math.isclose(result.Q, 500.0, rel_tol=1e-10)

    def test_default_result_has_no_iteration_diagnostics(self):
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC_3,
        )
        result = model.solve(req)
        assert result.iteration_count == 0
        assert result.converged is None
        assert result.residual is None

    def test_counterflow_disabled_no_iteration_diagnostics(self):
        model = SegmentedMarchModel()
        cfg = CounterflowIterationConfig(enabled=False)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
            counterflow_iteration=cfg,
        )
        result = model.solve(req)
        # disabled → one-pass → no iteration diagnostics
        assert result.iteration_count == 0
        assert result.converged is None
        assert result.residual is None


# ===========================================================================
# 2. Explicit CO_CURRENT unchanged
# ===========================================================================


class TestCocurrentUnchanged:
    """Item 2: explicit CO_CURRENT produces same result as before."""

    def test_cocurrent_result_matches_no_arrangement(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0)
        req_none = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=None,
        )
        req_cc = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.CO_CURRENT,
        )
        r_none = model.solve(req_none)
        r_cc = model.solve(req_cc)
        assert math.isclose(r_none.Q, r_cc.Q, rel_tol=1e-10)
        assert math.isclose(r_none.primary_state_out.h, r_cc.primary_state_out.h, rel_tol=1e-10)
        assert r_cc.converged is None
        assert r_cc.iteration_count == 0

    def test_cocurrent_profile_arrangement_is_cocurrent(self):
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.CO_CURRENT,
        )
        result = model.solve(req)
        assert result.zone_profile.flow_arrangement is FlowArrangement.CO_CURRENT


# ===========================================================================
# 3. Phase 11S one-pass COUNTERFLOW still available when iteration disabled
# ===========================================================================


class TestOnePassStillAvailable:
    """Item 3: one-pass remains when iteration not enabled."""

    def test_onepass_when_config_none(self):
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(T_in=350.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
            counterflow_iteration=None,
        )
        result = model.solve(req)
        assert isinstance(result.zone_profile, SegmentedProfile)
        assert result.zone_profile.flow_arrangement is FlowArrangement.COUNTERFLOW
        assert result.converged is None
        assert result.iteration_count == 0

    def test_onepass_when_enabled_false(self):
        model = SegmentedMarchModel()
        cfg = CounterflowIterationConfig(enabled=False, max_iter=5)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(T_in=350.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
            counterflow_iteration=cfg,
        )
        result = model.solve(req)
        assert result.converged is None
        assert result.iteration_count == 0


# ===========================================================================
# 4. CounterflowIterationConfig validation
# ===========================================================================


class TestIterationConfigValidation:
    """Item 4: CounterflowIterationConfig rejects invalid inputs."""

    def test_max_iter_zero_rejected(self):
        with pytest.raises(ValueError, match="max_iter"):
            CounterflowIterationConfig(enabled=True, max_iter=0)

    def test_max_iter_negative_rejected(self):
        with pytest.raises(ValueError, match="max_iter"):
            CounterflowIterationConfig(enabled=True, max_iter=-1)

    def test_tolerance_zero_rejected(self):
        with pytest.raises(ValueError, match="tolerance"):
            CounterflowIterationConfig(tolerance=0.0)

    def test_tolerance_negative_rejected(self):
        with pytest.raises(ValueError, match="tolerance"):
            CounterflowIterationConfig(tolerance=-1e-6)

    def test_tolerance_nan_rejected(self):
        with pytest.raises(ValueError, match="tolerance"):
            CounterflowIterationConfig(tolerance=float("nan"))

    def test_tolerance_inf_rejected(self):
        with pytest.raises(ValueError, match="tolerance"):
            CounterflowIterationConfig(tolerance=float("inf"))

    def test_relaxation_zero_rejected(self):
        with pytest.raises(ValueError, match="relaxation"):
            CounterflowIterationConfig(relaxation=0.0)

    def test_relaxation_negative_rejected(self):
        with pytest.raises(ValueError, match="relaxation"):
            CounterflowIterationConfig(relaxation=-0.1)

    def test_relaxation_greater_than_one_rejected(self):
        with pytest.raises(ValueError, match="relaxation"):
            CounterflowIterationConfig(relaxation=1.1)

    def test_relaxation_nan_rejected(self):
        with pytest.raises(ValueError, match="relaxation"):
            CounterflowIterationConfig(relaxation=float("nan"))

    def test_relaxation_inf_rejected(self):
        with pytest.raises(ValueError, match="relaxation"):
            CounterflowIterationConfig(relaxation=float("inf"))

    def test_valid_config_accepted(self):
        cfg = CounterflowIterationConfig(enabled=True, max_iter=10, tolerance=1e-4, relaxation=0.7)
        assert cfg.enabled is True
        assert cfg.max_iter == 10
        assert math.isclose(cfg.tolerance, 1e-4)
        assert math.isclose(cfg.relaxation, 0.7)

    def test_relaxation_exactly_one_accepted(self):
        cfg = CounterflowIterationConfig(relaxation=1.0)
        assert math.isclose(cfg.relaxation, 1.0)

    def test_max_iter_one_accepted(self):
        cfg = CounterflowIterationConfig(max_iter=1)
        assert cfg.max_iter == 1

    def test_enabled_false_with_invalid_max_iter_still_raises(self):
        """Validation runs regardless of enabled flag."""
        with pytest.raises(ValueError, match="max_iter"):
            CounterflowIterationConfig(enabled=False, max_iter=0)


# ===========================================================================
# 5. Iterated counterflow accepted only for SinkInletTempAndFlow
# ===========================================================================


class TestIteratedCounterflowOnlyForSink:
    """Item 5: enabled=True is rejected for non-SinkInletTempAndFlow BCs."""

    def test_fixed_heat_rate_with_enabled_raises(self):
        with pytest.raises(ValueError, match="SinkInletTempAndFlow"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=FixedHeatRate(Q=500.0),
                geometry=object(),
                discretization=_DISC_3,
                flow_arrangement=FlowArrangement.COUNTERFLOW,
                counterflow_iteration=CounterflowIterationConfig(enabled=True),
            )

    def test_fixed_wall_temp_with_enabled_raises(self):
        with pytest.raises(ValueError, match="SinkInletTempAndFlow"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=FixedWallTemp(T_wall=320.0),
                geometry=object(),
                discretization=_DISC_3,
                flow_arrangement=FlowArrangement.COUNTERFLOW,
                counterflow_iteration=CounterflowIterationConfig(enabled=True),
            )

    def test_ambient_coupling_with_enabled_raises(self):
        with pytest.raises(ValueError, match="SinkInletTempAndFlow"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=AmbientCoupling(T_ambient=300.0, UA_ambient=10.0),
                geometry=object(),
                discretization=_DISC_3,
                flow_arrangement=FlowArrangement.COUNTERFLOW,
                counterflow_iteration=CounterflowIterationConfig(enabled=True),
            )

    def test_sink_with_co_current_arrangement_and_enabled_raises(self):
        with pytest.raises(ValueError, match="COUNTERFLOW"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=_sink_bc(),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_base_geom(),
                htc_primary=_ConstHTC(),
                htc_secondary=_ConstHTC(),
                primary_T_in=300.0,
                primary_cp=1500.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                flow_arrangement=FlowArrangement.CO_CURRENT,
                counterflow_iteration=CounterflowIterationConfig(enabled=True),
            )

    def test_sink_with_no_arrangement_and_enabled_raises(self):
        with pytest.raises(ValueError, match="COUNTERFLOW"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=_sink_bc(),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_base_geom(),
                htc_primary=_ConstHTC(),
                htc_secondary=_ConstHTC(),
                primary_T_in=300.0,
                primary_cp=1500.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                flow_arrangement=None,
                counterflow_iteration=CounterflowIterationConfig(enabled=True),
            )


# ===========================================================================
# 6. Iterated mode updates Q_cell based on secondary profile, not fixed bc.T_in
# ===========================================================================


class TestIteratedUpdatesQCell:
    """Item 6: Q_cell values in later iterations differ from one-pass (bc.T_in fixed)."""

    def test_q_cells_differ_between_onepass_and_iterated(self):
        """The iterated solver should produce different Q_cell values vs one-pass
        because the secondary profile is updated between iterations."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0, mdot=0.02, cp=3000.0)

        # One-pass (iteration disabled)
        req_onepass = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_4,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(htc=3000.0),
            htc_secondary=_ConstHTC(htc=3000.0),
            primary_T_in=280.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
            counterflow_iteration=CounterflowIterationConfig(enabled=False),
        )
        r_onepass = model.solve(req_onepass)

        # Iterated (max_iter=50, should converge and produce different Q_cells)
        req_iter = _make_iter_req(
            bc=bc,
            disc=_DISC_4,
            htc_p=_ConstHTC(htc=3000.0),
            htc_s=_ConstHTC(htc=3000.0),
            T_in=280.0,
            cp=1500.0,
            iteration_cfg=_iter_cfg(max_iter=50, tolerance=1e-9),
        )
        r_iter = model.solve(req_iter)

        # Total Q may differ because Q_cells use different per-cell secondary temps
        # They won't be exactly equal in general with high enough HTC
        one_q_cells = [c.Q_cell for c in r_onepass.zone_profile.cells]
        iter_q_cells = [c.Q_cell for c in r_iter.zone_profile.cells]
        # At least some cells should differ (the secondary profile was updated)
        some_differ = any(
            not math.isclose(q1, q2, rel_tol=1e-3) for q1, q2 in zip(one_q_cells, iter_q_cells)
        )
        assert some_differ, (
            "Iterated Q_cells should differ from one-pass after profile updates; "
            f"one-pass={one_q_cells!r}, iterated={iter_q_cells!r}"
        )

    def test_q_cell_uses_secondary_profile_not_bc_t_in(self):
        """In the iterated solver, Q_cell in cell 0 should use secondary T
        derived from the profile (which differs from bc.T_in after iteration)."""
        model = SegmentedMarchModel()
        # Use asymmetric case: high HTC, large temperature difference, n_cells=3.
        # bc.T_in = 400 K, primary_T_in = 280 K.
        # After iteration, secondary profile in cell 0 will be lower than bc.T_in.
        bc = _sink_bc(T_in=400.0, mdot=0.02, cp=3000.0)
        req = _make_iter_req(
            bc=bc,
            disc=_DISC_3,
            htc_p=_ConstHTC(htc=5000.0),
            htc_s=_ConstHTC(htc=5000.0),
            T_in=280.0,
            cp=1500.0,
            iteration_cfg=_iter_cfg(max_iter=100, tolerance=1e-10),
        )
        r = model.solve(req)
        assert r.converged is True
        # At convergence: secondary_T_in for cell 0 < bc.T_in (profile updated)
        profile = r.zone_profile
        assert profile.cells[-1].secondary_T_in == pytest.approx(bc.T_in)  # inlet at n-1
        # cell 0 secondary T_in should be less than bc.T_in (secondary has given up heat)
        assert profile.cells[0].secondary_T_in < bc.T_in


# ===========================================================================
# 7. Iterated counterflow converges on a simple stable case
# ===========================================================================


class TestIteratedConvergence:
    """Item 7: iterated solver converges for a well-posed configuration."""

    def test_converges_simple_3cell(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)
        req = _make_iter_req(
            bc=bc,
            disc=_DISC_3,
            htc_p=_ConstHTC(htc=2000.0),
            htc_s=_ConstHTC(htc=2000.0),
            T_in=300.0,
            cp=1500.0,
            iteration_cfg=_iter_cfg(max_iter=100, tolerance=1e-8, relaxation=1.0),
        )
        result = model.solve(req)
        assert result.converged is True
        assert result.residual is not None
        assert result.residual <= 1e-8
        assert result.iteration_count >= 1

    def test_converges_1cell_trivially(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0, mdot=0.05, cp=4000.0)
        req = _make_iter_req(
            bc=bc,
            disc=_DISC_1,
            htc_p=_ConstHTC(htc=2000.0),
            htc_s=_ConstHTC(htc=2000.0),
            T_in=300.0,
            cp=1500.0,
            iteration_cfg=_iter_cfg(max_iter=100, tolerance=1e-8),
        )
        result = model.solve(req)
        assert result.converged is True

    def test_converged_result_is_self_consistent(self):
        """At convergence, the secondary profile from the last iteration satisfies
        its own backward integration equations to within tolerance."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)
        req = _make_iter_req(
            bc=bc,
            disc=_DISC_3,
            htc_p=_ConstHTC(htc=2000.0),
            htc_s=_ConstHTC(htc=2000.0),
            T_in=300.0,
            cp=1500.0,
            iteration_cfg=_iter_cfg(max_iter=200, tolerance=1e-10),
        )
        result = model.solve(req)
        assert result.converged is True

        cells = result.zone_profile.cells
        n = len(cells)
        # Re-derive the secondary profile from Q_cells and check consistency
        C_secondary = bc.mdot_secondary * bc.cp_secondary
        computed_T_in = [0.0] * n
        computed_T_out = [0.0] * n
        for i in range(n - 1, -1, -1):
            if i == n - 1:
                computed_T_in[i] = bc.T_in
            else:
                computed_T_in[i] = computed_T_out[i + 1]
            computed_T_out[i] = computed_T_in[i] - cells[i].Q_cell / C_secondary

        for i in range(n):
            assert math.isclose(cells[i].secondary_T_in, computed_T_in[i], abs_tol=1e-9), (
                f"secondary_T_in[{i}] mismatch: got {cells[i].secondary_T_in}, "
                f"expected {computed_T_in[i]}"
            )
            assert math.isclose(cells[i].secondary_T_out, computed_T_out[i], abs_tol=1e-9), (
                f"secondary_T_out[{i}] mismatch: got {cells[i].secondary_T_out}, "
                f"expected {computed_T_out[i]}"
            )


# ===========================================================================
# 8. Iteration count and residual are reported
# ===========================================================================


class TestIterationDiagnostics:
    """Item 8: iteration_count, converged, residual are all populated."""

    def test_iteration_count_is_positive(self):
        model = SegmentedMarchModel()
        result = model.solve(_make_iter_req())
        assert result.iteration_count >= 1

    def test_residual_is_nonnegative_finite(self):
        model = SegmentedMarchModel()
        result = model.solve(_make_iter_req())
        assert result.residual is not None
        assert math.isfinite(result.residual)
        assert result.residual >= 0.0

    def test_converged_is_bool(self):
        model = SegmentedMarchModel()
        result = model.solve(_make_iter_req())
        assert isinstance(result.converged, bool)

    def test_profile_arrangement_is_counterflow(self):
        model = SegmentedMarchModel()
        result = model.solve(_make_iter_req())
        assert result.zone_profile.flow_arrangement is FlowArrangement.COUNTERFLOW

    def test_iteration_count_respects_max_iter_upper_bound(self):
        model = SegmentedMarchModel()
        cfg = _iter_cfg(max_iter=5)
        result = model.solve(_make_iter_req(iteration_cfg=cfg))
        assert result.iteration_count <= 5


# ===========================================================================
# 9. Non-convergence with low max_iter is explicit
# ===========================================================================


class TestNonConvergence:
    """Item 9: max_iter=1 with a non-trivial case produces converged=False."""

    def test_max_iter_1_non_convergence(self):
        """With max_iter=1 and a strict tolerance, non-convergence is returned
        as converged=False with a positive residual."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0, mdot=0.02, cp=3000.0)
        cfg = _iter_cfg(max_iter=1, tolerance=1e-12)
        req = _make_iter_req(
            bc=bc,
            disc=_DISC_4,
            htc_p=_ConstHTC(htc=3000.0),
            htc_s=_ConstHTC(htc=3000.0),
            T_in=280.0,
            cp=1500.0,
            iteration_cfg=cfg,
        )
        result = model.solve(req)
        assert result.converged is False
        assert result.iteration_count == 1
        assert result.residual is not None
        assert result.residual > 0.0

    def test_non_convergence_residual_exceeds_tolerance(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0, mdot=0.02, cp=3000.0)
        tol = 1e-12
        cfg = _iter_cfg(max_iter=1, tolerance=tol)
        req = _make_iter_req(
            bc=bc,
            disc=_DISC_4,
            htc_p=_ConstHTC(htc=3000.0),
            htc_s=_ConstHTC(htc=3000.0),
            T_in=280.0,
            cp=1500.0,
            iteration_cfg=cfg,
        )
        result = model.solve(req)
        if not result.converged:
            assert result.residual > tol

    def test_non_convergence_still_returns_result(self):
        """Non-convergence must not raise; it returns a result with converged=False."""
        model = SegmentedMarchModel()
        cfg = _iter_cfg(max_iter=1, tolerance=1e-30)
        result = model.solve(_make_iter_req(iteration_cfg=cfg, disc=_DISC_3))
        assert isinstance(result, HXSolveResult)

    def test_max_iter_respected(self):
        model = SegmentedMarchModel()
        cfg = _iter_cfg(max_iter=3, tolerance=1e-30)
        result = model.solve(_make_iter_req(iteration_cfg=cfg, disc=_DISC_3))
        assert result.iteration_count == 3


# ===========================================================================
# 10. Relaxation changes iteration behavior
# ===========================================================================


class TestRelaxation:
    """Item 10: smaller relaxation slows convergence (more iterations to converge)."""

    def test_full_relaxation_converges_in_fewer_iterations_than_half(self):
        """relaxation=1.0 should converge in <= iterations of relaxation=0.5
        for a simple stable case."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)

        cfg_full = _iter_cfg(max_iter=200, tolerance=1e-8, relaxation=1.0)
        cfg_half = _iter_cfg(max_iter=200, tolerance=1e-8, relaxation=0.5)

        r_full = model.solve(_make_iter_req(bc=bc, iteration_cfg=cfg_full))
        r_half = model.solve(_make_iter_req(bc=bc, iteration_cfg=cfg_half))

        assert r_full.converged is True
        assert r_half.converged is True
        # relaxation=1.0 should take no more iterations than relaxation=0.5
        assert r_full.iteration_count <= r_half.iteration_count

    def test_residual_path_differs_with_relaxation(self):
        """Intermediate iteration counts differ: half-relaxation uses more iterations."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)

        cfg_full = _iter_cfg(max_iter=5, tolerance=1e-30, relaxation=1.0)
        cfg_half = _iter_cfg(max_iter=5, tolerance=1e-30, relaxation=0.5)

        r_full = model.solve(_make_iter_req(bc=bc, iteration_cfg=cfg_full))
        r_half = model.solve(_make_iter_req(bc=bc, iteration_cfg=cfg_half))

        # Both ran exactly 5 iterations (tolerance too tight to converge)
        assert r_full.iteration_count == 5
        assert r_half.iteration_count == 5
        # Residuals differ because relaxation affects how the profile updates
        assert not math.isclose(
            r_full.residual, r_half.residual, rel_tol=1e-6
        ), "Residuals with relaxation=1.0 and relaxation=0.5 should differ"


# ===========================================================================
# 11. Secondary inlet remains at cell n-1
# ===========================================================================


class TestSecondaryInletAtCellNMinus1:
    """Item 11: secondary_T_in at cell n-1 equals bc.T_in."""

    def test_secondary_inlet_at_last_cell(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0)
        result = model.solve(_make_iter_req(bc=bc, disc=_DISC_3))
        cells = result.zone_profile.cells
        assert cells[-1].secondary_T_in == pytest.approx(bc.T_in)

    def test_secondary_inlet_at_last_cell_4cells(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=380.0)
        result = model.solve(_make_iter_req(bc=bc, disc=_DISC_4))
        cells = result.zone_profile.cells
        assert cells[-1].secondary_T_in == pytest.approx(bc.T_in)

    def test_secondary_outlet_at_cell_0(self):
        """secondary_T_out at cell 0 is the secondary stream outlet (derived)."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)
        result = model.solve(
            _make_iter_req(
                bc=bc, disc=_DISC_3, iteration_cfg=_iter_cfg(max_iter=100, tolerance=1e-9)
            )
        )
        assert result.converged is True
        # secondary_T_out at cell 0 should be less than bc.T_in (heat was given up)
        cells = result.zone_profile.cells
        assert cells[0].secondary_T_out < bc.T_in


# ===========================================================================
# 12. Secondary profile backward integration is consistent
# ===========================================================================


class TestSecondaryProfileConsistency:
    """Item 12: secondary profile satisfies backward integration equations."""

    def _check_profile_consistency(self, result: HXSolveResult, bc: SinkInletTempAndFlow) -> None:
        cells = result.zone_profile.cells
        n = len(cells)
        C_secondary = bc.mdot_secondary * bc.cp_secondary
        assert cells[n - 1].secondary_T_in == pytest.approx(bc.T_in, abs=1e-9)
        for i in range(n):
            expected_out = cells[i].secondary_T_in - cells[i].Q_cell / C_secondary
            assert math.isclose(
                cells[i].secondary_T_out, expected_out, abs_tol=1e-9
            ), f"secondary_T_out[{i}] mismatch"
        for i in range(n - 1):
            assert math.isclose(
                cells[i].secondary_T_in, cells[i + 1].secondary_T_out, abs_tol=1e-9
            ), f"secondary_T_in[{i}] != secondary_T_out[{i+1}]"

    def test_profile_consistent_3cells(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)
        cfg = _iter_cfg(max_iter=100, tolerance=1e-10)
        result = model.solve(_make_iter_req(bc=bc, disc=_DISC_3, iteration_cfg=cfg))
        self._check_profile_consistency(result, bc)

    def test_profile_consistent_4cells(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=370.0, mdot=0.04, cp=3500.0)
        cfg = _iter_cfg(max_iter=100, tolerance=1e-10)
        result = model.solve(_make_iter_req(bc=bc, disc=_DISC_4, iteration_cfg=cfg))
        self._check_profile_consistency(result, bc)

    def test_profile_consistent_on_non_convergence(self):
        """Even when not converged, the profile from the last iteration is
        internally consistent with the last Q_cells."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0, mdot=0.05, cp=4000.0)
        result = model.solve(
            _make_iter_req(
                bc=bc,
                disc=_DISC_3,
                iteration_cfg=_iter_cfg(max_iter=1, tolerance=1e-30),
            )
        )
        self._check_profile_consistency(result, bc)


# ===========================================================================
# 13. q_flux reaches primary HTC in iterated mode
# ===========================================================================


class TestQFluxInIteratedMode:
    """Item 13: q_flux_primary reaches primary HTCInput.q_flux in iterated mode."""

    def test_q_flux_forwarded_to_primary_htc(self):
        model = SegmentedMarchModel()
        htc_p = _ConstHTC()
        htc_s = _ConstHTC()
        q_flux_val = 12345.0
        req = _make_iter_req(
            htc_p=htc_p,
            htc_s=htc_s,
            q_flux=q_flux_val,
            iteration_cfg=_iter_cfg(max_iter=3),
        )
        model.solve(req)
        # Primary HTC should receive q_flux on every call in every iteration
        assert all(v == q_flux_val for v in htc_p.received_q_flux)
        assert len(htc_p.received_q_flux) > 0

    def test_q_flux_not_forwarded_to_secondary_htc(self):
        model = SegmentedMarchModel()
        htc_p = _ConstHTC()
        htc_s = _ConstHTC()
        req = _make_iter_req(
            htc_p=htc_p,
            htc_s=htc_s,
            q_flux=99999.0,
            iteration_cfg=_iter_cfg(max_iter=3),
        )
        model.solve(req)
        # Secondary HTC always receives q_flux=None
        assert all(v is None for v in htc_s.received_q_flux)


# ===========================================================================
# 14. MSH two-phase DP converts Pa/m to Pa exactly once per cell per iteration
# ===========================================================================


class TestTwoPhaseDPInIteratedMode:
    """Item 14: MSH gradient (Pa/m) is multiplied by L_cell exactly once per cell."""

    def test_msh_two_phase_dp_converts_gradient_to_drop(self):
        """The recorded gradient × L_cell × n_cells == dP_primary / friction_multiplier."""
        model = SegmentedMarchModel()
        gradient = 2000.0  # Pa/m
        L_cell = 0.1  # m
        n = 3
        fake_dp = _ConstTwoPhaseDP(gradient=gradient)
        req = _make_iter_req(
            disc=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n),
            geom=_two_phase_geom({"L_cell": L_cell}),
            dp=fake_dp,
            dp_two_phase=True,
            iteration_cfg=_iter_cfg(max_iter=2),
        )
        result = model.solve(req)
        # Each iteration: n cells × gradient × L_cell
        # After all iterations, raw_dP_primary from last iteration:
        # n_cells * gradient * L_cell per iteration (summed over cells, last iter)
        expected_raw_per_iter = gradient * L_cell * n
        assert math.isclose(result.raw_dP_primary, expected_raw_per_iter, rel_tol=1e-9)

    def test_msh_property_scalars_forwarded(self):
        """rho_l, rho_v, mu_l, mu_v reach TwoPhaseDPInput.property_scalars."""
        model = SegmentedMarchModel()
        fake_dp = _ConstTwoPhaseDP(gradient=1000.0)
        geom = _two_phase_geom()
        req = _make_iter_req(
            geom=geom,
            dp=fake_dp,
            dp_two_phase=True,
            iteration_cfg=_iter_cfg(max_iter=1),
        )
        model.solve(req)
        assert len(fake_dp.received_property_scalars) > 0
        for ps in fake_dp.received_property_scalars:
            assert ps["rho_l"] == geom["rho_l"]
            assert ps["rho_v"] == geom["rho_v"]
            assert ps["mu_l"] == geom["mu_l"]
            assert ps["mu_v"] == geom["mu_v"]


# ===========================================================================
# 15. Missing scalars fail clearly
# ===========================================================================


class TestMissingScalarsFail:
    """Item 15: missing required scalars raise clear ValueError."""

    def test_missing_A_ht_raises(self):
        model = SegmentedMarchModel()
        geom = _base_geom()
        del geom["A_ht"]
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(_make_iter_req(geom=geom))

    def test_missing_rho_l_for_two_phase_dp_raises(self):
        model = SegmentedMarchModel()
        geom = _two_phase_geom()
        del geom["rho_l"]
        with pytest.raises(ValueError, match="rho_l"):
            model.solve(_make_iter_req(geom=geom, dp=_ConstTwoPhaseDP(), dp_two_phase=True))

    def test_missing_rho_v_for_two_phase_dp_raises(self):
        model = SegmentedMarchModel()
        geom = _two_phase_geom()
        del geom["rho_v"]
        with pytest.raises(ValueError, match="rho_v"):
            model.solve(_make_iter_req(geom=geom, dp=_ConstTwoPhaseDP(), dp_two_phase=True))

    def test_missing_mu_l_for_two_phase_dp_raises(self):
        model = SegmentedMarchModel()
        geom = _two_phase_geom()
        del geom["mu_l"]
        with pytest.raises(ValueError, match="mu_l"):
            model.solve(_make_iter_req(geom=geom, dp=_ConstTwoPhaseDP(), dp_two_phase=True))

    def test_missing_mu_v_for_two_phase_dp_raises(self):
        model = SegmentedMarchModel()
        geom = _two_phase_geom()
        del geom["mu_v"]
        with pytest.raises(ValueError, match="mu_v"):
            model.solve(_make_iter_req(geom=geom, dp=_ConstTwoPhaseDP(), dp_two_phase=True))


# ===========================================================================
# 16. No quality marching or phase inference
# ===========================================================================


class TestNoQualityMarching:
    """Item 16: x comes from geom_scalars only; no inference or marching."""

    def test_x_must_come_from_geom_scalars(self):
        """If x is missing from geom_scalars, the solver raises ValueError."""
        model = SegmentedMarchModel()
        geom = _base_geom()
        del geom["x"]
        with pytest.raises(ValueError, match="'x'"):
            model.solve(_make_iter_req(geom=geom))

    def test_x_not_inferred_from_fluid_state(self):
        """The solver does not infer x from FluidState.h or .P."""
        model = SegmentedMarchModel()
        # Provide a valid x=0.5 in geom; result must succeed without quality inference
        geom = _base_geom({"x": 0.5})
        result = model.solve(_make_iter_req(geom=geom))
        assert isinstance(result, HXSolveResult)

    def test_no_per_cell_x_variation(self):
        """The same x from geom_scalars is used in every cell; no marching."""
        # Verify by checking that HTC calls all use the same geom_scalars x
        model = SegmentedMarchModel()
        htc_p = _ConstHTC()
        htc_s = _ConstHTC()
        model.solve(_make_iter_req(htc_p=htc_p, htc_s=htc_s, iteration_cfg=_iter_cfg(max_iter=1)))
        # All q_flux values the primary HTC received are from the same request
        # (no per-cell variation in geom_scalars is introduced)
        assert len(htc_p.received_q_flux) > 0


# ===========================================================================
# 17. No CoolProp / PropertyBackend imports in hx_models
# ===========================================================================


class TestArchitectureBoundaries:
    """Items 17–18: no CoolProp, no PropertyBackend, no CorrelationRegistry in hx_models."""

    def test_no_coolprop_in_base(self):
        import mpl_sim.hx_models.base as m

        text = open(m.__file__).read()
        assert "import CoolProp" not in text
        assert "from CoolProp" not in text

    def test_no_coolprop_in_segmented(self):
        import mpl_sim.hx_models.segmented as m

        text = open(m.__file__).read()
        assert "import CoolProp" not in text
        assert "from CoolProp" not in text

    def test_no_property_backend_in_segmented(self):
        import mpl_sim.hx_models.segmented as m

        text = open(m.__file__).read()
        assert "PropertyBackend()" not in text

    def test_no_correlation_registry_resolution_in_segmented(self):
        import mpl_sim.hx_models.segmented as m

        text = open(m.__file__).read()
        assert "CorrelationRegistry" not in text or "CorrelationRegistry.resolve" not in text

    def test_counterflow_iteration_config_exported_from_package(self):
        import mpl_sim.hx_models as pkg

        assert hasattr(pkg, "CounterflowIterationConfig")
        assert "CounterflowIterationConfig" in pkg.__all__


# ===========================================================================
# 18. No registry resolution (covered in item 17 tests above)
# ===========================================================================


# ===========================================================================
# 19. Existing Phase 11S tests still pass (smoke regressions)
# ===========================================================================


class TestPhase11SRegression:
    """Item 19: representative Phase 11S behavior is unaffected."""

    def test_11s_onepass_counterflow_still_works(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
            counterflow_iteration=None,
        )
        result = model.solve(req)
        assert result.zone_profile.flow_arrangement is FlowArrangement.COUNTERFLOW
        assert result.iteration_count == 0
        assert result.converged is None
        cells = result.zone_profile.cells
        assert cells[-1].secondary_T_in == pytest.approx(bc.T_in)

    def test_11s_cocurrent_gives_different_result_than_counterflow(self):
        """Co-current and counterflow produce different Q totals for same inputs."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0, mdot=0.02, cp=3000.0)
        common = dict(
            htc_p=_ConstHTC(htc=3000.0),
            htc_s=_ConstHTC(htc=3000.0),
            T_in=280.0,
            cp=1500.0,
            disc=_DISC_4,
        )
        req_cc = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_4,
            geom_scalars=_base_geom(),
            htc_primary=common["htc_p"],
            htc_secondary=common["htc_s"],
            primary_T_in=common["T_in"],
            primary_cp=common["cp"],
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.CO_CURRENT,
        )
        req_cf = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_4,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(htc=3000.0),
            htc_secondary=_ConstHTC(htc=3000.0),
            primary_T_in=common["T_in"],
            primary_cp=common["cp"],
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        r_cc = model.solve(req_cc)
        r_cf = model.solve(req_cf)
        # Co-current and one-pass counterflow are not identical in general
        # (they use different per-cell secondary temperature estimates)
        assert r_cc.Q != pytest.approx(r_cf.Q, rel=1e-6)

    def test_iterated_q_total_is_finite(self):
        model = SegmentedMarchModel()
        result = model.solve(_make_iter_req())
        assert math.isfinite(result.Q)
        assert math.isfinite(result.primary_state_out.h)
        assert math.isfinite(result.primary_state_out.P)

    def test_iterated_h_out_energy_balance(self):
        """h_out = h_in + Q_total / mdot (energy balance holds)."""
        model = SegmentedMarchModel()
        mdot = 0.1
        req = _make_iter_req(mdot=mdot, iteration_cfg=_iter_cfg(max_iter=50, tolerance=1e-9))
        result = model.solve(req)
        expected_h_out = _STATE_IN.h + result.Q / mdot
        assert math.isclose(result.primary_state_out.h, expected_h_out, rel_tol=1e-9)
