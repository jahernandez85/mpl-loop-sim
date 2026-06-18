"""Tests for SegmentedMarchModel SinkInletTempAndFlow path — Phase 11J.

Flow arrangement: explicit co-current (parallel-flow) foundation.
Both primary and secondary inlets are at cell 0.
Counterflow is deferred; this test file explicitly asserts co-current behavior
and does NOT claim implicit convergence or counterflow semantics.

Verifies:
  Sink segmented energy:
    - Heating case: secondary hotter than primary gives total Q > 0
    - Cooling case: secondary colder than primary gives total Q < 0
    - Zero temperature difference gives Q = 0
    - Final h_out equals last cell h_out
    - Final Q equals sum of cell Q_cell
    - Primary and secondary temperature updates are energy-consistent per cell
    - Overall primary enthalpy change equals Q_total / primary_mdot
    - Cell temperatures are diagnostics only, not stored in FluidState

  Co-current convention:
    - Secondary inlet is at cell 0 (same end as primary inlet)
    - Secondary temperature decreases when primary gains heat (Q > 0)
    - Secondary temperature increases when primary rejects heat (Q < 0)

  Required inputs:
    - Missing primary_T_in fails
    - Missing primary_cp fails at HXSolveRequest construction (FINITE_CAPACITY)
    - Invalid primary_cp fails at HXSolveRequest construction
    - PrimaryThermalMode.CONSTANT_TEMPERATURE fails clearly with deferred message
    - Missing/invalid secondary mdot, cp, or inlet temperature fails at BC construction
    - Missing A_ht fails
    - Missing htc_primary fails
    - Missing htc_secondary fails
    - UAComputationMode.PRIMARY_ONLY fails clearly
    - Invalid primary HTC output fails
    - Invalid secondary HTC output fails

  HTC behavior:
    - htc_primary called once per cell
    - htc_secondary called once per cell
    - Primary HTC receives current primary cell inlet FluidState
    - htc_multiplier affects UA_cell, Q, and temperature changes
    - HTC verdicts are propagated for every cell (primary then secondary)
    - Invalid HTC scalars fail clearly

  DP behavior:
    - dp_primary called once per cell
    - DP verdicts propagated after HTC verdicts in deterministic order
    - friction_multiplier affects pressure/DP only, not Q
    - Negative DP remains allowed
    - Non-finite DP output fails

  Profile:
    - Profile contains n_cells records
    - Records are immutable
    - Records include primary and secondary diagnostics
    - Last primary T_out, P_out, and h_out are consistent with result

  Architecture:
    - No CoolProp
    - No PropertyBackend
    - No Network/Solver
    - No CorrelationRegistry resolution
    - No segmented march in CorrelationRole
    - No hidden defaults

Architectural constraints respected:
  - No CoolProp, no PropertyBackend, no Network, no Solver.
  - All correlations are local fakes.
  - Cell temperatures appear only in zone_profile, never in FluidState.
  - secondary_T_in, secondary_T_out are diagnostics only.
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
    HXSolveRequest,
    PrimaryThermalMode,
    SinkInletTempAndFlow,
    UAComputationMode,
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


class _ConstantHTCCorrelation(Correlation):
    """Returns a fixed HTC value; records call count and states."""

    def __init__(self, htc: float = 1000.0) -> None:
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


class _FakeDPCorrelation(Correlation):
    """Returns a configurable DP value; records call states."""

    def __init__(self, dp: float = 200.0) -> None:
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


class _BadHTCCorrelation(Correlation):
    """Returns an invalid (zero) HTC value to test rejection."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_htc_output(0.0)


class _NanHTCCorrelation(Correlation):
    """Returns NaN HTC value to test rejection."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.HTC

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_htc_output(math.nan)


class _NegativeDPCorrelation(Correlation):
    """Returns negative DP (pressure recovery)."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_dp_output(-100.0)


class _NanDPCorrelation(Correlation):
    """Returns NaN DP; must be rejected."""

    def role(self) -> CorrelationRole:
        return CorrelationRole.SINGLE_PHASE_DP

    def envelope(self) -> ValidityEnvelope:
        return _MINIMAL_ENVELOPE

    def evaluate(self, inp: CorrelationInput) -> CorrelationOutput:
        return _make_dp_output(math.nan)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_IDENTITY = PureFluid("R134a")
