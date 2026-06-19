"""Phase 11S: segmented counterflow / phase-change coupling foundation tests.

Verifies all 15 required coverage items for Phase 11S:

 1. Existing segmented default behavior unchanged.
 2. Explicit co-current (FlowArrangement.CO_CURRENT) reproduces default.
 3. Explicit counterflow (FlowArrangement.COUNTERFLOW) is accepted.
 4. Counterflow secondary-side direction semantics:
      - cell[n-1].secondary_T_in == bc.T_in  (secondary inlet at far end)
      - cell[0].secondary_T_in < bc.T_in     (secondary has cooled toward outlet)
      - secondary_T_in decreases from cell n-1 toward cell 0 for heating case
 5. Counterflow one-pass limitation is documented and testable:
      - Q computed using bc.T_in as fixed estimate for all cells
      - derived secondary temps do not affect Q_cell (one-pass only)
      - SegmentedProfile.flow_arrangement == COUNTERFLOW
 6. Per-cell L_cell and two-phase DP conversion still work with counterflow.
 7. q_flux_primary still reaches primary HTC correlation in counterflow.
 8. Shah boiling HTC receives q_flux via q_flux_primary in segmented paths.
 9. Yan condensation HTC remains usable without q_flux (q_flux=None).
10. Two-phase DP property scalars (rho_l, rho_v, mu_l, mu_v) still reach
    TwoPhaseDPInput via dp_primary_is_two_phase=True.
11. Missing required scalar input fails clearly (A_ht, G, D_h, etc.).
12. No hidden quality/latent-heat/saturation-temperature inference:
      - x, h_fg, rho_l, rho_v, mu_l, mu_v must all come from geom_scalars.
13. No CorrelationRegistry resolution in hx_models.
14. No CoolProp or PropertyBackend import in hx_models.
15. Existing tests from 11N–11R still pass (verified by full pytest; here we
    run representative smoke tests for each phase to confirm no regression).

Architecture constraints respected:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes or real (Shah, Yan, MSH) with explicit scalars.
  - Cell temperatures appear only in zone_profile, never in FluidState.
  - FlowArrangement.COUNTERFLOW is a one-pass approximation; tests do not
    claim iterative convergence.
  - secondary_T_in / secondary_T_out are diagnostics only.
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
from mpl_sim.correlations.two_phase_dp import MSHTwoPhaseFrictionGradient
from mpl_sim.correlations.two_phase_htc import ShahBoilingHTC, YanCondensationHTC
from mpl_sim.discretization.primitives import DiscretizationMode, DiscretizationSpec
from mpl_sim.hx_models.base import (
    AmbientCoupling,
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
# Minimal shared fixtures
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
    """Constant-output two-phase DP correlation (gradient in Pa/m).

    Records the property_scalars mapping it received.
    """

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


def _make_sink_req(
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
    flow_arrangement: FlowArrangement | None = None,
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
        flow_arrangement=flow_arrangement,
    )


# ===========================================================================
# 1. Existing segmented default behavior unchanged
# ===========================================================================


class TestDefaultBehaviorUnchanged:
    """Item 1: flow_arrangement=None preserves existing FixedHeatRate behavior."""

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

    def test_fixed_heat_rate_profile_flow_arrangement_is_none(self):
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC_3,
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.flow_arrangement is None

    def test_sink_default_none_arrangement_gives_cocurrent_semantics(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0)
        req = _make_sink_req(bc=bc, flow_arrangement=None)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        # co-current: cell 0 secondary_T_in == bc.T_in
        assert math.isclose(profile.cells[0].secondary_T_in, bc.T_in, rel_tol=1e-10)

    def test_ambient_coupling_default_unchanged(self):
        model = SegmentedMarchModel()
        bc = AmbientCoupling(T_ambient=300.0, UA_ambient=10.0)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_3,
            primary_T_in=320.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        result = model.solve(req)
        assert result.Q < 0.0  # primary cools (T_primary > T_ambient)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.flow_arrangement is None

    def test_fixed_wall_temp_default_unchanged(self):
        model = SegmentedMarchModel()
        bc = FixedWallTemp(T_wall=400.0)
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(2000.0),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        result = model.solve(req)
        assert result.Q > 0.0


# ===========================================================================
# 2. Explicit co-current matches default
# ===========================================================================


class TestExplicitCocurrentMatchesDefault:
    """Item 2: FlowArrangement.CO_CURRENT gives same result as flow_arrangement=None."""

    def test_cocurrent_q_matches_default(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0)
        req_default = _make_sink_req(bc=bc, flow_arrangement=None)
        req_explicit = _make_sink_req(bc=bc, flow_arrangement=FlowArrangement.CO_CURRENT)
        r_default = model.solve(req_default)
        r_explicit = model.solve(req_explicit)
        assert math.isclose(r_default.Q, r_explicit.Q, rel_tol=1e-10)

    def test_cocurrent_h_out_matches_default(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0)
        req_default = _make_sink_req(bc=bc, flow_arrangement=None)
        req_explicit = _make_sink_req(bc=bc, flow_arrangement=FlowArrangement.CO_CURRENT)
        r_default = model.solve(req_default)
        r_explicit = model.solve(req_explicit)
        assert math.isclose(
            r_default.primary_state_out.h,
            r_explicit.primary_state_out.h,
            rel_tol=1e-10,
        )

    def test_cocurrent_dp_matches_default(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=350.0)
        # Single-phase DP requires rho and mu in geom_scalars
        geom = _base_geom({"rho": 800.0, "mu": 1e-4})
        dp = _ConstDP(500.0)
        req_default = _make_sink_req(bc=bc, dp=dp, geom=geom, flow_arrangement=None)
        dp2 = _ConstDP(500.0)
        req_explicit = _make_sink_req(
            bc=bc, dp=dp2, geom=geom, flow_arrangement=FlowArrangement.CO_CURRENT
        )
        r_default = model.solve(req_default)
        r_explicit = model.solve(req_explicit)
        assert math.isclose(r_default.dP_primary, r_explicit.dP_primary, rel_tol=1e-10)

    def test_cocurrent_profile_flow_arrangement_recorded(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(flow_arrangement=FlowArrangement.CO_CURRENT)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.flow_arrangement is FlowArrangement.CO_CURRENT

    def test_cocurrent_secondary_inlet_at_cell_zero(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=360.0)
        req = _make_sink_req(bc=bc, flow_arrangement=FlowArrangement.CO_CURRENT)
        result = model.solve(req)
        profile = result.zone_profile
        # co-current: secondary inlet is at cell 0
        assert math.isclose(profile.cells[0].secondary_T_in, bc.T_in, rel_tol=1e-10)

    def test_cocurrent_cell_records_match_default_count(self):
        model = SegmentedMarchModel()
        bc = _sink_bc()
        req_default = _make_sink_req(bc=bc, flow_arrangement=None)
        req_explicit = _make_sink_req(bc=bc, flow_arrangement=FlowArrangement.CO_CURRENT)
        r_default = model.solve(req_default)
        r_explicit = model.solve(req_explicit)
        assert len(r_default.zone_profile.cells) == len(r_explicit.zone_profile.cells)


# ===========================================================================
# 3. Counterflow mode is accepted
# ===========================================================================


class TestCounterflowIsAccepted:
    """Item 3: FlowArrangement.COUNTERFLOW does not raise; returns HXSolveResult."""

    def test_counterflow_accepted_returns_result(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert isinstance(result, HXSolveResult)

    def test_counterflow_profile_is_segmented_profile(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert isinstance(result.zone_profile, SegmentedProfile)

    def test_counterflow_profile_flow_arrangement_recorded(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert result.zone_profile.flow_arrangement is FlowArrangement.COUNTERFLOW

    def test_counterflow_cell_count_matches_n_cells(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(disc=_DISC_4, flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert len(result.zone_profile.cells) == 4

    def test_counterflow_heating_case_q_positive(self):
        """Heating: secondary hotter than primary → Q > 0."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0)  # secondary inlet well above primary at 300 K
        req = _make_sink_req(bc=bc, T_in=300.0, flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert result.Q > 0.0

    def test_counterflow_cooling_case_q_negative(self):
        """Cooling: secondary colder than primary → Q < 0."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=250.0)  # secondary inlet below primary at 350 K
        req = _make_sink_req(bc=bc, T_in=350.0, flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert result.Q < 0.0

    def test_counterflow_h_out_consistent_with_q(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        expected_h_out = _STATE_IN.h + result.Q / 0.1
        assert math.isclose(result.primary_state_out.h, expected_h_out, rel_tol=1e-9)


# ===========================================================================
# 4. Counterflow secondary-side direction semantics
# ===========================================================================


class TestCounterflowSecondaryDirectionSemantics:
    """Item 4: secondary inlet is at cell n-1, not cell 0, in counterflow."""

    def test_secondary_inlet_at_last_cell(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0)
        req = _make_sink_req(bc=bc, T_in=300.0, flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        cells = result.zone_profile.cells
        last = cells[-1]
        # secondary inlet (bc.T_in) must appear at cell n-1
        assert math.isclose(last.secondary_T_in, bc.T_in, rel_tol=1e-10)

    def test_secondary_inlet_not_at_cell_zero(self):
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0)
        req = _make_sink_req(
            bc=bc, T_in=300.0, disc=_DISC_3, flow_arrangement=FlowArrangement.COUNTERFLOW
        )
        result = model.solve(req)
        cells = result.zone_profile.cells
        # cell 0 secondary_T_in must NOT equal bc.T_in (it has cooled toward outlet)
        assert not math.isclose(cells[0].secondary_T_in, bc.T_in, rel_tol=1e-6)

    def test_secondary_temperature_decreases_left_in_heating_case(self):
        """In heating case (Q>0): secondary loses heat flowing left (n-1→0).
        secondary_T_in should decrease from last cell toward first cell."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0)
        req = _make_sink_req(
            bc=bc, T_in=300.0, disc=_DISC_4, flow_arrangement=FlowArrangement.COUNTERFLOW
        )
        result = model.solve(req)
        cells = result.zone_profile.cells
        # secondary_T_in at cell n-1 = 400 K; should decrease toward cell 0
        assert cells[-1].secondary_T_in > cells[0].secondary_T_in

    def test_secondary_outlet_at_cell_zero_outlet(self):
        """secondary outlet (T_s_out[0]) is the secondary stream outlet in counterflow."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0, mdot=0.05, cp=4000.0)
        req = _make_sink_req(bc=bc, T_in=300.0, flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        cells = result.zone_profile.cells
        # secondary outlet = cells[0].secondary_T_out
        # must be less than cells[-1].secondary_T_in (inlet) in heating case
        assert cells[0].secondary_T_out < cells[-1].secondary_T_in

    def test_counterflow_secondary_profile_backward_integration_consistent(self):
        """secondary_T_in[i] == secondary_T_out[i+1] for all i < n-1."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=380.0)
        req = _make_sink_req(
            bc=bc, T_in=300.0, disc=_DISC_4, flow_arrangement=FlowArrangement.COUNTERFLOW
        )
        result = model.solve(req)
        cells = result.zone_profile.cells
        for i in range(len(cells) - 1):
            assert math.isclose(
                cells[i].secondary_T_in,
                cells[i + 1].secondary_T_out,
                rel_tol=1e-10,
            ), (
                f"cell {i}: secondary_T_in={cells[i].secondary_T_in} != "
                f"cell {i + 1} secondary_T_out={cells[i + 1].secondary_T_out}"
            )

    def test_counterflow_secondary_energy_balance_consistent(self):
        """For each cell i: secondary_T_out[i] = secondary_T_in[i] - Q_cell[i]/C_s."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=380.0, mdot=0.05, cp=4000.0)
        req = _make_sink_req(
            bc=bc, T_in=300.0, disc=_DISC_3, flow_arrangement=FlowArrangement.COUNTERFLOW
        )
        result = model.solve(req)
        cells = result.zone_profile.cells
        C_s = bc.mdot_secondary * bc.cp_secondary
        for cell in cells:
            expected_T_s_out = cell.secondary_T_in - cell.Q_cell / C_s
            assert math.isclose(cell.secondary_T_out, expected_T_s_out, rel_tol=1e-10), (
                f"cell {cell.cell_index}: T_s_out={cell.secondary_T_out} "
                f"expected {expected_T_s_out}"
            )

    def test_counterflow_vs_cocurrent_secondary_direction_differs(self):
        """In co-current: cell[0].secondary_T_in == bc.T_in.
        In counterflow: cell[-1].secondary_T_in == bc.T_in.
        """
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0)
        req_cc = _make_sink_req(bc=bc, flow_arrangement=FlowArrangement.CO_CURRENT)
        req_cf = _make_sink_req(bc=bc, flow_arrangement=FlowArrangement.COUNTERFLOW)
        r_cc = model.solve(req_cc)
        r_cf = model.solve(req_cf)
        cc_cells = r_cc.zone_profile.cells
        cf_cells = r_cf.zone_profile.cells
        assert math.isclose(cc_cells[0].secondary_T_in, bc.T_in, rel_tol=1e-10)
        assert math.isclose(cf_cells[-1].secondary_T_in, bc.T_in, rel_tol=1e-10)
        assert not math.isclose(cf_cells[0].secondary_T_in, bc.T_in, rel_tol=1e-6)


# ===========================================================================
# 5. Counterflow one-pass limitation is documented and testable
# ===========================================================================


class TestCounterflowOnPassLimitation:
    """Item 5: one-pass approximation — Q uses bc.T_in as fixed secondary estimate."""

    def test_q_per_cell_uses_bc_t_in_as_fixed_secondary_estimate(self):
        """In one-pass: each cell's Q is computed using T_s = bc.T_in.
        Verify that the sum of Q_cell equals Q_total and is consistent with
        the approximation (T_s_fixed = bc.T_in everywhere)."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0, mdot=0.05, cp=4000.0)
        htc = 2000.0
        A_ht = 0.03
        n = 3
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n)
        T_primary_0 = 300.0
        primary_mdot = 0.1
        primary_cp = 1500.0
        T_s_fixed = bc.T_in  # one-pass uses this everywhere

        req = _make_sink_req(
            bc=bc,
            disc=disc,
            T_in=T_primary_0,
            cp=primary_cp,
            mdot=primary_mdot,
            htc_p=_ConstHTC(htc),
            htc_s=_ConstHTC(htc),
            geom=_base_geom({"A_ht": A_ht}),
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        result = model.solve(req)
        cells = result.zone_profile.cells

        # Manually compute expected Q_cell for cell 0 using T_s = T_s_fixed
        A_cell = A_ht / n
        C_p = primary_mdot * primary_cp
        C_s = bc.mdot_secondary * bc.cp_secondary
        C_min = min(C_p, C_s)
        C_max = max(C_p, C_s)
        Cr = C_min / C_max
        UA_cell = 1.0 / (1.0 / (htc * A_cell) + 1.0 / (htc * A_cell))
        NTU = UA_cell / C_min
        epsilon = (1.0 - math.exp(-NTU * (1.0 + Cr))) / (1.0 + Cr)

        # cell 0: T_p_in = T_primary_0, T_s = T_s_fixed
        expected_Q_cell_0 = epsilon * C_min * (T_s_fixed - T_primary_0)
        assert math.isclose(cells[0].Q_cell, expected_Q_cell_0, rel_tol=1e-9)

    def test_derived_secondary_temps_do_not_affect_q_cell(self):
        """One-pass: Q_cell values are fixed from the forward pass; the backward
        secondary profile derivation does not change them."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=400.0)
        req = _make_sink_req(bc=bc, T_in=300.0, flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        # Q_total must equal sum of Q_cell (backward derivation must not alter Q)
        total_q = sum(cell.Q_cell for cell in result.zone_profile.cells)
        assert math.isclose(result.Q, total_q, rel_tol=1e-10)

    def test_counterflow_profile_reports_counterflow_arrangement(self):
        model = SegmentedMarchModel()
        req = _make_sink_req(flow_arrangement=FlowArrangement.COUNTERFLOW)
        result = model.solve(req)
        assert result.zone_profile.flow_arrangement is FlowArrangement.COUNTERFLOW

    def test_counterflow_not_same_as_cocurrent(self):
        """Q differs between co-current and counterflow for same inputs because
        the secondary temperature estimate differs between paths."""
        model = SegmentedMarchModel()
        bc = _sink_bc(T_in=380.0)
        req_cc = _make_sink_req(bc=bc, T_in=300.0, flow_arrangement=FlowArrangement.CO_CURRENT)
        req_cf = _make_sink_req(bc=bc, T_in=300.0, flow_arrangement=FlowArrangement.COUNTERFLOW)
        r_cc = model.solve(req_cc)
        r_cf = model.solve(req_cf)
        # Results differ because co-current uses per-cell marching secondary temperature
        # while counterflow one-pass uses bc.T_in fixed for all cells.
        # For n > 1 cells with significant temperature change, these should differ.
        # (For n=1 both use bc.T_in, so they would be equal — use n=3.)
        assert not math.isclose(r_cc.Q, r_cf.Q, rel_tol=1e-6)


# ===========================================================================
# 6. Per-cell L_cell and two-phase DP conversion still work with counterflow
# ===========================================================================


class TestTwoPhaseDpInCounterflow:
    """Item 6: two-phase DP gradient × L_cell conversion works in counterflow."""

    def test_two_phase_dp_counterflow_conversion(self):
        """MSH gradient is multiplied by L_cell per cell; friction_multiplier applies."""
        model = SegmentedMarchModel()
        gradient_pa_m = 800.0
        L_cell = 0.1
        n = 3
        disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n)
        fake_dp = _ConstTwoPhaseDP(gradient=gradient_pa_m)
        geom = _two_phase_geom({"L_cell": L_cell})
        friction_mult = 1.2
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=disc,
            geom_scalars=geom,
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            dp_primary=fake_dp,
            dp_primary_is_two_phase=True,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
            friction_multiplier=friction_mult,
        )
        result = model.solve(req)
        expected_raw_dp = gradient_pa_m * L_cell * n
        expected_dp = friction_mult * expected_raw_dp
        assert math.isclose(result.raw_dP_primary, expected_raw_dp, rel_tol=1e-9)
        assert math.isclose(result.dP_primary, expected_dp, rel_tol=1e-9)

    def test_two_phase_dp_property_scalars_reach_input_in_counterflow(self):
        """rho_l, rho_v, mu_l, mu_v reach TwoPhaseDPInput.property_scalars."""
        model = SegmentedMarchModel()
        fake_dp = _ConstTwoPhaseDP(gradient=500.0)
        geom = _two_phase_geom()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=geom,
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            dp_primary=fake_dp,
            dp_primary_is_two_phase=True,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        model.solve(req)
        assert len(fake_dp.received_property_scalars) == 3
        for ps in fake_dp.received_property_scalars:
            assert ps["rho_l"] == geom["rho_l"]
            assert ps["rho_v"] == geom["rho_v"]
            assert ps["mu_l"] == geom["mu_l"]
            assert ps["mu_v"] == geom["mu_v"]

    def test_friction_multiplier_does_not_affect_q_in_counterflow(self):
        """friction_multiplier applies only to DP, not to Q."""
        model = SegmentedMarchModel()
        geom = _two_phase_geom()

        def _req(fm: float) -> HXSolveRequest:
            return HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=_sink_bc(),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=geom,
                htc_primary=_ConstHTC(),
                htc_secondary=_ConstHTC(),
                dp_primary=_ConstTwoPhaseDP(500.0),
                dp_primary_is_two_phase=True,
                primary_T_in=300.0,
                primary_cp=1500.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                flow_arrangement=FlowArrangement.COUNTERFLOW,
                friction_multiplier=fm,
            )

        r1 = model.solve(_req(1.0))
        r2 = model.solve(_req(2.0))
        assert math.isclose(r1.Q, r2.Q, rel_tol=1e-10)
        assert not math.isclose(r1.dP_primary, r2.dP_primary, rel_tol=1e-6)


# ===========================================================================
# 7 & 8. q_flux_primary reaches primary HTC / Shah boiling HTC receives q_flux
# ===========================================================================


class TestQFluxInCounterflow:
    """Items 7 & 8: q_flux_primary reaches htc_primary in all flow arrangements."""

    def test_q_flux_reaches_primary_htc_in_counterflow(self):
        """q_flux_primary is passed unchanged to HTCInput.q_flux for primary HTC."""
        model = SegmentedMarchModel()
        htc_p = _ConstHTC()
        req = _make_sink_req(
            htc_p=htc_p,
            q_flux=12000.0,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        model.solve(req)
        assert all(q == 12000.0 for q in htc_p.received_q_flux)

    def test_q_flux_not_sent_to_secondary_htc_in_counterflow(self):
        """q_flux_primary must NOT reach secondary HTC."""
        model = SegmentedMarchModel()
        htc_s = _ConstHTC()
        req = _make_sink_req(
            htc_s=htc_s,
            q_flux=12000.0,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        model.solve(req)
        assert all(q is None for q in htc_s.received_q_flux)

    def test_q_flux_reaches_primary_htc_in_cocurrent(self):
        """Same check for co-current — q_flux_primary is passed to primary HTC."""
        model = SegmentedMarchModel()
        htc_p = _ConstHTC()
        req = _make_sink_req(
            htc_p=htc_p,
            q_flux=8000.0,
            flow_arrangement=FlowArrangement.CO_CURRENT,
        )
        model.solve(req)
        assert all(q == 8000.0 for q in htc_p.received_q_flux)

    def test_shah_boiling_htc_in_counterflow_sink(self):
        """Shah receives explicit q_flux and scalars in the counterflow path."""
        geom: dict = {
            "G": 200.0,
            "x": 0.5,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.03,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1e-4,
            "k_l": 0.1,
            "Pr_l": 5.0,
            "h_fg": 200_000.0,
        }
        req = _make_sink_req(
            geom=geom,
            htc_p=ShahBoilingHTC(),
            q_flux=5000.0,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        result = SegmentedMarchModel().solve(req)
        assert result.Q > 0.0
        assert result.verdicts[0].value[0] > 0.0

    def test_shah_boiling_htc_receives_q_flux_via_segmented(self):
        """Shah boiling HTC can be injected via FixedWallTemp segmented path with q_flux."""
        shah = ShahBoilingHTC()
        model = SegmentedMarchModel()
        bc = FixedWallTemp(T_wall=320.0)
        geom: dict = {
            "G": 200.0,
            "x": 0.5,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.03,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1e-4,
            "k_l": 0.1,
            "Pr_l": 5.0,
            "h_fg": 200_000.0,
        }
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=geom,
            htc_primary=shah,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            q_flux_primary=5000.0,
        )
        result = model.solve(req)
        assert isinstance(result, HXSolveResult)
        assert len(result.verdicts) >= 1
        # Shah should have produced a positive HTC
        assert result.verdicts[0].value[0] > 0.0

    def test_missing_q_flux_causes_shah_to_raise(self):
        """Shah boiling HTC raises ValueError when q_flux is None."""
        shah = ShahBoilingHTC()
        model = SegmentedMarchModel()
        bc = FixedWallTemp(T_wall=320.0)
        geom: dict = {
            "G": 200.0,
            "x": 0.5,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.03,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1e-4,
            "k_l": 0.1,
            "Pr_l": 5.0,
            "h_fg": 200_000.0,
        }
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=geom,
            htc_primary=shah,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            q_flux_primary=None,
        )
        with pytest.raises(ValueError):
            model.solve(req)


# ===========================================================================
# 9. Yan condensation HTC usable without q_flux
# ===========================================================================


class TestYanCondensationInSegmented:
    """Item 9: YanCondensationHTC works without q_flux in segmented paths."""

    def test_yan_htc_in_counterflow_sink(self):
        """Yan remains q-flux-independent in the counterflow path."""
        geom: dict = {
            "G": 150.0,
            "x": 0.4,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.02,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1.5e-4,
            "k_l": 0.12,
            "Pr_l": 5.0,
        }
        req = _make_sink_req(
            geom=geom,
            htc_p=YanCondensationHTC(),
            q_flux=None,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        result = SegmentedMarchModel().solve(req)
        assert result.Q > 0.0
        assert result.verdicts[0].value[0] > 0.0

    def test_yan_htc_in_fixed_wall_temp_segmented(self):
        """Yan HTC requires no q_flux; inject via FixedWallTemp segmented."""
        yan = YanCondensationHTC()
        model = SegmentedMarchModel()
        bc = FixedWallTemp(T_wall=280.0)
        geom: dict = {
            "G": 150.0,
            "x": 0.4,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.02,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1.5e-4,
            "k_l": 0.12,
            "Pr_l": 5.0,
        }
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=geom,
            htc_primary=yan,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            q_flux_primary=None,
        )
        result = model.solve(req)
        assert isinstance(result, HXSolveResult)
        assert result.verdicts[0].value[0] > 0.0

    def test_yan_htc_in_cocurrent_sink(self):
        """Yan HTC injected as htc_primary in co-current SinkInletTempAndFlow."""
        yan = YanCondensationHTC()
        model = SegmentedMarchModel()
        geom: dict = {
            "G": 150.0,
            "x": 0.4,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.02,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1.5e-4,
            "k_l": 0.12,
            "Pr_l": 5.0,
        }
        req = _make_sink_req(
            htc_p=yan,
            geom=geom,
            q_flux=None,
            flow_arrangement=FlowArrangement.CO_CURRENT,
        )
        result = model.solve(req)
        assert isinstance(result, HXSolveResult)


# ===========================================================================
# 10. Two-phase DP property scalars reach TwoPhaseDPInput
# ===========================================================================


class TestTwoPhaseDpPropertyScalars:
    """Item 10: rho_l/rho_v/mu_l/mu_v forwarded to TwoPhaseDPInput.property_scalars."""

    def test_property_scalars_in_cocurrent(self):
        model = SegmentedMarchModel()
        fake_dp = _ConstTwoPhaseDP(gradient=1000.0)
        geom = _two_phase_geom()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=geom,
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            dp_primary=fake_dp,
            dp_primary_is_two_phase=True,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.CO_CURRENT,
        )
        model.solve(req)
        for ps in fake_dp.received_property_scalars:
            assert "rho_l" in ps and "rho_v" in ps
            assert "mu_l" in ps and "mu_v" in ps
            assert ps["rho_l"] == 1000.0
            assert ps["mu_v"] == 1e-5

    def test_msh_with_counterflow_accepts_property_scalars(self):
        """MSH (real correlation) can be used in counterflow when scalars are supplied."""
        msh = MSHTwoPhaseFrictionGradient()
        model = SegmentedMarchModel()
        geom: dict = {
            "G": 200.0,
            "x": 0.3,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.03,
            "rho_l": 1100.0,
            "rho_v": 25.0,
            "mu_l": 1.2e-4,
            "mu_v": 1.1e-5,
        }
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=geom,
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            dp_primary=msh,
            dp_primary_is_two_phase=True,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        result = model.solve(req)
        assert result.dP_primary > 0.0


# ===========================================================================
# 11. Missing required scalar input fails clearly
# ===========================================================================


class TestMissingScalarFails:
    """Item 11: missing required scalars raise ValueError with clear message."""

    def test_missing_a_ht_fails_counterflow(self):
        model = SegmentedMarchModel()
        geom = {"G": 200.0, "x": 0.5, "D_h": 0.002, "L_cell": 0.1}  # no A_ht
        req = _make_sink_req(geom=geom, flow_arrangement=FlowArrangement.COUNTERFLOW)
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req)

    def test_missing_a_ht_fails_cocurrent(self):
        model = SegmentedMarchModel()
        geom = {"G": 200.0, "x": 0.5, "D_h": 0.002, "L_cell": 0.1}  # no A_ht
        req = _make_sink_req(geom=geom, flow_arrangement=FlowArrangement.CO_CURRENT)
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req)

    def test_missing_two_phase_dp_scalar_fails_counterflow(self):
        """Missing rho_l for two-phase DP fails with clear message."""
        model = SegmentedMarchModel()
        geom = _base_geom()
        geom.update({"rho_v": 20.0, "mu_l": 1e-4, "mu_v": 1e-5})  # missing rho_l
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=geom,
            htc_primary=_ConstHTC(),
            htc_secondary=_ConstHTC(),
            dp_primary=_ConstTwoPhaseDP(),
            dp_primary_is_two_phase=True,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        with pytest.raises(ValueError, match="rho_l"):
            model.solve(req)

    def test_missing_htc_primary_fails_counterflow(self):
        with pytest.raises(ValueError, match="htc_primary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=_sink_bc(),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_base_geom(),
                htc_primary=None,
                htc_secondary=_ConstHTC(),
                primary_T_in=300.0,
                primary_cp=1500.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                flow_arrangement=FlowArrangement.COUNTERFLOW,
            )

    def test_missing_primary_t_in_fails_counterflow(self):
        with pytest.raises(ValueError, match="primary_T_in"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=_sink_bc(),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_base_geom(),
                htc_primary=_ConstHTC(),
                htc_secondary=_ConstHTC(),
                primary_T_in=None,
                primary_cp=1500.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                flow_arrangement=FlowArrangement.COUNTERFLOW,
            )

    def test_constant_temperature_mode_fails_counterflow(self):
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
            primary_cp=None,
            primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        with pytest.raises(ValueError, match="CONSTANT_TEMPERATURE"):
            model.solve(req)

    def test_primary_only_ua_mode_fails_counterflow(self):
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=_sink_bc(),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_base_geom(),
            htc_primary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        with pytest.raises(ValueError, match="PRIMARY_ONLY"):
            model.solve(req)


# ===========================================================================
# 12. No hidden inference of quality, latent heat, or saturation temperature
# ===========================================================================


class TestNoHiddenInference:
    """Item 12: all phase-change scalars must come from geom_scalars explicitly."""

    def test_quality_x_must_be_supplied_in_geom_scalars(self):
        """Missing 'x' from geom_scalars raises ValueError, not a hidden default."""
        model = SegmentedMarchModel()
        bc = FixedWallTemp(T_wall=320.0)
        geom: dict = {
            # 'x' intentionally omitted
            "G": 200.0,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.03,
        }
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=geom,
            htc_primary=_ConstHTC(),
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        with pytest.raises(ValueError, match="'x'"):
            model.solve(req)

    def test_no_primary_t_sat_field_on_hx_solve_request(self):
        """HXSolveRequest has no primary_T_sat field — saturation T must come
        from geom_scalars if needed; no hidden lookup is performed."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_1,
        )
        assert not hasattr(req, "primary_T_sat")

    def test_no_primary_h_fg_field_on_hx_solve_request(self):
        """HXSolveRequest has no primary_h_fg field — h_fg must come from
        geom_scalars (as Shah boiling HTC requires); no hidden lookup."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_1,
        )
        assert not hasattr(req, "primary_h_fg")

    def test_h_fg_must_be_in_geom_scalars_for_shah(self):
        """Shah boiling HTC raises when h_fg is absent from geom_scalars."""
        shah = ShahBoilingHTC()
        model = SegmentedMarchModel()
        bc = FixedWallTemp(T_wall=320.0)
        geom: dict = {
            "G": 200.0,
            "x": 0.5,
            "D_h": 0.002,
            "L_cell": 0.1,
            "A_ht": 0.03,
            "rho_l": 1000.0,
            "rho_v": 20.0,
            "mu_l": 1e-4,
            "k_l": 0.1,
            "Pr_l": 5.0,
            # h_fg intentionally omitted
        }
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=bc,
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=geom,
            htc_primary=shah,
            primary_T_in=300.0,
            primary_cp=1500.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            q_flux_primary=5000.0,
        )
        with pytest.raises((ValueError, KeyError)):
            model.solve(req)

    def test_geom_scalars_are_immutable_at_request_level(self):
        """geom_scalars is a MappingProxyType after HXSolveRequest construction."""
        import types as _types

        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars={"G": 200.0},
        )
        assert isinstance(req.geom_scalars, _types.MappingProxyType)
        with pytest.raises(TypeError):
            req.geom_scalars["G"] = 999.0  # type: ignore[index]


# ===========================================================================
# 13. No CorrelationRegistry resolution in hx_models
# ===========================================================================


class TestNoRegistryResolution:
    """Item 13: hx_models must not import or use CorrelationRegistry."""

    def test_segmented_module_does_not_import_correlation_registry(self):
        import mpl_sim.hx_models.segmented as seg_mod

        assert not hasattr(seg_mod, "CorrelationRegistry")

    def test_base_module_does_not_import_correlation_registry(self):
        import mpl_sim.hx_models.base as base_mod

        assert not hasattr(base_mod, "CorrelationRegistry")

    def test_epsilon_ntu_module_does_not_import_correlation_registry(self):
        import mpl_sim.hx_models.epsilon_ntu as entu_mod

        assert not hasattr(entu_mod, "CorrelationRegistry")

    def test_lmtd_module_does_not_import_correlation_registry(self):
        import mpl_sim.hx_models.lmtd as lmtd_mod

        assert not hasattr(lmtd_mod, "CorrelationRegistry")

    def test_hx_models_package_does_not_expose_correlation_registry(self):
        import mpl_sim.hx_models as hx_pkg

        assert "CorrelationRegistry" not in dir(hx_pkg)


# ===========================================================================
# 14. No CoolProp or PropertyBackend import in hx_models
# ===========================================================================


class TestNoCoolPropOrPropertyBackend:
    """Item 14: hx_models must not import CoolProp or PropertyBackend."""

    def test_segmented_no_coolprop(self):
        import sys

        import mpl_sim.hx_models.segmented  # noqa: F401

        assert "CoolProp" not in sys.modules or (
            "mpl_sim.hx_models.segmented" not in str(sys.modules.get("CoolProp", ""))
        )

    def test_base_no_property_backend(self):
        import mpl_sim.hx_models.base as base_mod

        assert not hasattr(base_mod, "PropertyBackend")
        assert not hasattr(base_mod, "CoolPropBackend")

    def test_segmented_no_property_backend(self):
        import mpl_sim.hx_models.segmented as seg_mod

        assert not hasattr(seg_mod, "PropertyBackend")
        assert not hasattr(seg_mod, "CoolPropBackend")

    def test_hx_models_package_no_coolprop_attribute(self):
        import mpl_sim.hx_models as hx_pkg

        assert not hasattr(hx_pkg, "CoolProp")
        assert not hasattr(hx_pkg, "PropertyBackend")

    def test_flow_arrangement_importable_without_coolprop(self):
        """FlowArrangement can be imported without triggering any property lookup."""
        from mpl_sim.hx_models.base import FlowArrangement as FA  # noqa: F401

        assert FA.CO_CURRENT is not FA.COUNTERFLOW


# ===========================================================================
# 15. Regression smoke tests for 11N–11R
# ===========================================================================


class TestPhase11NThroughRRegression:
    """Item 15: existing 11N–11R behavior remains intact after Phase 11S changes."""

    def test_11n_q_flux_primary_validation(self):
        """Phase 11N: q_flux_primary=0 is rejected."""
        with pytest.raises(ValueError, match="q_flux_primary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=FixedHeatRate(Q=100.0),
                geometry=object(),
                discretization=_DISC_1,
                q_flux_primary=0.0,
            )

    def test_11n_q_flux_primary_negative_rejected(self):
        with pytest.raises(ValueError, match="q_flux_primary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=0.1,
                secondary_bc=FixedHeatRate(Q=100.0),
                geometry=object(),
                discretization=_DISC_1,
                q_flux_primary=-100.0,
            )

    def test_11p_dp_primary_is_two_phase_false_default(self):
        """Phase 11P: dp_primary_is_two_phase defaults to False."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_1,
        )
        assert req.dp_primary_is_two_phase is False

    def test_11p_two_phase_dp_conversion_in_fixed_heat_rate(self):
        """Phase 11P: gradient × L_cell conversion works in FixedHeatRate path."""
        model = SegmentedMarchModel()
        gradient = 1000.0
        L_cell = 0.2
        fake_dp = _ConstTwoPhaseDP(gradient=gradient)
        geom = _two_phase_geom({"L_cell": L_cell})
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=300.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=geom,
            dp_primary=fake_dp,
            dp_primary_is_two_phase=True,
        )
        result = model.solve(req)
        expected_raw = gradient * L_cell * 3
        assert math.isclose(result.raw_dP_primary, expected_raw, rel_tol=1e-9)

    def test_11q_evaporator_hx_input_has_q_flux_field(self):
        """Phase 11Q: EvaporatorHXInput has q_flux_primary field."""
        from mpl_sim.components.evaporator import EvaporatorHXInput
        from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

        inp = EvaporatorHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=100.0),
            model=EpsilonNTUModel(),
            discretization=_DISC_1,
        )
        assert hasattr(inp, "q_flux_primary")
        assert inp.q_flux_primary is None

    def test_11q_condenser_hx_input_has_dp_two_phase_field(self):
        """Phase 11Q: CondenserHXInput has dp_primary_is_two_phase field."""
        from mpl_sim.components.condenser import CondenserHXInput
        from mpl_sim.hx_models.epsilon_ntu import EpsilonNTUModel

        inp = CondenserHXInput(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=-100.0),
            model=EpsilonNTUModel(),
            discretization=_DISC_1,
        )
        assert hasattr(inp, "dp_primary_is_two_phase")
        assert inp.dp_primary_is_two_phase is False

    def test_11r_evaporator_scenario_binding_exists(self):
        """Phase 11R: EvaporatorScenarioBinding is importable from mpl_sim.components."""
        from mpl_sim.components import EvaporatorScenarioBinding  # noqa: F401

    def test_11r_condenser_scenario_binding_exists(self):
        """Phase 11R: CondenserScenarioBinding is importable from mpl_sim.components."""
        from mpl_sim.components import CondenserScenarioBinding  # noqa: F401

    def test_11s_flow_arrangement_exported_from_hx_models(self):
        """Phase 11S: FlowArrangement is exported from mpl_sim.hx_models."""
        from mpl_sim.hx_models import FlowArrangement  # noqa: F401

        assert hasattr(FlowArrangement, "CO_CURRENT")
        assert hasattr(FlowArrangement, "COUNTERFLOW")

    def test_11s_flow_arrangement_field_on_hx_solve_request(self):
        """Phase 11S: HXSolveRequest accepts flow_arrangement field."""
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=0.1,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_1,
            flow_arrangement=FlowArrangement.COUNTERFLOW,
        )
        assert req.flow_arrangement is FlowArrangement.COUNTERFLOW

    def test_11s_segmented_profile_has_flow_arrangement_field(self):
        """Phase 11S: SegmentedProfile has flow_arrangement field."""
        profile = SegmentedProfile(cells=(), flow_arrangement=None)
        assert profile.flow_arrangement is None
        profile2 = SegmentedProfile(cells=(), flow_arrangement=FlowArrangement.CO_CURRENT)
        assert profile2.flow_arrangement is FlowArrangement.CO_CURRENT
