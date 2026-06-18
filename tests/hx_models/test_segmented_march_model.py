"""Tests for SegmentedMarchModel — Phase 11F.

Verifies:
  Model identity and registry:
    - SegmentedMarchModel.kind() returns HeatExchangerModelKind.SEGMENTED_MARCH
    - SegmentedMarchModel is exported from mpl_sim.hx_models
    - HeatExchangerModelRegistry can register/resolve SegmentedMarchModel
    - SEGMENTED_MARCH is not a CorrelationRole

  FixedHeatRate segmented energy:
    - Positive Q increases outlet enthalpy
    - Negative Q decreases outlet enthalpy
    - Zero Q leaves enthalpy unchanged
    - h_out = h_in + Q_total / primary_mdot
    - Cell profile contains n_cells cells
    - Sum of cell Q_cell equals Q_total
    - Last cell h_out equals result primary_state_out.h
    - Fluid identity and pressure behavior are preserved

  Cell count / discretization validation:
    - LUMPED mode raises ValueError
    - MOVING_BOUNDARY mode raises ValueError
    - UNIFORM mode with n_cells=1 works (explicit single-cell segmentation)
    - UNIFORM mode with n_cells=3 works

  DP path (cell-wise):
    - dp_primary is called once per cell
    - Raw DP is summed across cells
    - Calibrated DP equals friction_multiplier * raw_total_dp
    - Pressure is marched cell-by-cell
    - Verdicts are propagated for every DP call (one per cell)
    - Negative DP remains allowed (pressure recovery)
    - Non-finite DP output raises ValueError
    - DP does not affect enthalpy balance

  Unsupported BCs / supported in later phases:
    - SinkInletTempAndFlow is now supported (Phase 11J); PRIMARY_ONLY raises ValueError
    - FixedWallTemp and AmbientCoupling are covered by their focused test modules

  Architecture:
    - segmented.py does not import CoolProp
    - segmented.py does not import PropertyBackend
    - segmented.py does not import network/ or solvers/
    - segmented.py does not resolve CorrelationRegistry
    - SEGMENTED_MARCH is absent from CorrelationRole

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
    FixedHeatRate,
    HeatExchangerModelKind,
    HXSolveRequest,
    SinkInletTempAndFlow,
    UnsupportedHeatExchangerBoundaryConditionError,
)
from mpl_sim.hx_models.registry import create_empty_hx_model_registry
from mpl_sim.hx_models.segmented import (
    SegmentedCellRecord,
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

_FAKE_DP_VALUE = 300.0  # Pa per cell


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


class _FakeDPCorrelation(Correlation):
    """Returns a configurable DP value; records the states it was called with."""

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


class _NanDPCorrelation(Correlation):
    """Returns NaN; used to test non-finite DP rejection."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_dp_output(math.nan)