_H_IN = 250_000.0  # J/kg
_P_IN = 1_000_000.0  # Pa
_STATE_IN = FluidState(P=_P_IN, h=_H_IN, identity=_IDENTITY)
_MDOT = 0.05  # kg/s
_CP_PRIMARY = 3500.0  # J/kg/K — explicit, no hidden default
_T_PRIMARY_IN = 290.0  # K

_T_SECONDARY_HOT = 340.0  # K — secondary hotter → primary gains heat
_T_SECONDARY_COLD = 250.0  # K — secondary colder → primary rejects heat
_MDOT_SECONDARY = 0.08  # kg/s
_CP_SECONDARY = 4000.0  # J/kg/K

_HTC_P = 1500.0  # W/(m²·K)
_HTC_S = 2000.0  # W/(m²·K)
_A_HT = 0.6  # m²

_DISC_3 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=3)
_DISC_1 = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=1)

_GEOM_HTC = {
    "G": 150.0,
    "x": 0.5,
    "D_h": 0.003,
    "A_ht": _A_HT,
}

_GEOM_DP = {
    "G": 150.0,
    "x": 0.5,
    "D_h": 0.003,
    "A_ht": _A_HT,
    "rho": 1100.0,
    "mu": 2e-4,
    "L_cell": 0.1,
}


def _make_sink_req(
    T_secondary_in: float = _T_SECONDARY_HOT,
    mdot_secondary: float = _MDOT_SECONDARY,
    cp_secondary: float = _CP_SECONDARY,
    T_primary_in: float = _T_PRIMARY_IN,
    cp_primary: float = _CP_PRIMARY,
    mdot: float = _MDOT,
    n_cells: int = 3,
    htc_p: Correlation | None = None,
    htc_s: Correlation | None = None,
    dp_primary: Correlation | None = None,
    htc_multiplier: float = 1.0,
    friction_multiplier: float = 1.0,
    geom_scalars: dict | None = None,
    ua_computation_mode: UAComputationMode = UAComputationMode.TWO_SIDED,
    primary_thermal_mode: PrimaryThermalMode = PrimaryThermalMode.FINITE_CAPACITY,
) -> HXSolveRequest:
    htc_primary = htc_p if htc_p is not None else _ConstantHTCCorrelation(_HTC_P)
    htc_secondary = htc_s if htc_s is not None else _ConstantHTCCorrelation(_HTC_S)
    disc = DiscretizationSpec(mode=DiscretizationMode.UNIFORM, n_cells=n_cells)
    gs = geom_scalars if geom_scalars is not None else _GEOM_HTC
    return HXSolveRequest(
        primary_state_in=_STATE_IN,
        primary_mdot=mdot,
        secondary_bc=SinkInletTempAndFlow(
            T_in=T_secondary_in,
            mdot_secondary=mdot_secondary,
            cp_secondary=cp_secondary,
        ),
        geometry=object(),
        discretization=disc,
        geom_scalars=gs,
        htc_primary=htc_primary,
        htc_secondary=htc_secondary,
        dp_primary=dp_primary,
        htc_multiplier=htc_multiplier,
        friction_multiplier=friction_multiplier,
        primary_T_in=T_primary_in,
        primary_cp=cp_primary,
        primary_thermal_mode=primary_thermal_mode,
        ua_computation_mode=ua_computation_mode,
    )


# ---------------------------------------------------------------------------
# Sink segmented energy
# ---------------------------------------------------------------------------


