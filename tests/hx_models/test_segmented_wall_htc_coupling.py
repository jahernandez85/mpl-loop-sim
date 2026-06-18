"""Tests for SegmentedMarchModel FixedWallTemp path — Phase 11H.

Verifies:
  FixedWallTemp segmented energy:
    - Heating case (T_wall > T_in) gives total Q > 0
    - Cooling case (T_wall < T_in) gives total Q < 0
    - Zero-difference case gives Q = 0
    - Final h_out equals last cell h_out
    - Final Q equals sum of cell Q_cell
    - Cell temperatures march using explicit primary_cp
    - T_out stored only in profile diagnostics, not in FluidState

  Required inputs:
    - Missing primary_T_in fails
    - Missing primary_cp fails
    - Non-finite or non-positive primary_cp fails at HXSolveRequest construction
    - primary_thermal_mode != FINITE_CAPACITY fails clearly
    - Missing A_ht fails
    - Invalid A_ht fails
    - Missing htc_primary fails
    - Invalid HTC outputs fail

  HTC behavior:
    - HTC correlation called once per cell
    - Each HTC call receives the current cell inlet FluidState
    - htc_multiplier scales UA_cell, cell Q, and total Q
    - HTC verdicts propagated for every cell
    - Invalid HTC input scalars fail clearly

  DP behavior:
    - Existing FixedHeatRate DP tests still pass (covered in test_segmented_march_model.py)
    - FixedWallTemp with DP calls dp_primary once per cell
    - DP verdicts propagated along with HTC verdicts
    - friction_multiplier affects pressure/DP only, not Q
    - Negative DP remains allowed as pressure recovery

  Profile:
    - Profile contains n_cells records
    - Each record is immutable (frozen dataclass)
    - Each record includes T_in, T_out, htc_primary, UA_cell
    - Last record P_out, h_out, T_out are consistent with result

  Architecture:
    - No CoolProp
    - No PropertyBackend
    - No Network/Solver
    - No CorrelationRegistry resolution
    - No segmented march in CorrelationRole

Architectural constraints respected:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes.
  - Cell temperatures appear only in zone_profile, never in FluidState.
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
    PrimaryThermalMode,
)
from mpl_sim.hx_models.segmented import (
    SegmentedMarchModel,
    SegmentedProfile,
)

# ---------------------------------------------------------------------------
# Fake correlations
# ---------------------------------------------------------------------------

_MINIMAL_ENVELOPE = ValidityEnvelope(
    fluid_families=(AnyFluid(),),
    bounds=(Bound(quantity=BoundedQuantity.REYNOLDS, min=None, max=None, units=""),),
    source=SourceRef(citation="test"),
)

_FAKE_HTC_VALUE = 1000.0  # W/(m²·K)
_FAKE_DP_VALUE = 200.0  # Pa per cell


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


def _make_dp_output(value: float) -> CorrelationOutput:
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


class _FakeHTCCorrelation(Correlation):
    """Returns a configurable HTC value; records the states it was called with."""

    def __init__(self, htc: float = _FAKE_HTC_VALUE) -> None:
        self._htc = htc
        self.call_count = 0
        self.called_states: list[FluidState] = []

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        self.call_count += 1
        self.called_states.append(inp.state[0])
        return _make_htc_output(self._htc)


class _NanHTCCorrelation(Correlation):
    """Returns NaN HTC; used to test non-finite HTC rejection."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_htc_output(math.nan)


class _ZeroHTCCorrelation(Correlation):
    """Returns zero HTC; must be rejected (HTC must be > 0)."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_htc_output(0.0)


class _NegativeHTCCorrelation(Correlation):
    """Returns negative HTC; must be rejected."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_htc_output(-500.0)


class _FakeDPCorrelation(Correlation):
    """Returns a configurable DP value; records call states."""

    def __init__(self, dp: float = _FAKE_DP_VALUE) -> None:
        self._dp = dp
        self.call_count = 0
        self.called_states: list[FluidState] = []

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        self.call_count += 1
        self.called_states.append(inp.state[0])
        return _make_dp_output(self._dp)