class _NegativeDPCorrelation(Correlation):
    """Returns negative DP (pressure recovery); must not be rejected."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_dp_output(-100.0)


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_H_IN = 250_000.0  # J/kg
_P_IN = 1_000_000.0  # Pa
_STATE_IN = FluidState(P=_P_IN, h=_H_IN, identity=_IDENTITY)
_MDOT = 0.05  # kg/s

_DISC_UNIFORM_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)
_DISC_UNIFORM_1 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=1)
_DISC_LUMPED = DiscretizationSpec(mode=DiscretizationMode.LUMPED)
_DISC_MOVING = DiscretizationSpec(mode=DiscretizationMode.MOVING_BOUNDARY)

# Minimal geom_scalars for FixedHeatRate (no DP).
_GEOM_ENERGY = {"G": 100.0, "D_h": 0.002, "x": 0.5}

# Full geom_scalars for DP path.
_GEOM_DP = {
    "G": 100.0,
    "D_h": 0.002,
    "rho": 1200.0,
    "mu": 2e-4,
    "L_cell": 0.1,
}


def _make_fhr_req(
    Q: float = 500.0,
    n_cells: int = 3,
    dp_primary: Correlation | None = None,
    friction_multiplier: float = 1.0,
    mdot: float = _MDOT,
    geom_scalars: dict | None = None,
) -> HXSolveRequest:
    disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells)
    gs = geom_scalars if geom_scalars is not None else {}
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=FixedHeatRate(Q=Q),
        geometry=object(),
        discretization=disc,
        geom_scalars=gs,
        dp_primary=dp_primary,
        friction_multiplier=friction_multiplier,
    )


# ---------------------------------------------------------------------------
# Model identity and registry
# ---------------------------------------------------------------------------


class TestSegmentedMarchModelIdentity:
    def test_kind_returns_segmented_march(self) -> None:
        assert SegmentedMarchModel().kind() is HeatExchangerModelKind.SEGMENTED_MARCH

    def test_kind_is_not_epsilon_ntu(self) -> None:
        assert SegmentedMarchModel().kind() is not HeatExchangerModelKind.EPSILON_NTU

    def test_kind_is_not_lmtd(self) -> None:
        assert SegmentedMarchModel().kind() is not HeatExchangerModelKind.LMTD

    def test_exported_from_hx_models(self) -> None:
        import mpl_sim.hx_models as pkg

        assert hasattr(pkg, "SegmentedMarchModel")
        assert pkg.SegmentedMarchModel is SegmentedMarchModel

    def test_cell_record_exported_from_hx_models(self) -> None:
        import mpl_sim.hx_models as pkg

        assert hasattr(pkg, "SegmentedCellRecord")
        assert pkg.SegmentedCellRecord is SegmentedCellRecord

    def test_profile_exported_from_hx_models(self) -> None:
        import mpl_sim.hx_models as pkg

        assert hasattr(pkg, "SegmentedProfile")
        assert pkg.SegmentedProfile is SegmentedProfile

    def test_registry_can_register_segmented(self) -> None:
        reg = create_empty_hx_model_registry()
        model = SegmentedMarchModel()
        reg.register("segmented", model)
        assert reg.is_registered("segmented")

    def test_registry_can_resolve_segmented(self) -> None:
        reg = create_empty_hx_model_registry()
        model = SegmentedMarchModel()
        reg.register("segmented", model)
        assert reg.resolve("segmented") is model

    def test_segmented_march_not_in_correlation_role(self) -> None:
        role_names = {r.name for r in CorrelationRole}
        assert "SEGMENTED_MARCH" not in role_names

    def test_segmented_march_not_in_correlation_role_values(self) -> None:
        # Belt-and-suspenders: confirm SEGMENTED_MARCH does not appear
        # as a value in CorrelationRole regardless of name casing.
        for role in CorrelationRole:
            assert "SEGMENTED" not in role.name.upper() or role.name.upper() == "SEGMENTED"
        # More direct: check no CorrelationRole member contains "MARCH"
        for role in CorrelationRole:
            assert "MARCH" not in role.name.upper()


# ---------------------------------------------------------------------------
# FixedHeatRate segmented energy
# ---------------------------------------------------------------------------


class TestFixedHeatRateEnergy:
    def test_positive_q_increases_enthalpy(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=1000.0)
        result = model.solve(req)
        assert result.primary_state_out.h > _H_IN

    def test_negative_q_decreases_enthalpy(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=-1000.0)
        result = model.solve(req)
        assert result.primary_state_out.h < _H_IN

    def test_zero_q_leaves_enthalpy_unchanged(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=0.0)
        result = model.solve(req)
        assert result.primary_state_out.h == pytest.approx(_H_IN, rel=1e-9)

    def test_h_out_equals_h_in_plus_q_over_mdot(self) -> None:
        Q = 750.0
        mdot = 0.03
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=Q, mdot=mdot)
        result = model.solve(req)
        expected_h_out = _H_IN + Q / mdot
        assert result.primary_state_out.h == pytest.approx(expected_h_out, rel=1e-9)

    def test_result_q_equals_prescribed_q(self) -> None:
        Q = 1234.5
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=Q)
        result = model.solve(req)
        assert result.Q == pytest.approx(Q, rel=1e-9)

    def test_cell_profile_has_correct_count(self) -> None:
        n = 5
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=n)
        result = model.solve(req)
        assert isinstance(result.zone_profile, SegmentedProfile)
        assert len(result.zone_profile.cells) == n

    def test_sum_of_cell_q_equals_total_q(self) -> None:
        Q = 900.0
        n = 4
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=Q, n_cells=n)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        total_q = sum(c.Q_cell for c in profile.cells)
        assert total_q == pytest.approx(Q, rel=1e-9)

    def test_last_cell_h_out_equals_result_h_out(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=600.0, n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        last_cell = profile.cells[-1]
        assert last_cell.h_out == pytest.approx(result.primary_state_out.h, rel=1e-9)

    def test_cell_h_march_is_contiguous(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=600.0, n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].h_in == pytest.approx(profile.cells[i - 1].h_out, rel=1e-12)

    def test_fluid_identity_preserved(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0)
        result = model.solve(req)
        assert result.primary_state_out.identity is _IDENTITY

    def test_pressure_unchanged_when_no_dp(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0)
        result = model.solve(req)
        assert result.primary_state_out.P == pytest.approx(_P_IN, rel=1e-9)
        assert result.dP_primary == pytest.approx(0.0, abs=1e-12)

    def test_cell_indices_are_sequential(self) -> None:
        n = 4
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=n)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i, rec in enumerate(profile.cells):
            assert rec.cell_index == i

    def test_single_cell_uniform_is_allowed(self) -> None:
        """UNIFORM with n_cells=1 is explicit and must be accepted."""
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=1)
        result = model.solve(req)
        assert isinstance(result.zone_profile, SegmentedProfile)
        assert len(result.zone_profile.cells) == 1

    def test_single_cell_result_matches_prescribed_q(self) -> None:
        Q = 400.0
        mdot = 0.04
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=Q, n_cells=1, mdot=mdot)
        result = model.solve(req)
        assert result.primary_state_out.h == pytest.approx(_H_IN + Q / mdot, rel=1e-9)

    def test_htc_multiplier_does_not_affect_energy(self) -> None:
        """htc_multiplier has no effect on FixedHeatRate energy balance."""
        Q = 500.0
        model = SegmentedMarchModel()
        req_1x = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedHeatRate(Q=Q),
            geometry=object(),
            discretization=_DISC_UNIFORM_3,
            htc_multiplier=1.0,
        )
        req_2x = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedHeatRate(Q=Q),
            geometry=object(),
            discretization=_DISC_UNIFORM_3,
            htc_multiplier=2.0,
        )
        r1 = model.solve(req_1x)
        r2 = model.solve(req_2x)
        assert r1.primary_state_out.h == pytest.approx(r2.primary_state_out.h, rel=1e-12)


# ---------------------------------------------------------------------------
# Cell count / discretization validation
# ---------------------------------------------------------------------------


class TestDiscretizationValidation:
    def test_lumped_mode_raises_value_error(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_LUMPED,
        )
        with pytest.raises(ValueError, match="UNIFORM"):
            model.solve(req)

    def test_moving_boundary_mode_raises_value_error(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_MOVING,
        )
        with pytest.raises(ValueError, match="UNIFORM"):
            model.solve(req)

    def test_lumped_error_names_segmented_march_model(self) -> None:
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=FixedHeatRate(Q=100.0),
            geometry=object(),
            discretization=_DISC_LUMPED,
        )
        with pytest.raises(ValueError, match="SegmentedMarchModel"):
            model.solve(req)

    def test_uniform_n_cells_1_works(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=200.0, n_cells=1)
        result = model.solve(req)
        assert len(result.zone_profile.cells) == 1

    def test_uniform_n_cells_2_works(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=200.0, n_cells=2)
        result = model.solve(req)
        assert len(result.zone_profile.cells) == 2

    def test_uniform_n_cells_10_works(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=200.0, n_cells=10)
        result = model.solve(req)
        assert len(result.zone_profile.cells) == 10


# ---------------------------------------------------------------------------
# DP path (cell-wise)
# ---------------------------------------------------------------------------


class TestDPPath:
    def test_dp_correlation_called_once_per_cell(self) -> None:
        n = 4
        fake_dp = _FakeDPCorrelation()
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        model.solve(req)
        assert fake_dp.call_count == n

    def test_raw_dp_is_summed_over_cells(self) -> None:
        n = 3
        per_cell_dp = 200.0
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        expected_raw_total = n * per_cell_dp
        assert result.raw_dP_primary == pytest.approx(expected_raw_total, rel=1e-9)

    def test_calibrated_dp_equals_multiplier_times_raw_total(self) -> None:
        n = 3
        per_cell_dp = 200.0
        multiplier = 1.5
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        req = _make_fhr_req(
            Q=500.0,
            n_cells=n,
            dp_primary=fake_dp,
            friction_multiplier=multiplier,
            geom_scalars=_GEOM_DP,
        )
        result = model.solve(req)
        expected_calibrated = multiplier * n * per_cell_dp
        assert result.dP_primary == pytest.approx(expected_calibrated, rel=1e-9)

    def test_pressure_marched_per_cell(self) -> None:
        n = 3
        per_cell_dp = 300.0
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=0.0, n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        expected_p_out = _P_IN - n * per_cell_dp
        assert result.primary_state_out.P == pytest.approx(expected_p_out, rel=1e-9)

    def test_cell_p_march_is_contiguous(self) -> None:
        n = 4
        per_cell_dp = 150.0
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=0.0, n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].P_in == pytest.approx(profile.cells[i - 1].P_out, rel=1e-12)

    def test_last_cell_p_out_equals_result_p_out(self) -> None:
        n = 3
        fake_dp = _FakeDPCorrelation(dp=200.0)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=0.0, n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        last_cell = profile.cells[-1]
        assert last_cell.P_out == pytest.approx(result.primary_state_out.P, rel=1e-9)

    def test_verdicts_one_per_cell(self) -> None:
        n = 5
        fake_dp = _FakeDPCorrelation(dp=100.0)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=n, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        assert len(result.verdicts) == n

    def test_negative_dp_allowed_pressure_recovery(self) -> None:
        """Negative DP (pressure recovery) must not be rejected."""
        n = 2
        model = SegmentedMarchModel()
        req = _make_fhr_req(
            Q=500.0, n_cells=n, dp_primary=_NegativeDPCorrelation(), geom_scalars=_GEOM_DP
        )
        result = model.solve(req)
        assert result.primary_state_out.P > _P_IN

    def test_nan_dp_raises_value_error(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(
            Q=500.0, n_cells=2, dp_primary=_NanDPCorrelation(), geom_scalars=_GEOM_DP
        )
        with pytest.raises(ValueError, match="finite"):
            model.solve(req)

    def test_dp_does_not_affect_enthalpy(self) -> None:
        Q = 600.0
        mdot = 0.04
        fake_dp = _FakeDPCorrelation(dp=500.0)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=Q, n_cells=3, dp_primary=fake_dp, mdot=mdot, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        expected_h = _H_IN + Q / mdot
        assert result.primary_state_out.h == pytest.approx(expected_h, rel=1e-9)

    def test_friction_multiplier_does_not_affect_enthalpy(self) -> None:
        Q = 600.0
        mdot = 0.04
        fake_dp = _FakeDPCorrelation(dp=200.0)
        model = SegmentedMarchModel()
        req = _make_fhr_req(
            Q=Q,
            n_cells=3,
            dp_primary=fake_dp,
            mdot=mdot,
            friction_multiplier=2.0,
            geom_scalars=_GEOM_DP,
        )
        result = model.solve(req)
        expected_h = _H_IN + Q / mdot
        assert result.primary_state_out.h == pytest.approx(expected_h, rel=1e-9)

    def test_dp_state_passed_to_correlation_is_cell_inlet(self) -> None:
        """Each cell's DP call receives the cell's inlet state (h and P march)."""
        n = 3
        per_cell_dp = 100.0
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        Q = 300.0
        mdot = 0.05
        req = _make_fhr_req(Q=Q, n_cells=n, dp_primary=fake_dp, mdot=mdot, geom_scalars=_GEOM_DP)
        model.solve(req)
        # First cell must receive the original inlet state
        assert fake_dp.called_states[0].P == pytest.approx(_P_IN, rel=1e-9)
        assert fake_dp.called_states[0].h == pytest.approx(_H_IN, rel=1e-9)
        # Second cell must receive updated state
        expected_h_cell1 = _H_IN + (Q / n) / mdot
        expected_p_cell1 = _P_IN - per_cell_dp
        assert fake_dp.called_states[1].h == pytest.approx(expected_h_cell1, rel=1e-9)
        assert fake_dp.called_states[1].P == pytest.approx(expected_p_cell1, rel=1e-9)

    def test_cell_raw_dp_recorded_in_profile(self) -> None:
        per_cell_dp = 200.0
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=3, dp_primary=fake_dp, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.raw_dP_cell == pytest.approx(per_cell_dp, rel=1e-9)

    def test_cell_calibrated_dp_recorded_in_profile(self) -> None:
        per_cell_dp = 200.0
        multiplier = 1.8
        fake_dp = _FakeDPCorrelation(dp=per_cell_dp)
        model = SegmentedMarchModel()
        req = _make_fhr_req(
            Q=500.0,
            n_cells=3,
            dp_primary=fake_dp,
            friction_multiplier=multiplier,
            geom_scalars=_GEOM_DP,
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.dP_cell == pytest.approx(multiplier * per_cell_dp, rel=1e-9)

    def test_no_dp_path_raw_dp_zero(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=3)
        result = model.solve(req)
        assert result.raw_dP_primary == pytest.approx(0.0, abs=1e-12)

    def test_no_dp_path_verdicts_empty(self) -> None:
        model = SegmentedMarchModel()
        req = _make_fhr_req(Q=500.0, n_cells=3)
        result = model.solve(req)
        assert result.verdicts == ()


# ---------------------------------------------------------------------------
# SinkInletTempAndFlow — supported in Phase 11J; PRIMARY_ONLY rejected
# ---------------------------------------------------------------------------


class TestSinkInletBCBehavior:
    def test_sink_inlet_primary_only_raises_value_error(self) -> None:
        """PRIMARY_ONLY is not supported for segmented sink; TWO_SIDED is required."""
        from mpl_sim.hx_models.base import PrimaryThermalMode, UAComputationMode

        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=SinkInletTempAndFlow(T_in=310.0, mdot_secondary=0.1, cp_secondary=4200.0),
            geometry=object(),
            discretization=_DISC_UNIFORM_3,
            primary_T_in=300.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            primary_cp=4200.0,
            htc_primary=_FakeDPCorrelation(),
        )
        with pytest.raises(ValueError, match="PRIMARY_ONLY"):
            model.solve(req)

    def test_sink_inlet_not_rejected_as_unsupported(self) -> None:
        """SinkInletTempAndFlow must not raise UnsupportedHeatExchangerBoundaryConditionError."""
        from mpl_sim.hx_models.base import PrimaryThermalMode, UAComputationMode

        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=SinkInletTempAndFlow(T_in=310.0, mdot_secondary=0.1, cp_secondary=4200.0),
            geometry=object(),
            discretization=_DISC_UNIFORM_3,
            primary_T_in=300.0,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.PRIMARY_ONLY,
            primary_cp=4200.0,
            htc_primary=_FakeDPCorrelation(),
        )
        try:
            model.solve(req)
        except UnsupportedHeatExchangerBoundaryConditionError:
            pytest.fail(
                "SegmentedMarchModel raised UnsupportedHeatExchangerBoundaryConditionError "
                "for SinkInletTempAndFlow; this BC is supported in Phase 11J"
            )
        except ValueError:
            pass  # expected — PRIMARY_ONLY not supported


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

    def test_segmented_does_not_import_network(self) -> None:
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
                # Reject any import of CorrelationRegistry from any module
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