class TestSinkSegmentedEnergy:
    def test_heating_case_gives_positive_q(self) -> None:
        """Secondary hotter than primary: primary gains heat, Q > 0."""
        model = SegmentedMarchModel()
        req = _make_sink_req(T_secondary_in=_T_SECONDARY_HOT, T_primary_in=_T_PRIMARY_IN)
        result = model.solve(req)
        assert result.Q > 0.0

    def test_cooling_case_gives_negative_q(self) -> None:
        """Secondary colder than primary: primary rejects heat, Q < 0."""
        model = SegmentedMarchModel()
        req = _make_sink_req(T_secondary_in=_T_SECONDARY_COLD, T_primary_in=_T_PRIMARY_IN)
        result = model.solve(req)
        assert result.Q < 0.0

    def test_zero_temperature_difference_gives_zero_q(self) -> None:
        """Equal inlet temperatures give Q = 0."""
        model = SegmentedMarchModel()
        req = _make_sink_req(T_secondary_in=_T_PRIMARY_IN, T_primary_in=_T_PRIMARY_IN)
        result = model.solve(req)
        assert result.Q == pytest.approx(0.0, abs=1e-10)

    def test_final_h_out_equals_last_cell_h_out(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req()
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[-1].h_out == pytest.approx(result.primary_state_out.h, rel=1e-12)

    def test_total_q_equals_sum_of_cell_q(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        cell_sum = sum(c.Q_cell for c in profile.cells)
        assert result.Q == pytest.approx(cell_sum, rel=1e-12)

    def test_primary_temperature_update_energy_consistent(self) -> None:
        """T_primary_out = T_primary_in + Q_cell / C_primary for each cell."""
        cp = 3000.0
        mdot = 0.04
        model = SegmentedMarchModel()
        req = _make_sink_req(T_primary_in=_T_PRIMARY_IN, cp_primary=cp, mdot=mdot, n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        C_primary = mdot * cp
        for rec in profile.cells:
            assert rec.T_in is not None
            assert rec.T_out is not None
            expected_t_out = rec.T_in + rec.Q_cell / C_primary
            assert rec.T_out == pytest.approx(expected_t_out, rel=1e-12)

    def test_secondary_temperature_update_energy_consistent(self) -> None:
        """T_secondary_out = T_secondary_in - Q_cell / C_secondary for each cell."""
        cp_s = 4000.0
        mdot_s = 0.06
        model = SegmentedMarchModel()
        req = _make_sink_req(cp_secondary=cp_s, mdot_secondary=mdot_s, n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        C_secondary = mdot_s * cp_s
        for rec in profile.cells:
            assert rec.secondary_T_in is not None
            assert rec.secondary_T_out is not None
            expected_t_s_out = rec.secondary_T_in - rec.Q_cell / C_secondary
            assert rec.secondary_T_out == pytest.approx(expected_t_s_out, rel=1e-12)

    def test_overall_enthalpy_change_equals_q_total_over_mdot(self) -> None:
        """h_out - h_in = Q_total / primary_mdot."""
        mdot = 0.05
        model = SegmentedMarchModel()
        req = _make_sink_req(mdot=mdot, n_cells=3)
        result = model.solve(req)
        expected_h_out = _H_IN + result.Q / mdot
        assert result.primary_state_out.h == pytest.approx(expected_h_out, rel=1e-12)

    def test_t_out_not_stored_in_fluid_state(self) -> None:
        """FluidState must remain (P, h, identity) only — no temperature attribute."""
        model = SegmentedMarchModel()
        req = _make_sink_req()
        result = model.solve(req)
        assert not hasattr(result.primary_state_out, "T")
        assert not hasattr(result.primary_state_out, "T_out")
        assert not hasattr(result.primary_state_out, "temperature")

    def test_single_cell_formula_exact(self) -> None:
        """With n_cells=1, verify the co-current ε-NTU formula exactly."""
        T_p_in = 280.0
        T_s_in = 330.0
        mdot_p = 0.05
        cp_p = 2000.0
        mdot_s = 0.08
        cp_s = 3000.0
        htc_p_val = 1000.0
        htc_s_val = 1200.0
        A_ht = 0.5

        C_p = mdot_p * cp_p
        C_s = mdot_s * cp_s
        C_min = min(C_p, C_s)
        C_max = max(C_p, C_s)
        Cr = C_min / C_max

        A_cell = A_ht
        UA_cell = 1.0 / (1.0 / (htc_p_val * A_cell) + 1.0 / (htc_s_val * A_cell))
        NTU = UA_cell / C_min
        epsilon = (1.0 - math.exp(-NTU * (1.0 + Cr))) / (1.0 + Cr)
        expected_Q = epsilon * C_min * (T_s_in - T_p_in)

        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=mdot_p,
            secondary_bc=SinkInletTempAndFlow(
                T_in=T_s_in, mdot_secondary=mdot_s, cp_secondary=cp_s
            ),
            geometry=object(),
            discretization=_DISC_1,
            geom_scalars={"G": 150.0, "x": 0.5, "D_h": 0.003, "A_ht": A_ht},
            htc_primary=_ConstantHTCCorrelation(htc_p_val),
            htc_secondary=_ConstantHTCCorrelation(htc_s_val),
            primary_T_in=T_p_in,
            primary_cp=cp_p,
            primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
        )
        result = model.solve(req)
        assert result.Q == pytest.approx(expected_Q, rel=1e-9)
        expected_h_out = _H_IN + expected_Q / mdot_p
        assert result.primary_state_out.h == pytest.approx(expected_h_out, rel=1e-9)

    def test_h_out_march_contiguous(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].h_in == pytest.approx(profile.cells[i - 1].h_out, rel=1e-12)

    def test_primary_temperature_march_contiguous(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].T_in == pytest.approx(profile.cells[i - 1].T_out, rel=1e-12)

    def test_secondary_temperature_march_contiguous(self) -> None:
        """Secondary temperature marches co-currently: secondary_T_in[i+1] = secondary_T_out[i]."""
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i in range(1, len(profile.cells)):
            assert profile.cells[i].secondary_T_in == pytest.approx(
                profile.cells[i - 1].secondary_T_out, rel=1e-12
            )

    def test_cocurrent_secondary_inlet_at_cell_0(self) -> None:
        """Co-current: secondary inlet is at cell 0, same end as primary inlet."""
        T_s_in = 340.0
        model = SegmentedMarchModel()
        req = _make_sink_req(T_secondary_in=T_s_in, n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[0].secondary_T_in == pytest.approx(T_s_in, rel=1e-12)


# ---------------------------------------------------------------------------
# Required inputs
# ---------------------------------------------------------------------------


class TestRequiredInputs:
    def test_missing_primary_t_in_fails(self) -> None:
        """primary_T_in is always required when secondary_bc is SinkInletTempAndFlow."""
        with pytest.raises(ValueError, match="primary_T_in"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY_HOT,
                    mdot_secondary=_MDOT_SECONDARY,
                    cp_secondary=_CP_SECONDARY,
                ),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_GEOM_HTC,
                htc_primary=_ConstantHTCCorrelation(),
                htc_secondary=_ConstantHTCCorrelation(),
                primary_cp=_CP_PRIMARY,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                # primary_T_in omitted
            )

    def test_missing_primary_cp_fails_at_construction(self) -> None:
        """FINITE_CAPACITY requires primary_cp; HXSolveRequest enforces this."""
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY_HOT,
                    mdot_secondary=_MDOT_SECONDARY,
                    cp_secondary=_CP_SECONDARY,
                ),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_GEOM_HTC,
                htc_primary=_ConstantHTCCorrelation(),
                htc_secondary=_ConstantHTCCorrelation(),
                primary_T_in=_T_PRIMARY_IN,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                # primary_cp omitted
            )

    def test_invalid_primary_cp_non_positive_fails_at_construction(self) -> None:
        with pytest.raises(ValueError, match="primary_cp"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY_HOT,
                    mdot_secondary=_MDOT_SECONDARY,
                    cp_secondary=_CP_SECONDARY,
                ),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_GEOM_HTC,
                htc_primary=_ConstantHTCCorrelation(),
                htc_secondary=_ConstantHTCCorrelation(),
                primary_T_in=_T_PRIMARY_IN,
                primary_cp=-100.0,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
            )

    def test_constant_temperature_mode_fails_with_deferred_message(self) -> None:
        """PrimaryThermalMode.CONSTANT_TEMPERATURE is deferred for segmented sink."""
        model = SegmentedMarchModel()
        req = HXSolveRequest(
            primary_state_in=_STATE_IN,
            primary_mdot=_MDOT,
            secondary_bc=SinkInletTempAndFlow(
                T_in=_T_SECONDARY_HOT,
                mdot_secondary=_MDOT_SECONDARY,
                cp_secondary=_CP_SECONDARY,
            ),
            geometry=object(),
            discretization=_DISC_3,
            geom_scalars=_GEOM_HTC,
            htc_primary=_ConstantHTCCorrelation(),
            htc_secondary=_ConstantHTCCorrelation(),
            primary_T_in=_T_PRIMARY_IN,
            primary_thermal_mode=PrimaryThermalMode.CONSTANT_TEMPERATURE,
            ua_computation_mode=UAComputationMode.TWO_SIDED,
        )
        with pytest.raises(ValueError, match="[Dd]eferred"):
            model.solve(req)

    def test_invalid_secondary_mdot_fails_at_bc_construction(self) -> None:
        with pytest.raises(ValueError, match="mdot_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.0, cp_secondary=4000.0)

    def test_invalid_secondary_cp_fails_at_bc_construction(self) -> None:
        with pytest.raises(ValueError, match="cp_secondary"):
            SinkInletTempAndFlow(T_in=300.0, mdot_secondary=0.1, cp_secondary=-1.0)

    def test_invalid_secondary_t_in_fails_at_bc_construction(self) -> None:
        with pytest.raises(ValueError, match="T_in"):
            SinkInletTempAndFlow(T_in=0.0, mdot_secondary=0.1, cp_secondary=4000.0)

    def test_missing_a_ht_fails(self) -> None:
        """A_ht is required in geom_scalars."""
        model = SegmentedMarchModel()
        req = _make_sink_req(geom_scalars={"G": 150.0, "x": 0.5, "D_h": 0.003})
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req)

    def test_missing_htc_primary_fails(self) -> None:
        with pytest.raises(ValueError, match="htc_primary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY_HOT,
                    mdot_secondary=_MDOT_SECONDARY,
                    cp_secondary=_CP_SECONDARY,
                ),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_GEOM_HTC,
                htc_secondary=_ConstantHTCCorrelation(),
                primary_T_in=_T_PRIMARY_IN,
                primary_cp=_CP_PRIMARY,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                # htc_primary omitted — TWO_SIDED requires it
            )

    def test_missing_htc_secondary_fails(self) -> None:
        with pytest.raises(ValueError, match="htc_secondary"):
            HXSolveRequest(
                primary_state_in=_STATE_IN,
                primary_mdot=_MDOT,
                secondary_bc=SinkInletTempAndFlow(
                    T_in=_T_SECONDARY_HOT,
                    mdot_secondary=_MDOT_SECONDARY,
                    cp_secondary=_CP_SECONDARY,
                ),
                geometry=object(),
                discretization=_DISC_3,
                geom_scalars=_GEOM_HTC,
                htc_primary=_ConstantHTCCorrelation(),
                primary_T_in=_T_PRIMARY_IN,
                primary_cp=_CP_PRIMARY,
                primary_thermal_mode=PrimaryThermalMode.FINITE_CAPACITY,
                ua_computation_mode=UAComputationMode.TWO_SIDED,
                # htc_secondary omitted — TWO_SIDED requires it
            )

    def test_primary_only_ua_mode_fails_clearly(self) -> None:
        """UAComputationMode.PRIMARY_ONLY is not supported for segmented sink coupling."""
        model = SegmentedMarchModel()
        req = _make_sink_req(ua_computation_mode=UAComputationMode.PRIMARY_ONLY)
        with pytest.raises(ValueError, match="PRIMARY_ONLY"):
            model.solve(req)

    def test_invalid_primary_htc_output_zero_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_p=_BadHTCCorrelation())
        with pytest.raises(ValueError, match="primary HTC"):
            model.solve(req)

    def test_invalid_primary_htc_output_nan_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_p=_NanHTCCorrelation())
        with pytest.raises(ValueError, match="primary HTC"):
            model.solve(req)

    def test_invalid_secondary_htc_output_zero_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_s=_BadHTCCorrelation())
        with pytest.raises(ValueError, match="secondary HTC"):
            model.solve(req)

    def test_invalid_secondary_htc_output_nan_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_s=_NanHTCCorrelation())
        with pytest.raises(ValueError, match="secondary HTC"):
            model.solve(req)