class _NegativeDPCorrelation(Correlation):
    """Returns negative DP (pressure recovery)."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_dp_output(-100.0)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_H_IN = 250_000.0  # J/kg
_P_IN = 1_000_000.0  # Pa
_STATE_IN = FluidState(P=_P_IN, h=_H_IN, identity=_IDENTITY)
_MDOT = 0.05  # kg/s
_CP = 4200.0  # J/kg/K — explicit, no hidden water default

_T_IN = 300.0  # K
_T_WALL_HOT = 350.0  # K — heating case
_T_WALL_COLD = 250.0  # K — cooling case

_DISC_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)
_DISC_1 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=1)

# Geom scalars for FixedWallTemp: HTC needs G, D_h, x; A_ht for area.
_GEOM_FWT = {"G": 100.0, "D_h": 0.002, "x": 0.5, "A_ht": 0.1}

# Geom scalars with DP scalars included.
_GEOM_FWT_DP = {
    "G": 100.0,
    "D_h": 0.002,
    "x": 0.5,
    "A_ht": 0.1,
    "rho": 1200.0,
    "mu": 2e-4,
    "L_cell": 0.1,
}


def _make_fwt_req(
    T_wall: float = _T_WALL_HOT,
    T_in: float = _T_IN,
    cp: float = _CP,
    n_cells: int = 3,
    htc_primary: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    mdot: float = _MDOT,
    geom_scalars: dict | None = None,
    primary_thermal_mode: PrimaryThermalMode | None = PrimaryThermalMode.FINITE_CAPACITY,
) -> HXSolveRequest:
    disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells)
    gs = geom_scalars if geom_scalars is not None else _GEOM_FWT
    htc = htc_primary if htc_primary is not None else _FakeHTCCorrelation()
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=FixedWallTemp(T_wall=T_wall),
        geometry=object(),
        discretization=disc,
        geom_scalars=gs,
        htc_primary=htc,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=T_in,
        primary_cp=cp,
        primary_thermal_mode=primary_thermal_mode,
    )


# ---------------------------------------------------------------------------
# FixedWallTemp segmented energy
# ---------------------------------------------------------------------------


class TestFixedWallTempEnergy:
    def test_heating_case_gives_positive_q(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT, T_in=_T_IN)
        result = model.solve(req)
        assert result.Q > 0.0

    def test_cooling_case_gives_negative_q(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_COLD, T_in=_T_IN)
        result = model.solve(req)
        assert result.Q < 0.0

    def test_zero_difference_gives_zero_q(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_IN, T_in=_T_IN)
        result = model.solve(req)
        assert result.Q == pytest.approx(0.0, abs=1e-10)

    def test_final_h_out_equals_last_cell_h_out(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[-1].h_out == pytest.approx(result.primary_state_out.h, rel=1e-12)

    def test_total_q_equals_sum_of_cell_q(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT, n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        cell_sum = sum(c.Q_cell for c in profile.cells)
        assert result.Q == pytest.approx(cell_sum, rel=1e-12)

    def test_cell_temperatures_march_using_primary_cp(self) -> None:
        """T_out = T_in + Q_cell / (mdot * cp) for each cell."""
        htc = _FakeHTCCorrelation(htc=_FAKE_HTC_VALUE)
        model = SegmentedMarchModel()
        cp = 2000.0
        mdot = 0.05
        req = _make_fwt_req(
            T_wall=_T_WALL_HOT,
            T_in=_T_IN,
            cp=cp,
            n_cells=3,
            htc_primary=htc,
            mdot=mdot,
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.T_in is not None
            assert rec.T_out is not None
            expected_t_out = rec.T_in + rec.Q_cell / (mdot * cp)
            assert rec.T_out == pytest.approx(expected_t_out, rel=1e-12)

    def test_t_out_not_stored_in_fluid_state(self) -> None:
        """FluidState must remain (P, h, identity) only — no temperature attribute."""
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT)
        result = model.solve(req)
        assert not hasattr(result.primary_state_out, "T")
        assert not hasattr(result.primary_state_out, "T_out")
        assert not hasattr(result.primary_state_out, "temperature")

    def test_h_out_consistent_with_q_and_mdot(self) -> None:
        """h_out = h_in + Q_total / primary_mdot."""
        model = SegmentedMarchModel()
        mdot = 0.04
        req = _make_fwt_req(T_wall=_T_WALL_HOT, n_cells=3, mdot=mdot)
        result = model.solve(req)
        expected_h_out = _H_IN + result.Q / mdot
        assert result.primary_state_out.h == pytest.approx(expected_h_out, rel=1e-12)

    def test_single_cell_energy_formula_exact(self) -> None:
        """With n_cells=1, verify the per-cell formula exactly."""
        htc_val = 500.0
        A_ht = 0.2
        T_wall = 320.0
        T_in = 295.0
        mdot = 0.03
        gs = {"G": 80.0, "D_h": 0.003, "x": 0.3, "A_ht": A_ht}
        htc = _FakeHTCCorrelation(htc=htc_val)
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot,
            secondary_bc=FixedWallTemp(T_wall=T_wall),
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars=gs,
            htc_primary=htc,
            primary_T_in=T_in,
            primary_cp=_CP,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        result = model.solve(req)
        # n_cells=1: A_cell = A_ht, UA_cell = htc_val * A_ht
        expected_Q = htc_val * A_ht * (T_wall - T_in)
        assert result.Q == pytest.approx(expected_Q, rel=1e-9)
        expected_h_out = _H_IN + expected_Q / mdot
        assert result.primary_state_out.h == pytest.approx(expected_h_out, rel=1e-9)

    def test_cell_h_march_contiguous(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT, n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].h_in == pytest.approx(profile.cells[i - 1].h_out, rel=1e-12)

    def test_cell_temperature_march_contiguous(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT, n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].T_in == pytest.approx(profile.cells[i - 1].T_out, rel=1e-12)


# ---------------------------------------------------------------------------
# Required inputs
# ---------------------------------------------------------------------------


class TestRequiredInputs:
    def test_missing_primary_t_in_fails(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_GEOM_FWT,
            htc_primary=_FakeHTCCorrelation(),
            primary_cp=_CP,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            # primary_T_in omitted
        )
        with pytest.raises(ValueError, match="primary_T_in"):
            model.solve(req)

    def test_missing_primary_cp_fails(self) -> None:
        # HXSolveRequest enforces primary_cp required for FINITE_CAPACITY at construction.
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=FixedWallTemp(T_wall=350.0),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_GEOM_FWT,
                htc_primary=_FakeHTCCorrelation(),
                primary_T_in=_T_IN,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                # primary_cp omitted
            )

    def test_non_finite_primary_cp_fails_at_construction(self) -> None:
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=FixedWallTemp(T_wall=350.0),
                geometry=object(),
                discretization=_DISC_3,
                primary_T_in=_T_IN,
                primary_cp=math.nan,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            )

    def test_non_positive_primary_cp_fails_at_construction(self) -> None:
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=FixedWallTemp(T_wall=350.0),
                geometry=object(),
                discretization=_DISC_3,
                primary_T_in=_T_IN,
                primary_cp=-100.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            )

    def test_primary_thermal_mode_none_fails(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_GEOM_FWT,
            htc_primary=_FakeHTCCorrelation(),
            primary_T_in=_T_IN,
            primary_cp=_CP,
            # primary_thermal_mode omitted (None)
        )
        with pytest.raises(ValueError, match="primary_thermal_mode"):
            model.solve(req)

    def test_constant_temperature_mode_fails_with_deferred_message(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_GEOM_FWT,
            htc_primary=_FakeHTCCorrelation(),
            primary_T_in=_T_IN,
            # CONSTANT_TEMPERATURE forbids primary_cp (HXSolveRequest enforces this)
            primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
        )
        with pytest.raises(ValueError, match="[Dd]eferred"):
            model.solve(req)

    def test_missing_a_ht_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_no_area = {"G": 100.0, "D_h": 0.002, "x": 0.5}  # no A_ht
        req = _make_fwt_req(geom_scalars=gs_no_area)
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req)

    def test_zero_a_ht_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_zero_area = {"G": 100.0, "D_h": 0.002, "x": 0.5, "A_ht": 0.0}
        req = _make_fwt_req(geom_scalars=gs_zero_area)
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req)

    def test_negative_a_ht_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_neg_area = {"G": 100.0, "D_h": 0.002, "x": 0.5, "A_ht": -0.1}
        req = _make_fwt_req(geom_scalars=gs_neg_area)
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req)

    def test_missing_htc_primary_fails(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedWallTemp(T_wall=350.0),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_GEOM_FWT,
            # htc_primary omitted
            primary_T_in=_T_IN,
            primary_cp=_CP,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        with pytest.raises(ValueError, match="htc_primary"):
            model.solve(req)

    def test_nan_htc_output_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(htc_primary=_NanHTCCorrelation())
        with pytest.raises(ValueError, match="finite"):
            model.solve(req)

    def test_zero_htc_output_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(htc_primary=_ZeroHTCCorrelation())
        with pytest.raises(ValueError, match="> 0"):
            model.solve(req)

    def test_negative_htc_output_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(htc_primary=_NegativeHTCCorrelation())
        with pytest.raises(ValueError, match="> 0"):
            model.solve(req)


# ---------------------------------------------------------------------------
# HTC behavior
# ---------------------------------------------------------------------------


class TestHTCBehavior:
    def test_htc_called_once_per_cell(self) -> None:
        n = 4
        htc = _FakeHTCCorrelation()
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=n, htc_primary=htc)
        model.solve(req)
        assert htc.call_count == n

    def test_each_htc_call_receives_cell_inlet_state(self) -> None:
        """Cell 0 receives the original inlet; cell 1 receives marched state."""
        htc_val = 1000.0
        A_ht = 0.1
        n = 3
        htc = _FakeHTCCorrelation(htc=htc_val)
        model = SegmentedMarchModel()
        mdot = _MDOT
        cp = _CP
        T_wall = _T_WALL_HOT
        T_in = _T_IN
        req = _make_fwt_req(
            T_wall=T_wall,
            T_in=T_in,
            cp=cp,
            n_cells=n,
            htc_primary=htc,
            mdot=mdot,
        )
        model.solve(req)
        # Cell 0 must receive original inlet
        assert htc.called_states[0].P == pytest.approx(_P_IN, rel=1e-9)
        assert htc.called_states[0].h == pytest.approx(_H_IN, rel=1e-9)
        # Cell 1 must receive updated state (h marched from cell 0)
        A_cell = A_ht / n
        UA_cell = htc_val * A_cell
        Q_cell_0 = UA_cell * (T_wall - T_in)
        expected_h_cell1 = _H_IN + Q_cell_0 / mdot
        assert htc.called_states[1].h == pytest.approx(expected_h_cell1, rel=1e-9)

    def test_htc_multiplier_scales_ua_cell_and_q(self) -> None:
        """With n_cells=1, htc_multiplier=2 doubles Q compared to multiplier=1."""
        model = SegmentedMarchModel()
        req_1x = _make_fwt_req(T_wall=_T_WALL_HOT, T_in=_T_IN, n_cells=1, htc_multiplier=1.0)
        req_2x = _make_fwt_req(T_wall=_T_WALL_HOT, T_in=_T_IN, n_cells=1, htc_multiplier=2.0)
        r1 = model.solve(req_1x)
        r2 = model.solve(req_2x)
        assert r2.Q == pytest.approx(2.0 * r1.Q, rel=1e-9)

    def test_htc_multiplier_zero_gives_zero_q(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(htc_multiplier=0.0)
        result = model.solve(req)
        assert result.Q == pytest.approx(0.0, abs=1e-10)

    def test_htc_verdicts_propagated_for_every_cell(self) -> None:
        n = 5
        htc = _FakeHTCCorrelation()
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=n, htc_primary=htc)
        result = model.solve(req)
        # No DP: exactly n HTC verdicts
        assert len(result.verdicts) == n

    def test_invalid_g_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_bad = {"G": -1.0, "D_h": 0.002, "x": 0.5, "A_ht": 0.1}
        req = _make_fwt_req(geom_scalars=gs_bad)
        with pytest.raises(ValueError, match="G"):
            model.solve(req)

    def test_invalid_d_h_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_bad = {"G": 100.0, "D_h": 0.0, "x": 0.5, "A_ht": 0.1}
        req = _make_fwt_req(geom_scalars=gs_bad)
        with pytest.raises(ValueError, match="D_h"):
            model.solve(req)

    def test_x_out_of_range_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_bad = {"G": 100.0, "D_h": 0.002, "x": 1.5, "A_ht": 0.1}
        req = _make_fwt_req(geom_scalars=gs_bad)
        with pytest.raises(ValueError, match="x"):
            model.solve(req)

    def test_missing_g_fails(self) -> None:
        model = SegmentedMarchModel()
        gs_bad = {"D_h": 0.002, "x": 0.5, "A_ht": 0.1}
        req = _make_fwt_req(geom_scalars=gs_bad)
        with pytest.raises(ValueError, match="G"):
            model.solve(req)


# ---------------------------------------------------------------------------
# DP behavior
# ---------------------------------------------------------------------------


class TestDPBehavior:
    def test_fwt_dp_called_once_per_cell(self) -> None:
        n = 4
        fake_dp = _FakeDPCorrelation()
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_FWT_DP)
        model.solve(req)
        assert fake_dp.call_count == n

    def test_fwt_dp_verdicts_combined_with_htc_verdicts(self) -> None:
        """With both HTC and DP, verdicts count = 2 * n_cells (HTC then DP per cell)."""
        n = 3
        htc = _FakeHTCCorrelation()
        fake_dp = _FakeDPCorrelation()
        model = SegmentedMarchModel()
        req = _make_fwt_req(
            n_cells=n,
            htc_primary=htc,
            dp_primary=fake_dp,
            geom_scalars=_GEOM_FWT_DP,
        )
        result = model.solve(req)
        assert len(result.verdicts) == 2 * n

    def test_fwt_friction_multiplier_does_not_affect_q(self) -> None:
        """friction_multiplier must not change Q or enthalpy."""
        model = SegmentedMarchModel()
        req_1x = _make_fwt_req(
            dp_primary=_FakeDPCorrelation(dp=300.0),
            friction_multiplier=1.0,
            geom_scalars=_GEOM_FWT_DP,
        )
        req_3x = _make_fwt_req(
            dp_primary=_FakeDPCorrelation(dp=300.0),
            friction_multiplier=3.0,
            geom_scalars=_GEOM_FWT_DP,
        )
        r1 = model.solve(req_1x)
        r3 = model.solve(req_3x)
        assert r1.Q == pytest.approx(r3.Q, rel=1e-12)
        assert r1.primary_state_out.h == pytest.approx(r3.primary_state_out.h, rel=1e-12)

    def test_fwt_friction_multiplier_affects_pressure(self) -> None:
        model = SegmentedMarchModel()
        per_cell_dp = 100.0
        n = 3
        req_1x = _make_fwt_req(
            n_cells=n,
            dp_primary=_FakeDPCorrelation(dp=per_cell_dp),
            friction_multiplier=1.0,
            geom_scalars=_GEOM_FWT_DP,
        )
        req_2x = _make_fwt_req(
            n_cells=n,
            dp_primary=_FakeDPCorrelation(dp=per_cell_dp),
            friction_multiplier=2.0,
            geom_scalars=_GEOM_FWT_DP,
        )
        r1 = model.solve(req_1x)
        r2 = model.solve(req_2x)
        assert r1.primary_state_out.P > r2.primary_state_out.P

    def test_fwt_negative_dp_allowed_pressure_recovery(self) -> None:
        n = 2
        model = SegmentedMarchModel()
        req = _make_fwt_req(
            n_cells=n,
            dp_primary=_NegativeDPCorrelation(),
            geom_scalars=_GEOM_FWT_DP,
        )
        result = model.solve(req)
        assert result.primary_state_out.P > _P_IN

    def test_fwt_no_dp_gives_zero_raw_dp(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req()
        result = model.solve(req)
        assert result.raw_dP_primary == pytest.approx(0.0, abs=1e-12)
        assert result.dP_primary == pytest.approx(0.0, abs=1e-12)

    def test_fwt_dp_receives_cell_inlet_state(self) -> None:
        """DP calls receive the same cell inlet states as HTC calls."""
        n = 3
        htc = _FakeHTCCorrelation()
        dp = _FakeDPCorrelation()
        model = SegmentedMarchModel()
        req = _make_fwt_req(
            n_cells=n,
            htc_primary=htc,
            dp_primary=dp,
            geom_scalars=_GEOM_FWT_DP,
        )
        model.solve(req)
        # HTC and DP for same cell see the same state
        for i in range(n):
            assert htc.called_states[i].P == pytest.approx(dp.called_states[i].P, rel=1e-12)
            assert htc.called_states[i].h == pytest.approx(dp.called_states[i].h, rel=1e-12)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestProfile:
    def test_profile_contains_n_cells_records(self) -> None:
        n = 5
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=n)
        result = model.solve(req)
        assert isinstance(result.zone_profile, SegmentedProfile)
        assert len(result.zone_profile.cells) == n

    def test_each_record_is_immutable(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=2)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            with pytest.raises((AttributeError, TypeError)):
                rec.Q_cell = 0.0  # type: ignore[misc]

    def test_each_record_has_t_in_diagnostic(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.T_in is not None
            assert math.isfinite(rec.T_in)

    def test_each_record_has_t_out_diagnostic(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.T_out is not None
            assert math.isfinite(rec.T_out)

    def test_each_record_has_htc_primary_diagnostic(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.htc_primary is not None
            assert rec.htc_primary == pytest.approx(_FAKE_HTC_VALUE, rel=1e-9)

    def test_each_record_has_ua_cell_diagnostic(self) -> None:
        htc_val = 800.0
        A_ht = 0.12
        n = 3
        gs = {"G": 100.0, "D_h": 0.002, "x": 0.5, "A_ht": A_ht}
        htc = _FakeHTCCorrelation(htc=htc_val)
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedWallTemp(T_wall=_T_WALL_HOT),
            geometry=object(),
            discretization=DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n),
            geom_scalars=gs,
            htc_primary=htc,
            primary_T_in=_T_IN,
            primary_cp=_CP,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        expected_ua_cell = htc_val * (A_ht / n)
        for rec in profile.cells:
            assert rec.UA_cell is not None
            assert rec.UA_cell == pytest.approx(expected_ua_cell, rel=1e-9)

    def test_last_record_p_out_consistent_with_result(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=3, dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_FWT_DP)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[-1].P_out == pytest.approx(result.primary_state_out.P, rel=1e-12)

    def test_last_record_h_out_consistent_with_result(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[-1].h_out == pytest.approx(result.primary_state_out.h, rel=1e-12)

    def test_last_record_t_out_consistent_with_temperature_march(self) -> None:
        """Last cell T_out should equal the primary outlet temperature."""
        cp = 3000.0
        mdot = 0.04
        model = SegmentedMarchModel()
        req = _make_fwt_req(T_wall=_T_WALL_HOT, T_in=_T_IN, cp=cp, n_cells=3, mdot=mdot)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        last = profile.cells[-1]
        assert last.T_out is not None
        # Independently verify: sum Q_cells / (mdot * cp) + T_in
        total_q = sum(c.Q_cell for c in profile.cells)
        expected_t_out = _T_IN + total_q / (mdot * cp)
        assert last.T_out == pytest.approx(expected_t_out, rel=1e-9)

    def test_cell_indices_sequential(self) -> None:
        n = 5
        model = SegmentedMarchModel()
        req = _make_fwt_req(n_cells=n)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i, rec in enumerate(profile.cells):
            assert rec.cell_index == i

    def test_fhr_profile_t_in_is_none(self) -> None:
        """FixedHeatRate path must leave T_in as None in cell records."""
        from mpl_sim.hx_models.base import FixedHeatRate

        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedHeatRate(Q=500.0),
            geometry=object(),
            discretization=_DISC_3,
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.T_in is None
            assert rec.T_out is None
            assert rec.htc_primary is None
            assert rec.UA_cell is None


# ---------------------------------------------------------------------------
# Architecture boundary checks
# ---------------------------------------------------------------------------


class TestArchitectureBoundaries:
    def test_segmented_does_not_import_coolprop(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(__file__).parents[2] / "src" / "mpl_sim" / "hx_models" / "segmented.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else ([node.module] if node.module else [])
                )
                for name in names:
                    assert "CoolProp" not in (
                        name or ""
                    ), f"segmented.py must not import CoolProp; found: {name!r}"

    def test_segmented_does_not_import_property_backend(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(__file__).parents[2] / "src" / "mpl_sim" / "hx_models" / "segmented.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else ([node.module] if node.module else [])
                )
                for name in names:
                    assert "PropertyBackend" not in (
                        name or ""
                    ), f"segmented.py must not import PropertyBackend; found: {name!r}"
                    assert "properties" not in (name or "").split(
                        "."
                    ), f"segmented.py must not import from properties/; found: {name!r}"

    def test_segmented_does_not_import_network_or_solvers(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(__file__).parents[2] / "src" / "mpl_sim" / "hx_models" / "segmented.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = node.module if isinstance(node, ast.ImportFrom) else None
                if module:
                    assert (
                        "network" not in module
                    ), f"segmented.py must not import from network/; found: {module!r}"
                    assert (
                        "solvers" not in module
                    ), f"segmented.py must not import from solvers/; found: {module!r}"

    def test_segmented_does_not_import_correlation_registry(self) -> None:
        import ast
        import pathlib

        src = pathlib.Path(__file__).parents[2] / "src" / "mpl_sim" / "hx_models" / "segmented.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name != "CorrelationRegistry", (
                        f"segmented.py must not import CorrelationRegistry; "
                        f"found import from {node.module!r}"
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "CorrelationRegistry" not in alias.name, (
                        f"segmented.py must not import CorrelationRegistry; "
                        f"found: {alias.name!r}"
                    )

    def test_segmented_march_not_in_correlation_role(self) -> None:
        role_names = {r.name for r in CorrelationRole}
        assert "SEGMENTED_MARCH" not in role_names

    def test_no_march_in_correlation_role_names(self) -> None:
        for role in CorrelationRole:
            assert "MARCH" not in role.name.upper()