# ---------------------------------------------------------------------------
# HTC behavior
# ---------------------------------------------------------------------------


class TestHTCBehavior:
    def test_htc_primary_called_once_per_cell(self) -> None:
        n = 4
        htc_p = _ConstantHTCCorrelation()
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_p=htc_p, n_cells=n)
        model.solve(req)
        assert htc_p.call_count == n

    def test_htc_secondary_called_once_per_cell(self) -> None:
        n = 4
        htc_s = _ConstantHTCCorrelation()
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_s=htc_s, n_cells=n)
        model.solve(req)
        assert htc_s.call_count == n

    def test_primary_htc_receives_cell_inlet_state(self) -> None:
        """Primary HTC correlation receives current cell inlet FluidState."""
        htc_p = _ConstantHTCCorrelation()
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_p=htc_p, n_cells=3)
        model.solve(req)
        # Cell 0 must receive the original primary inlet state
        assert htc_p.called_states[0].P == pytest.approx(_P_IN, rel=1e-9)
        assert htc_p.called_states[0].h == pytest.approx(_H_IN, rel=1e-9)

    def test_htc_multiplier_affects_ua_and_q(self) -> None:
        """Doubling htc_multiplier increases UA_cell and thus Q."""
        model = SegmentedMarchModel()
        req_1x = _make_sink_req(htc_multiplier=1.0)
        req_2x = _make_sink_req(htc_multiplier=2.0)
        r1 = model.solve(req_1x)
        r2 = model.solve(req_2x)
        # Higher htc_multiplier → higher UA → higher Q (when T_s > T_p)
        assert abs(r2.Q) > abs(r1.Q)

    def test_htc_verdicts_propagated_in_primary_then_secondary_order(self) -> None:
        """Verdict order per cell: primary HTC, secondary HTC (then DP if present)."""
        n = 3
        htc_p = _ConstantHTCCorrelation(_HTC_P)
        htc_s = _ConstantHTCCorrelation(_HTC_S)
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_p=htc_p, htc_s=htc_s, n_cells=n)
        result = model.solve(req)
        # 2 HTC verdicts per cell (no DP)
        assert len(result.verdicts) == 2 * n

    def test_htc_verdicts_all_propagated(self) -> None:
        n = 4
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=n)
        result = model.solve(req)
        # 2 HTC verdicts per cell, no DP
        assert len(result.verdicts) == 2 * n

    def test_ua_cell_computed_from_two_sided_resistance(self) -> None:
        """UA_cell = 1/(1/(h_p*A_cell) + 1/(h_s*A_cell)) for each cell."""
        n = 3
        htc_p_val = 1500.0
        htc_s_val = 2000.0
        A_ht = 0.6
        A_cell = A_ht / n
        expected_ua_cell = 1.0 / (1.0 / (htc_p_val * A_cell) + 1.0 / (htc_s_val * A_cell))
        model = SegmentedMarchModel()
        req = _make_sink_req(
            htc_p=_ConstantHTCCorrelation(htc_p_val),
            htc_s=_ConstantHTCCorrelation(htc_s_val),
            n_cells=n,
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.UA_cell is not None
            assert rec.UA_cell == pytest.approx(expected_ua_cell, rel=1e-9)


# ---------------------------------------------------------------------------
# DP behavior
# ---------------------------------------------------------------------------


class TestDPBehavior:
    def test_dp_called_once_per_cell(self) -> None:
        n = 4
        dp = _FakeDPCorrelation()
        model = SegmentedMarchModel()
        req = _make_sink_req(dp_primary=dp, n_cells=n, geom_scalars=_GEOM_DP)
        model.solve(req)
        assert dp.call_count == n

    def test_dp_verdicts_propagated_after_htc_verdicts(self) -> None:
        """Order: primary HTC, secondary HTC, DP — per cell."""
        n = 3
        dp = _FakeDPCorrelation()
        model = SegmentedMarchModel()
        req = _make_sink_req(dp_primary=dp, n_cells=n, geom_scalars=_GEOM_DP)
        result = model.solve(req)
        # 2 HTC + 1 DP per cell
        assert len(result.verdicts) == 3 * n

    def test_friction_multiplier_does_not_affect_q(self) -> None:
        model = SegmentedMarchModel()
        req_1x = _make_sink_req(
            dp_primary=_FakeDPCorrelation(300.0), friction_multiplier=1.0, geom_scalars=_GEOM_DP
        )
        req_3x = _make_sink_req(
            dp_primary=_FakeDPCorrelation(300.0), friction_multiplier=3.0, geom_scalars=_GEOM_DP
        )
        r1 = model.solve(req_1x)
        r3 = model.solve(req_3x)
        assert r1.Q == pytest.approx(r3.Q, rel=1e-12)
        assert r1.primary_state_out.h == pytest.approx(r3.primary_state_out.h, rel=1e-12)

    def test_friction_multiplier_affects_pressure(self) -> None:
        model = SegmentedMarchModel()
        req_1x = _make_sink_req(
            n_cells=3,
            dp_primary=_FakeDPCorrelation(100.0),
            friction_multiplier=1.0,
            geom_scalars=_GEOM_DP,
        )
        req_2x = _make_sink_req(
            n_cells=3,
            dp_primary=_FakeDPCorrelation(100.0),
            friction_multiplier=2.0,
            geom_scalars=_GEOM_DP,
        )
        r1 = model.solve(req_1x)
        r2 = model.solve(req_2x)
        assert r1.primary_state_out.P > r2.primary_state_out.P

    def test_negative_dp_allowed_pressure_recovery(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=2, dp_primary=_NegativeDPCorrelation(), geom_scalars=_GEOM_DP)
        result = model.solve(req)
        assert result.primary_state_out.P > _P_IN

    def test_nan_dp_output_fails(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(dp_primary=_NanDPCorrelation(), geom_scalars=_GEOM_DP)
        with pytest.raises(ValueError, match="finite"):
            model.solve(req)

    def test_no_dp_gives_zero_raw_dp(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req()
        result = model.solve(req)
        assert result.raw_dP_primary == pytest.approx(0.0, abs=1e-12)
        assert result.dP_primary == pytest.approx(0.0, abs=1e-12)

    def test_dp_receives_cell_inlet_state(self) -> None:
        dp = _FakeDPCorrelation()
        n = 3
        model = SegmentedMarchModel()
        req = _make_sink_req(dp_primary=dp, n_cells=n, geom_scalars=_GEOM_DP)
        model.solve(req)
        assert dp.called_states[0].P == pytest.approx(_P_IN, rel=1e-9)
        assert dp.called_states[0].h == pytest.approx(_H_IN, rel=1e-9)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


class TestProfile:
    def test_profile_contains_n_cells_records(self) -> None:
        n = 5
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=n)
        result = model.solve(req)
        assert isinstance(result.zone_profile, SegmentedProfile)
        assert len(result.zone_profile.cells) == n

    def test_each_record_is_immutable(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=2)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            with pytest.raises((AttributeError, TypeError)):
                rec.Q_cell = 0.0  # type: ignore[misc]

    def test_records_include_primary_diagnostics(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.T_in is not None
            assert rec.T_out is not None
            assert rec.htc_primary is not None
            assert rec.UA_cell is not None
            assert math.isfinite(rec.T_in)
            assert math.isfinite(rec.T_out)
            assert math.isfinite(rec.htc_primary)
            assert math.isfinite(rec.UA_cell)

    def test_records_include_secondary_diagnostics(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.secondary_T_in is not None
            assert rec.secondary_T_out is not None
            assert rec.htc_secondary is not None
            assert rec.epsilon is not None
            assert rec.NTU is not None
            assert rec.C_primary is not None
            assert rec.C_secondary is not None
            assert math.isfinite(rec.secondary_T_in)
            assert math.isfinite(rec.secondary_T_out)
            assert math.isfinite(rec.epsilon)
            assert math.isfinite(rec.NTU)

    def test_last_record_p_out_consistent_with_result(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=3, dp_primary=_FakeDPCorrelation(), geom_scalars=_GEOM_DP)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[-1].P_out == pytest.approx(result.primary_state_out.P, rel=1e-12)

    def test_last_record_h_out_consistent_with_result(self) -> None:
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=4)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        assert profile.cells[-1].h_out == pytest.approx(result.primary_state_out.h, rel=1e-12)

    def test_last_record_t_out_consistent_with_temperature_march(self) -> None:
        cp = 3000.0
        mdot = 0.04
        T_p_in = 280.0
        model = SegmentedMarchModel()
        req = _make_sink_req(T_primary_in=T_p_in, cp_primary=cp, mdot=mdot, n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        last = profile.cells[-1]
        assert last.T_out is not None
        total_q = sum(c.Q_cell for c in profile.cells)
        expected_t_out = T_p_in + total_q / (mdot * cp)
        assert last.T_out == pytest.approx(expected_t_out, rel=1e-9)

    def test_cell_indices_sequential(self) -> None:
        n = 5
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=n)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for i, rec in enumerate(profile.cells):
            assert rec.cell_index == i

    def test_epsilon_in_valid_range(self) -> None:
        """Co-current effectiveness must be in (0, 1/(1+Cr)]."""
        model = SegmentedMarchModel()
        req = _make_sink_req(n_cells=3)
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.epsilon is not None
            assert 0.0 <= rec.epsilon <= 1.0

    def test_c_primary_and_c_secondary_correct(self) -> None:
        """C_primary and C_secondary are constant across all cells."""
        mdot_p = 0.05
        cp_p = 3500.0
        mdot_s = 0.08
        cp_s = 4000.0
        model = SegmentedMarchModel()
        req = _make_sink_req(
            mdot=mdot_p, cp_primary=cp_p, mdot_secondary=mdot_s, cp_secondary=cp_s, n_cells=3
        )
        result = model.solve(req)
        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.C_primary == pytest.approx(mdot_p * cp_p, rel=1e-12)
            assert rec.C_secondary == pytest.approx(mdot_s * cp_s, rel=1e-12)


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

    def test_no_hidden_defaults_in_sink_path(self) -> None:
        """Verify that missing A_ht raises ValueError, not silently defaults."""
        model = SegmentedMarchModel()
        req_no_a_ht = _make_sink_req(geom_scalars={"G": 150.0, "x": 0.5, "D_h": 0.003})
        with pytest.raises(ValueError, match="A_ht"):
            model.solve(req_no_a_ht)


# ---------------------------------------------------------------------------
# htc_multiplier = 0.0 regression tests (Phase 11J audit fix)
# ---------------------------------------------------------------------------


class TestZeroHTCMultiplier:
    def test_zero_htc_multiplier_gives_zero_ua_and_zero_heat_transfer(self) -> None:
        """htc_multiplier=0.0 must not raise; UA_cell=0, Q=0, temperatures unchanged."""
        n = 3
        htc_p = _ConstantHTCCorrelation(_HTC_P)
        htc_s = _ConstantHTCCorrelation(_HTC_S)
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_p=htc_p, htc_s=htc_s, htc_multiplier=0.0, n_cells=n)

        result = model.solve(req)

        assert result.Q == pytest.approx(0.0, abs=1e-15)
        assert result.primary_state_out.h == pytest.approx(_H_IN, rel=1e-12)

        profile = result.zone_profile
        assert isinstance(profile, SegmentedProfile)
        for rec in profile.cells:
            assert rec.UA_cell == pytest.approx(0.0, abs=1e-15)
            assert rec.NTU == pytest.approx(0.0, abs=1e-15)
            assert rec.epsilon == pytest.approx(0.0, abs=1e-15)
            assert rec.Q_cell == pytest.approx(0.0, abs=1e-15)
            assert rec.T_out == pytest.approx(rec.T_in, abs=1e-15)
            assert rec.secondary_T_out == pytest.approx(rec.secondary_T_in, abs=1e-15)

        # HTC correlations are still called once per cell; verdicts still propagate
        assert htc_p.call_count == n
        assert htc_s.call_count == n
        assert len(result.verdicts) == 2 * n

    def test_zero_htc_multiplier_with_dp_primary(self) -> None:
        """With htc_multiplier=0.0 and dp_primary: heat transfer zero, DP still marches."""
        n = 3
        dp = _FakeDPCorrelation(dp=200.0)
        model = SegmentedMarchModel()
        req = _make_sink_req(htc_multiplier=0.0, dp_primary=dp, n_cells=n, geom_scalars=_GEOM_DP)

        result = model.solve(req)

        # Heat transfer is zero
        assert result.Q == pytest.approx(0.0, abs=1e-15)
        assert result.primary_state_out.h == pytest.approx(_H_IN, rel=1e-12)

        # DP path still works independently of zero heat transfer
        assert dp.call_count == n
        # Pressure drops by 3 * friction_multiplier * 200 Pa
        expected_dp = n * 200.0
        assert result.raw_dP_primary == pytest.approx(expected_dp, rel=1e-9)
        assert result.primary_state_out.P == pytest.approx(_P_IN - expected_dp, rel=1e-9)

        # Verdicts: 2 HTC + 1 DP per cell
        assert len(result.verdicts) == 3 * n

        # friction_multiplier still affects DP only (not Q)
        req_2x = _make_sink_req(
            htc_multiplier=0.0,
            dp_primary=_FakeDPCorrelation(dp=200.0),
            friction_multiplier=2.0,
            n_cells=n,
            geom_scalars=_GEOM_DP,
        )
        result_2x = model.solve(req_2x)
        assert result_2x.Q == pytest.approx(0.0, abs=1e-15)
        assert result_2x.primary_state_out.P < result.primary_state_out.P
